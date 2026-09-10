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
#[path = "diagnostic_counter.rs"]
mod counter;

static UNIQUE: AtomicU64 = AtomicU64::new(0);

#[cfg(test)]
#[path = "diagnostic_counter_prototype.rs"]
mod counter_prototype;

#[cfg(test)]
thread_local! {
    static WRITE_TIMING: std::cell::RefCell<Option<(Instant, Vec<(&'static str, f64)>)>> = const { std::cell::RefCell::new(None) };
}

#[cfg(test)]
fn timing_checkpoint(stage: &'static str) {
    WRITE_TIMING.with_borrow_mut(|probe| {
        if let Some((previous, samples)) = probe {
            let now = Instant::now();
            samples.push((stage, now.duration_since(*previous).as_secs_f64() * 1000.0));
            *previous = now;
        }
    });
}

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
        #[cfg(test)]
        timing_checkpoint("lock_admission");
        let pending_count = self.root.join("drops.pending");
        let mut journal = counter::Journal::load(&self.root)?;
        self.failures.fetch_add(journal.damaged as u64, Ordering::Relaxed);
        match read_counter(&pending_count) {
            Ok(Some(pending)) if pending >= journal.count => {
                journal.checkpoint(pending)?;
                fs::remove_file(&pending_count)?;
                sync_directory(&self.root)?;
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
        let mut drops = journal.count;
        let original_drops = drops;
        #[cfg(test)]
        timing_checkpoint("counter_recovery");
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
        #[cfg(test)]
        timing_checkpoint("scan_sort");
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
        if drops != original_drops || journal.needs_checkpoint() {
            #[cfg(test)]
            timing_checkpoint("eviction_sync");
            journal.checkpoint(drops)?;
        }
        let event_id = identity();
        #[cfg(test)]
        timing_checkpoint("counter_checkpoint");
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
        #[cfg(test)]
        timing_checkpoint("event_commit");
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
    #[test]
    #[ignore = "opt-in independent pending-file sync experiment"]
    fn pending_sync_overlap_probe() {
        let output = std::env::var("DIAGNOSTIC_SYNC_BENCH_OUTPUT").unwrap();
        let root = std::env::temp_dir().join(identity());
        fs::create_dir_all(&root).unwrap();
        let mut pairs = Vec::new();
        for index in 0..33 {
            let mut values = [0.0; 2];
            let order = if index % 2 == 0 { [0, 1] } else { [1, 0] };
            for mode in order {
                let counter_pending = root.join("counter.pending");
                let event_pending = root.join("event.pending");
                let started = Instant::now();
                // Common durable-deletion barrier from the actual rotation path.
                sync_directory(&root).unwrap();
                let mut counter = fs::File::create(&counter_pending).unwrap();
                counter.write_all(b"123").unwrap();
                let mut event = fs::File::create(&event_pending).unwrap();
                event.write_all(&[b'x'; 512]).unwrap();
                if mode == 0 {
                    counter.sync_all().unwrap();
                    event.sync_all().unwrap();
                } else {
                    std::thread::scope(|scope| {
                        let other = scope.spawn(|| counter.sync_all());
                        event.sync_all().unwrap();
                        other.join().unwrap().unwrap();
                    });
                }
                drop(counter);
                drop(event);
                // Keep both publication barriers and counter-before-event order.
                fs::rename(&counter_pending, root.join("counter.count")).unwrap();
                sync_directory(&root).unwrap();
                fs::rename(&event_pending, root.join("event.json")).unwrap();
                sync_directory(&root).unwrap();
                values[mode] = started.elapsed().as_secs_f64() * 1000.0;
                assert_eq!(fs::read(root.join("counter.count")).unwrap(), b"123");
                assert_eq!(fs::read(root.join("event.json")).unwrap(), [b'x'; 512]);
            }
            if index >= 3 {
                pairs.push(serde_json::json!({"first": if order[0] == 0 { "sequential" } else { "overlap" },
                    "sequential_ms": values[0], "overlap_ms": values[1], "delta_ms": values[1] - values[0]}));
            }
        }
        let report = serde_json::json!({"schema_version": "native-pending-sync-experiment-v1",
            "scope": "Synthetic two-file sync overlap, same three directory barriers; excludes native event serialization, scan, lock and actual crash recovery. No production protocol change.",
            "os": std::env::consts::OS, "arch": std::env::consts::ARCH,
            "warmup_pairs": 3, "sample_pairs": 30, "raw": pairs});
        fs::write(output, serde_json::to_vec_pretty(&report).unwrap()).unwrap();
        fs::remove_dir_all(root).unwrap();
    }

    #[test]
    #[ignore = "opt-in native spool timing; synthetic temporary files only"]
    fn spool_performance_probe() {
        let output = std::env::var("DIAGNOSTIC_SPOOL_BENCH_OUTPUT")
            .expect("set DIAGNOSTIC_SPOOL_BENCH_OUTPUT to the report path");
        let root = std::env::temp_dir().join(identity());
        let diagnostics = DesktopDiagnostics::new(&root);
        let mut sparse = Vec::new();
        let mut saturated = Vec::new();
        let mut contended = Vec::new();
        let mut saturated_stages = Vec::new();
        for index in 0..33 {
            let start = Instant::now();
            diagnostics.emit(DesktopEvent::DesktopStarted, None, None);
            if index >= 3 { sparse.push(start.elapsed().as_secs_f64() * 1000.0); }
        }
        for _ in 33..MAX_EVENTS { diagnostics.emit(DesktopEvent::DesktopStarted, None, None); }
        for index in 0..33 {
            let start = Instant::now();
            WRITE_TIMING.with_borrow_mut(|probe| *probe = Some((start, Vec::new())));
            diagnostics.emit(DesktopEvent::SidecarReady, Some(1), None);
            let stages = WRITE_TIMING.with_borrow_mut(|probe| probe.take().unwrap().1);
            if index >= 3 {
                saturated.push(start.elapsed().as_secs_f64() * 1000.0);
                saturated_stages.push(stages.into_iter().collect::<std::collections::BTreeMap<_, _>>());
            }
        }
        assert_eq!(diagnostics.failures.load(Ordering::Relaxed), 0);
        assert_eq!(Some(counter::Journal::load(&diagnostics.root).unwrap().count), Some(33));
        let held = fs::OpenOptions::new().read(true).write(true)
            .open(diagnostics.root.join("spool.quota-lock")).unwrap();
        held.lock().unwrap();
        for index in 0..33 {
            let start = Instant::now();
            diagnostics.emit(DesktopEvent::SidecarStopped, None, None);
            if index >= 3 { contended.push(start.elapsed().as_secs_f64() * 1000.0); }
        }
        drop(held);
        assert_eq!(diagnostics.failures.load(Ordering::Relaxed), 33);
        diagnostics.emit(DesktopEvent::DesktopStopped, None, None);
        assert_eq!(diagnostics.failures.load(Ordering::Relaxed), 33);
        let retained = fs::read_dir(&diagnostics.root).unwrap().filter_map(Result::ok)
            .filter(|entry| entry.path().extension().is_some_and(|ext| ext == "json")).count();
        assert_eq!(retained, MAX_EVENTS);
        fn summary(values: &[f64], budget: f64) -> serde_json::Value {
            let mut sorted = values.to_vec();
            sorted.sort_by(f64::total_cmp);
            let p95 = sorted[(sorted.len() as f64 * 0.95).ceil() as usize - 1];
            serde_json::json!({"count": sorted.len(), "p50": sorted[(sorted.len() as f64 * 0.5).ceil() as usize - 1],
                "p95": p95, "max": sorted.last().unwrap(), "budget_ms": budget, "passed": p95 <= budget})
        }
        let summaries = serde_json::json!({"sparse_emit_ms": summary(&sparse, 25.0),
            "saturated_emit_ms": summary(&saturated, 25.0), "contended_emit_ms": summary(&contended, 100.0)});
        let passed = summaries.as_object().unwrap().values().all(|value| value["passed"] == true);
        let report = serde_json::json!({"schema_version": "native-spool-benchmark-v1",
            "unix_time_ms": SystemTime::now().duration_since(UNIX_EPOCH).unwrap().as_millis(),
            "os": std::env::consts::OS, "arch": std::env::consts::ARCH, "debug_assertions": cfg!(debug_assertions),
            "scope": "Actual native emit, file lock, scan, fsync and rotation in a temporary directory; no sidecar consumer or WebView.",
            "gate_rationale": "P95 successful emit <=25 ms limits three startup events to a nominal 75 ms contribution; contended emit <=100 ms allows scheduling headroom over the existing 50 ms lock deadline. Local probe, not a hard filesystem latency bound.",
            "retained_events": retained, "observed_refused_emits": 33, "recovered_after_contention": true,
            "warmups_per_case": 3, "passed": passed, "summary": summaries,
            "raw": {"sparse_emit_ms": sparse, "saturated_emit_ms": saturated, "contended_emit_ms": contended,
                "saturated_stages_ms": saturated_stages}});
        fs::write(output, serde_json::to_vec_pretty(&report).unwrap()).unwrap();
        fs::remove_dir_all(root).unwrap();
        assert!(passed, "native spool performance budget exceeded; see report");
    }
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
            counter::Journal::load(&root.join("diagnostics/desktop-spool")).unwrap().count.to_string(),
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
            Some(counter::Journal::load(&diagnostics.root).unwrap().count),
            Some(9)
        );
        fs::write(diagnostics.root.join("drops.pending"), "").unwrap();
        diagnostics
            .write(DesktopEvent::DesktopStarted, None, None)
            .unwrap();
        assert_eq!(
            Some(counter::Journal::load(&diagnostics.root).unwrap().count),
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
            Some(counter::Journal::load(&diagnostics.root).unwrap().count),
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
            Some(counter::Journal::load(&diagnostics.root).unwrap().count),
            Some(2)
        );
        fs::remove_dir_all(root).unwrap();
    }
}
