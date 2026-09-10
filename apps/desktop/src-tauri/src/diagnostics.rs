//! Bounded native spool, independent of sidecar readiness. No content or paths in payloads.
use serde::Serialize;
use std::fs;
use std::io::{Read, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

const MAX_EVENTS: usize = 256;
const MAX_AGE: Duration = Duration::from_secs(7 * 24 * 60 * 60);
const MAX_EVENT_BYTES: u64 = 16 * 1024;
const MAX_SPOOL_BYTES: u64 = MAX_EVENTS as u64 * MAX_EVENT_BYTES;
static UNIQUE: AtomicU64 = AtomicU64::new(0);

fn identity() -> String {
    format!(
        "desktop-{:032x}-{:08x}-{:016x}",
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos(),
        std::process::id(),
        UNIQUE.fetch_add(1, Ordering::Relaxed)
    )
}

#[derive(Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
pub enum DesktopEvent {
    DesktopStarted,
    SidecarSpawned,
    SidecarReady,
    SidecarStartupFailed,
    SidecarExited,
    DesktopShutdownRequested,
    SidecarStopped,
    SidecarShutdownUnknown,
    DesktopStopped,
}

#[derive(Serialize)]
struct Record {
    schema_version: &'static str,
    event_id: String,
    instance_id: String,
    name: DesktopEvent,
    unix_time_ms: u64,
    duration_ms: Option<u64>,
    exit_code: Option<i32>,
    dropped_before: u64,
    write_failures_before: u64,
}

#[derive(Clone)]
pub struct DesktopDiagnostics {
    root: PathBuf,
    instance_id: String,
    lock: Arc<Mutex<()>>,
    failures: Arc<AtomicU64>,
}

impl DesktopDiagnostics {
    pub fn new(storage_root: &Path) -> Self {
        Self {
            root: storage_root.join("diagnostics").join("desktop-spool"),
            instance_id: identity(),
            lock: Arc::new(Mutex::new(())),
            failures: Arc::new(AtomicU64::new(0)),
        }
    }

    pub fn emit(&self, name: DesktopEvent, duration_ms: Option<u64>, exit_code: Option<i32>) {
        if self.write(name, duration_ms, exit_code).is_err() {
            self.failures.fetch_add(1, Ordering::Relaxed);
            eprintln!("desktop_diagnostic_write_failed");
        }
    }

    fn write(
        &self,
        name: DesktopEvent,
        duration_ms: Option<u64>,
        exit_code: Option<i32>,
    ) -> std::io::Result<()> {
        let _guard = self
            .lock
            .lock()
            .map_err(|_| std::io::Error::other("diagnostic_lock_failed"))?;
        fs::create_dir_all(&self.root)?;
        let process_lock = fs::OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(self.root.join("spool.quota-lock"))?;
        let deadline = Instant::now() + Duration::from_millis(50);
        loop {
            if process_lock.try_lock().is_ok() {
                break;
            }
            if Instant::now() >= deadline {
                return Err(std::io::Error::other("diagnostic_spool_busy"));
            }
            std::thread::sleep(Duration::from_millis(1));
        }
        let drops_path = self.root.join("drops.count");
        let pending_count = self.root.join("drops.pending");
        let mut drops = read_counter(&drops_path)?.unwrap_or(0);
        match read_counter(&pending_count) {
            Ok(Some(pending)) if pending >= drops => {
                fs::rename(&pending_count, &drops_path)?;
                sync_directory(&self.root)?;
                drops = pending;
            }
            Ok(Some(_)) => {
                // A stale checkpoint cannot lower the last durable count.
                fs::remove_file(&pending_count)?;
                sync_directory(&self.root)?;
                self.failures.fetch_add(1, Ordering::Relaxed);
            }
            Err(error) if error.kind() == std::io::ErrorKind::InvalidData => {
                // A crash during temporary-file write leaves an unknown gap.
                // Preserve the durable lower bound, never reset drops.count.
                fs::remove_file(&pending_count)?;
                sync_directory(&self.root)?;
                self.failures.fetch_add(1, Ordering::Relaxed);
            }
            Ok(None) => {}
            Err(error) => return Err(error),
        }
        let original_drops = drops;
        let mut files = Vec::new();
        let mut total_bytes = 0u64;
        for (i, entry) in fs::read_dir(&self.root)?.enumerate() {
            if i >= 1024 {
                return Err(std::io::Error::other("diagnostic_spool_scan_limit"));
            }
            let entry = entry?;
            let path = entry.path();
            let name = entry.file_name();
            let Some(name) = name.to_str() else {
                continue;
            };
            if !event_filename(name) {
                continue;
            }
            let metadata = fs::symlink_metadata(&path)?;
            if !metadata.is_file() {
                continue;
            }
            if SystemTime::now()
                .duration_since(metadata.modified()?)
                .is_ok_and(|age| age > MAX_AGE)
            {
                fs::remove_file(&path)?;
                drops = drops.saturating_add(1);
                continue;
            }
            total_bytes = total_bytes.saturating_add(metadata.len());
            files.push((path, metadata.len()));
        }
        files.sort_by(|a, b| a.0.cmp(&b.0));
        // Reserve a maximum-sized new record before creating its pending file.
        while files.len() >= MAX_EVENTS
            || total_bytes.saturating_add(MAX_EVENT_BYTES) > MAX_SPOOL_BYTES
        {
            if files.is_empty() {
                return Err(std::io::Error::other("diagnostic_spool_budget"));
            }
            let (oldest, bytes) = files.remove(0);
            match fs::remove_file(oldest) {
                Ok(()) => {
                    drops = drops.saturating_add(1);
                    total_bytes = total_bytes.saturating_sub(bytes);
                }
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
                    total_bytes = total_bytes.saturating_sub(bytes);
                }
                Err(error) => return Err(error),
            }
        }
        if drops != original_drops {
            // Persist deletions before a checkpoint can claim those evictions.
            sync_directory(&self.root)?;
        }
        if drops != original_drops || !drops_path.exists() {
            let mut file = fs::OpenOptions::new()
                .write(true)
                .create_new(true)
                .open(&pending_count)?;
            file.write_all(drops.to_string().as_bytes())?;
            file.sync_all()?;
            drop(file);
            fs::rename(&pending_count, &drops_path)?;
            sync_directory(&self.root)?;
        }
        let event_id = identity();
        let record = Record {
            schema_version: "desktop-diagnostic-v1",
            event_id: event_id.clone(),
            instance_id: self.instance_id.clone(),
            name,
            unix_time_ms: SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .unwrap_or_default()
                .as_millis() as u64,
            duration_ms,
            exit_code,
            dropped_before: drops,
            write_failures_before: self.failures.load(Ordering::Relaxed),
        };
        let bytes = serde_json::to_vec(&record)?;
        if bytes.len() as u64 > MAX_EVENT_BYTES {
            return Err(std::io::Error::other("diagnostic_event_size"));
        }
        let pending = self.root.join(format!("{event_id}.pending"));
        let mut file = fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&pending)?;
        file.write_all(&bytes)?;
        file.sync_all()?;
        drop(file);
        fs::rename(pending, self.root.join(format!("{event_id}.json")))?;
        sync_directory(&self.root)?;
        Ok(())
    }
}

fn event_filename(name: &str) -> bool {
    let stem = name
        .strip_suffix(".json")
        .or_else(|| name.strip_suffix(".pending"));
    stem.and_then(|stem| stem.strip_prefix("desktop-"))
        .is_some_and(|id| {
            !id.is_empty()
                && id.len() <= 88
                && id
                    .chars()
                    .all(|c| c.is_ascii_digit() || ('a'..='f').contains(&c) || c == '-')
        })
}

fn read_counter(path: &Path) -> std::io::Result<Option<u64>> {
    let mut options = fs::OpenOptions::new();
    options.read(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK);
    }
    let file = match options.open(path) {
        Ok(file) => file,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
    };
    if !file.metadata()?.is_file() {
        return Err(std::io::Error::other("diagnostic_counter_type"));
    }
    let mut text = String::new();
    file.take(21).read_to_string(&mut text)?;
    if text.is_empty() || text.len() > 20 || !text.bytes().all(|c| c.is_ascii_digit()) {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "diagnostic_counter_invalid",
        ));
    }
    text.parse().map(Some).map_err(|_| {
        std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "diagnostic_counter_invalid",
        )
    })
}

fn sync_directory(path: &Path) -> std::io::Result<()> {
    #[cfg(unix)]
    {
        fs::File::open(path)?.sync_all()?;
    }
    #[cfg(not(unix))]
    {
        let _ = path;
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_wire_matches_shared_fixture() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../../packages/shared/fixtures/diagnostics/desktop-spool-v1.json"
        ))
        .unwrap();
        let record = Record {
            schema_version: "desktop-diagnostic-v1",
            event_id: fixture["event_id"].as_str().unwrap().into(),
            instance_id: fixture["instance_id"].as_str().unwrap().into(),
            name: DesktopEvent::SidecarExited,
            unix_time_ms: 1789012800000,
            duration_ms: None,
            exit_code: Some(7),
            dropped_before: 3,
            write_failures_before: 1,
        };
        assert_eq!(serde_json::to_value(record).unwrap(), fixture);
    }
    #[test]
    fn spool_is_bounded_and_reports_eviction_without_content() {
        let root = std::env::temp_dir().join(identity());
        let diagnostics = DesktopDiagnostics::new(&root);
        for _ in 0..260 {
            diagnostics.emit(DesktopEvent::DesktopStarted, None, None);
        }
        let files: Vec<_> = fs::read_dir(root.join("diagnostics/desktop-spool"))
            .unwrap()
            .filter_map(Result::ok)
            .filter(|entry| entry.path().extension().is_some_and(|ext| ext == "json"))
            .collect();
        assert_eq!(files.len(), MAX_EVENTS);
        assert_eq!(
            fs::read_to_string(root.join("diagnostics/desktop-spool/drops.count")).unwrap(),
            "4"
        );
        let text = fs::read_to_string(files[0].path()).unwrap();
        assert!(!text.contains(root.to_str().unwrap()));
        let value: serde_json::Value = serde_json::from_str(&text).unwrap();
        assert_eq!(value["schema_version"], "desktop-diagnostic-v1");
        assert_eq!(value["name"], "desktop_started");
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn write_failure_is_best_effort() {
        let root = std::env::temp_dir().join(identity());
        fs::write(&root, b"not a directory").unwrap();
        let diagnostics = DesktopDiagnostics::new(&root);
        diagnostics.emit(DesktopEvent::SidecarStartupFailed, Some(1), None);
        assert_eq!(diagnostics.failures.load(Ordering::Relaxed), 1);
        fs::remove_file(root).unwrap();
    }
    #[test]
    fn pending_counter_recovers_without_resetting_durable_lower_bound() {
        let root = std::env::temp_dir().join(identity());
        let diagnostics = DesktopDiagnostics::new(&root);
        fs::create_dir_all(&diagnostics.root).unwrap();
        fs::write(diagnostics.root.join("drops.count"), "7").unwrap();
        fs::write(diagnostics.root.join("drops.pending"), "9").unwrap();
        diagnostics
            .write(DesktopEvent::DesktopStarted, None, None)
            .unwrap();
        assert_eq!(
            read_counter(&diagnostics.root.join("drops.count")).unwrap(),
            Some(9)
        );
        fs::write(diagnostics.root.join("drops.pending"), "").unwrap();
        diagnostics
            .write(DesktopEvent::DesktopStarted, None, None)
            .unwrap();
        assert_eq!(
            read_counter(&diagnostics.root.join("drops.count")).unwrap(),
            Some(9)
        );
        assert_eq!(diagnostics.failures.load(Ordering::Relaxed), 1);
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    fn spool_child_process() {
        let Ok(root) = std::env::var("DIAGNOSTIC_SPOOL_TEST_ROOT") else {
            return;
        };
        let diagnostics = DesktopDiagnostics::new(Path::new(&root));
        for _ in 0..140 {
            let deadline = Instant::now() + Duration::from_secs(10);
            while diagnostics
                .write(DesktopEvent::DesktopStarted, None, None)
                .is_err()
            {
                assert!(Instant::now() < deadline);
                std::thread::sleep(Duration::from_millis(1));
            }
        }
    }

    // Invoked only by the cross-runtime installation probe. Ordinary cargo
    // tests leave the environment unset and do not touch any runtime directory.
    #[test]
    fn installation_spool_child_process() {
        let Ok(root) = std::env::var("DIAGNOSTIC_INSTALLATION_TEST_ROOT") else {
            return;
        };
        let diagnostics = DesktopDiagnostics::new(Path::new(&root));
        for _ in 0..1200 {
            let deadline = Instant::now() + Duration::from_secs(5);
            while diagnostics
                .write(DesktopEvent::DesktopStarted, None, None)
                .is_err()
            {
                assert!(Instant::now() < deadline);
                std::thread::sleep(Duration::from_millis(1));
            }
            std::thread::sleep(Duration::from_millis(1));
        }
    }

    #[test]
    fn two_process_writers_share_ring_and_eviction_counter() {
        let root = std::env::temp_dir().join(identity());
        let spawn = || {
            std::process::Command::new(std::env::current_exe().unwrap())
                .args(["--exact", "diagnostics::tests::spool_child_process"])
                .env("DIAGNOSTIC_SPOOL_TEST_ROOT", &root)
                .stdout(std::process::Stdio::null())
                .spawn()
                .unwrap()
        };
        let mut first = spawn();
        let mut second = spawn();
        assert!(first.wait().unwrap().success());
        assert!(second.wait().unwrap().success());
        let diagnostics = DesktopDiagnostics::new(&root);
        let events: Vec<_> = fs::read_dir(&diagnostics.root)
            .unwrap()
            .map(Result::unwrap)
            .filter(|entry| event_filename(&entry.file_name().to_string_lossy()))
            .collect();
        assert_eq!(events.len(), MAX_EVENTS);
        assert_eq!(
            read_counter(&diagnostics.root.join("drops.count")).unwrap(),
            Some(24)
        );
        assert!(
            events
                .iter()
                .map(|entry| entry.metadata().unwrap().len())
                .sum::<u64>()
                <= MAX_SPOOL_BYTES
        );
        fs::remove_dir_all(root).unwrap();
    }

    #[cfg(unix)]
    #[test]
    fn native_lock_interoperates_with_python_flock_protocol() {
        use std::os::fd::AsRawFd;
        let root = std::env::temp_dir().join(identity());
        let diagnostics = DesktopDiagnostics::new(&root);
        fs::create_dir_all(&diagnostics.root).unwrap();
        let file = fs::OpenOptions::new()
            .read(true)
            .write(true)
            .create(true)
            .truncate(false)
            .open(diagnostics.root.join("spool.quota-lock"))
            .unwrap();
        assert_eq!(
            unsafe { libc::flock(file.as_raw_fd(), libc::LOCK_EX | libc::LOCK_NB) },
            0
        );
        assert!(diagnostics
            .write(DesktopEvent::DesktopStarted, None, None)
            .is_err());
        drop(file);
        diagnostics
            .write(DesktopEvent::DesktopStarted, None, None)
            .unwrap();
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn expired_and_oversized_spool_entries_are_evicted_before_new_write() {
        let root = std::env::temp_dir().join(identity());
        let diagnostics = DesktopDiagnostics::new(&root);
        fs::create_dir_all(&diagnostics.root).unwrap();
        let old = diagnostics.root.join("desktop-a.json");
        fs::write(&old, b"{}").unwrap();
        fs::OpenOptions::new()
            .write(true)
            .open(&old)
            .unwrap()
            .set_times(fs::FileTimes::new().set_modified(UNIX_EPOCH))
            .unwrap();
        let oversized = diagnostics.root.join("desktop-b.pending");
        fs::OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&oversized)
            .unwrap()
            .set_len(MAX_SPOOL_BYTES + 1)
            .unwrap();
        diagnostics
            .write(DesktopEvent::DesktopStarted, None, None)
            .unwrap();
        assert!(!old.exists());
        assert!(!oversized.exists());
        assert_eq!(
            read_counter(&diagnostics.root.join("drops.count")).unwrap(),
            Some(2)
        );
        fs::remove_dir_all(root).unwrap();
    }
}
