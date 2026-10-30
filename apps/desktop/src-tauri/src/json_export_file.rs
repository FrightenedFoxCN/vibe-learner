// Same-directory staging; never open/truncate or pre-delete the destination.
// Std-only so the real filesystem semantics can also be tested with rustc.
use std::fs::{self, File, OpenOptions};
use std::io::{self, Write};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::{SystemTime, UNIX_EPOCH};

static UNIQUE: AtomicU64 = AtomicU64::new(0);

fn temporary_name() -> String {
    format!(
        ".vibe-export-{:x}-{:x}-{:x}.tmp",
        std::process::id(),
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_nanos(),
        UNIQUE.fetch_add(1, Ordering::Relaxed)
    )
}

struct StagedFile {
    // Close the handle before cleanup/rename, including on Windows.
    file: Option<File>,
    path: PathBuf,
    published: bool,
}

impl StagedFile {
    fn create(parent: &Path, name: impl Fn() -> String) -> io::Result<Self> {
        for _ in 0..16 {
            let path = parent.join(name());
            let mut options = OpenOptions::new();
            options.write(true).create_new(true);
            #[cfg(unix)]
            {
                use std::os::unix::fs::OpenOptionsExt;
                options.mode(0o600);
            }
            match options.open(&path) {
                Ok(file) => {
                    return Ok(Self {
                        file: Some(file),
                        path,
                        published: false,
                    })
                }
                Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
                Err(error) => return Err(error),
            }
        }
        Err(io::Error::new(
            io::ErrorKind::AlreadyExists,
            "export_temp_collision",
        ))
    }
}

impl Drop for StagedFile {
    fn drop(&mut self) {
        drop(self.file.take());
        // Best effort: failure/crash can leave this operation's temp file behind.
        // Never sweep other files or remove/restore the selected destination.
        if !self.published {
            let _ = fs::remove_file(&self.path);
        }
    }
}

pub(super) fn replace(path: &Path, contents: &[u8]) -> io::Result<()> {
    replace_with(path, contents, |file, bytes| {
        file.write_all(bytes)?;
        file.sync_all()
    })
}

fn replace_with(
    path: &Path,
    contents: &[u8],
    stage_and_sync: impl FnOnce(&mut File, &[u8]) -> io::Result<()>,
) -> io::Result<()> {
    // Do not follow a selected symlink or replace a directory/device.
    match fs::symlink_metadata(path) {
        Ok(metadata) if !metadata.is_file() => {
            return Err(io::Error::new(
                io::ErrorKind::InvalidInput,
                "export_target_type",
            ));
        }
        Ok(_) => {}
        Err(error) if error.kind() == io::ErrorKind::NotFound => {}
        Err(error) => return Err(error),
    }
    let parent = path
        .parent()
        .filter(|p| !p.as_os_str().is_empty())
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "export_parent_missing"))?;
    let mut staged = StagedFile::create(parent, temporary_name)?;
    stage_and_sync(staged.file.as_mut().unwrap(), contents)?;
    drop(staged.file.take());
    // std uses the OS rename/replace primitive. Never emulate overwrite by unlinking.
    fs::rename(&staged.path, path)?;
    staged.published = true;
    // Replacement has committed. A directory-flush failure cannot safely be rolled
    // back or reported as a pre-commit write failure. Power-loss durability varies.
    #[cfg(unix)]
    if let Ok(directory) = File::open(parent) {
        let _ = directory.sync_all();
    }
    Ok(())
}
