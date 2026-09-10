//! Bounded native spool, independent of sidecar readiness. No content or paths in payloads.
use serde::Serialize;
use std::fs;
use std::io::Write;
use std::path::{Path, PathBuf};
use std::sync::{Arc, Mutex};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

const MAX_EVENTS: usize = 256;
static UNIQUE: AtomicU64 = AtomicU64::new(0);

fn identity() -> String {
    format!("desktop-{:032x}-{:08x}-{:016x}", SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_nanos(), std::process::id(), UNIQUE.fetch_add(1, Ordering::Relaxed))
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
        Self { root: storage_root.join("diagnostics").join("desktop-spool"), instance_id: identity(), lock: Arc::new(Mutex::new(())), failures: Arc::new(AtomicU64::new(0)) }
    }

    pub fn emit(&self, name: DesktopEvent, duration_ms: Option<u64>, exit_code: Option<i32>) {
        if self.write(name, duration_ms, exit_code).is_err() {
            self.failures.fetch_add(1, Ordering::Relaxed);
            eprintln!("desktop_diagnostic_write_failed");
        }
    }

    fn write(&self, name: DesktopEvent, duration_ms: Option<u64>, exit_code: Option<i32>) -> std::io::Result<()> {
        let _guard = self.lock.lock().map_err(|_| std::io::Error::other("diagnostic_lock_failed"))?;
        fs::create_dir_all(&self.root)?;
        let mut files: Vec<_> = fs::read_dir(&self.root)?.filter_map(Result::ok)
            .map(|entry| entry.path()).filter(|path| path.extension().is_some_and(|ext| ext == "json" || ext == "pending") && path.file_name().is_some_and(|name| name.to_string_lossy().starts_with("desktop-"))).collect();
        files.sort();
        let drops_path = self.root.join("drops.count");
        let mut drops = fs::read_to_string(&drops_path).ok().and_then(|text| text.parse::<u64>().ok()).unwrap_or(0);
        while files.len() >= MAX_EVENTS {
            let oldest = files.remove(0);
            match fs::remove_file(oldest) {
                Ok(()) => drops += 1,
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {},
                Err(error) => return Err(error),
            }
        }
        fs::write(drops_path, drops.to_string())?;
        let event_id = identity();
        let record = Record { schema_version: "desktop-diagnostic-v1", event_id: event_id.clone(), instance_id: self.instance_id.clone(), name,
            unix_time_ms: SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_millis() as u64,
            duration_ms, exit_code, dropped_before: drops, write_failures_before: self.failures.load(Ordering::Relaxed) };
        let bytes = serde_json::to_vec(&record)?;
        let pending = self.root.join(format!("{event_id}.pending"));
        let mut file = fs::OpenOptions::new().write(true).create_new(true).open(&pending)?;
        file.write_all(&bytes)?;
        file.sync_all()?;
        fs::rename(pending, self.root.join(format!("{event_id}.json")))?;
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn native_wire_matches_shared_fixture() {
        let fixture: serde_json::Value = serde_json::from_str(include_str!("../../../../packages/shared/fixtures/diagnostics/desktop-spool-v1.json")).unwrap();
        let record = Record {
            schema_version: "desktop-diagnostic-v1",
            event_id: fixture["event_id"].as_str().unwrap().into(),
            instance_id: fixture["instance_id"].as_str().unwrap().into(),
            name: DesktopEvent::SidecarExited,
            unix_time_ms: 1789012800000, duration_ms: None, exit_code: Some(7),
            dropped_before: 3, write_failures_before: 1,
        };
        assert_eq!(serde_json::to_value(record).unwrap(), fixture);
    }
    #[test]
    fn spool_is_bounded_and_reports_eviction_without_content() {
        let root = std::env::temp_dir().join(identity());
        let diagnostics = DesktopDiagnostics::new(&root);
        for _ in 0..260 { diagnostics.emit(DesktopEvent::DesktopStarted, None, None); }
        let files: Vec<_> = fs::read_dir(root.join("diagnostics/desktop-spool")).unwrap().filter_map(Result::ok).filter(|entry| entry.path().extension().is_some_and(|ext| ext == "json")).collect();
        assert_eq!(files.len(), MAX_EVENTS);
        assert_eq!(fs::read_to_string(root.join("diagnostics/desktop-spool/drops.count")).unwrap(), "4");
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
}
