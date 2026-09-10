//! Versioned two-slot eviction checkpoint, used under the native spool lock.
use super::sync_directory;
use sha2::{Digest, Sha256};
use std::fs::OpenOptions;
use std::io::{self, Read, Seek, Write};
use std::path::{Path, PathBuf};

const PREFIX: &str = "diagnostic-counter-v1:";
const SIZE: usize = PREFIX.len() + 20 + 1 + 64 + 1;

fn encode(count: u64) -> Vec<u8> {
    let payload = format!("{PREFIX}{count:020}");
    format!("{payload}:{:x}\n", Sha256::digest(payload.as_bytes())).into_bytes()
}

fn decode(bytes: &[u8]) -> Option<u64> {
    if bytes.len() != SIZE {
        return None;
    }
    let count_end = PREFIX.len() + 20;
    if !bytes.starts_with(PREFIX.as_bytes()) || bytes[count_end] != b':' || bytes[SIZE - 1] != b'\n'
    {
        return None;
    }
    let digits = &bytes[PREFIX.len()..count_end];
    if !digits.iter().all(u8::is_ascii_digit) {
        return None;
    }
    let count = std::str::from_utf8(digits).ok()?.parse().ok()?;
    (encode(count) == bytes).then_some(count)
}

pub(super) struct Journal {
    paths: [PathBuf; 2],
    slots: [Option<u64>; 2],
    pub count: u64,
    pub damaged: usize,
    primary_legacy: bool,
}
impl Journal {
    // Caller owns the existing installation spool lock throughout load/write.
    pub fn load(root: &Path) -> io::Result<Self> {
        let paths = [root.join("drops.count"), root.join("drops.alternate")];
        let mut slots = [None, None];
        let mut damaged = 0;
        let mut primary_legacy = false;
        for index in 0..2 {
            let mut options = OpenOptions::new();
            options.read(true);
            #[cfg(unix)]
            {
                use std::os::unix::fs::OpenOptionsExt;
                options.custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK);
            }
            match options.open(&paths[index]) {
                Ok(file) => {
                    if !file.metadata()?.is_file() {
                        return Err(io::Error::other("counter_slot_type"));
                    }
                    let mut bytes = Vec::new();
                    file.take((SIZE + 1) as u64).read_to_end(&mut bytes)?;
                    if bytes.starts_with(b"diagnostic-counter-v")
                        && bytes.contains(&b':')
                        && !bytes.starts_with(PREFIX.as_bytes())
                    {
                        return Err(io::Error::other("counter_version_unsupported"));
                    }
                    slots[index] = decode(&bytes);
                    if index == 0
                        && slots[index].is_none()
                        && !bytes.is_empty()
                        && bytes.len() <= 20
                        && bytes.iter().all(u8::is_ascii_digit)
                    {
                        slots[index] = std::str::from_utf8(&bytes)
                            .ok()
                            .and_then(|s| s.parse().ok());
                        primary_legacy = slots[index].is_some();
                    }
                    if slots[index].is_none() {
                        damaged += 1;
                    }
                }
                Err(e) if e.kind() == io::ErrorKind::NotFound => {}
                Err(e) => return Err(e),
            }
        }
        let count = slots.iter().copied().flatten().max();
        if count.is_none() && damaged > 0 {
            return Err(io::Error::other("counter_no_valid_checkpoint"));
        }
        Ok(Self {
            paths,
            slots,
            count: count.unwrap_or(0),
            damaged,
            primary_legacy,
        })
    }
    pub fn needs_checkpoint(&self) -> bool {
        self.primary_legacy || self.slots[0].is_none() || self.damaged > 0
    }
    pub fn checkpoint(&mut self, count: u64) -> io::Result<()> {
        if count < self.count {
            return Err(io::Error::other("counter_regression"));
        }
        if self.primary_legacy {
            // Preserve the old durable count before changing its inode format.
            // Until primary conversion, the secondary never exceeds the legacy
            // value, so an older binary cannot silently read a stale baseline.
            if self.slots[1] < Some(self.count) {
                self.write_slot(1, self.count)?;
            }
            #[cfg(test)]
            if std::env::var("DIAGNOSTIC_COUNTER_EXIT_STAGE").as_deref() == Ok("migration_backup") {
                std::process::exit(74);
            }
            self.write_slot(0, count)?;
            self.primary_legacy = false;
        } else {
            let index = if self.slots[0].is_none() || self.slots[0] <= self.slots[1] {
                0
            } else {
                1
            };
            self.write_slot(index, count)?;
        }
        self.count = count;
        self.damaged = 0;
        Ok(())
    }
    fn write_slot(&mut self, index: usize, count: u64) -> io::Result<()> {
        let mut options = OpenOptions::new();
        options.write(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.custom_flags(libc::O_NOFOLLOW | libc::O_NONBLOCK);
        }
        let (mut file, created) = match options.open(&self.paths[index]) {
            Ok(file) => (file, false),
            Err(e) if e.kind() == io::ErrorKind::NotFound => {
                (options.create_new(true).open(&self.paths[index])?, true)
            }
            Err(e) => return Err(e),
        };
        if !file.metadata()?.is_file() {
            return Err(io::Error::other("counter_slot_type"));
        }
        file.rewind()?;
        #[cfg(test)]
        if std::env::var("DIAGNOSTIC_COUNTER_EXIT_STAGE").as_deref() == Ok("partial_slot") {
            file.write_all(&encode(count)[..PREFIX.len() + 20])?;
            file.sync_all()?;
            std::process::exit(75);
        }
        file.write_all(&encode(count))?;
        file.set_len(SIZE as u64)?;
        file.sync_all()?;
        if created {
            sync_directory(self.paths[index].parent().unwrap())?;
        }
        self.slots[index] = Some(count);
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::diagnostics::{identity, read_counter};
    use std::fs;
    fn root() -> PathBuf {
        let root = std::env::temp_dir().join(identity());
        fs::create_dir_all(&root).unwrap();
        root
    }
    #[test]
    fn legacy_migrates_and_old_reader_fails_closed() {
        let root = root();
        fs::write(root.join("drops.count"), "99").unwrap();
        let mut journal = Journal::load(&root).unwrap();
        assert_eq!(journal.count, 99);
        journal.checkpoint(100).unwrap();
        assert!(read_counter(&root.join("drops.count")).is_err());
        assert_eq!(
            decode(&fs::read(root.join("drops.alternate")).unwrap()),
            Some(99)
        );
        assert_eq!(Journal::load(&root).unwrap().count, 100);
        assert!(journal.checkpoint(99).is_err());
        journal.checkpoint(u64::MAX).unwrap();
        assert_eq!(Journal::load(&root).unwrap().count, u64::MAX);
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn all_migration_prefixes_keep_backup_without_inventing_counts() {
        let root = root();
        fs::write(root.join("drops.alternate"), encode(99)).unwrap();
        let next = encode(100);
        for cut in 0..=SIZE {
            let mut partial = b"99".to_vec();
            if cut > partial.len() {
                partial.resize(cut, 0);
            }
            partial[..cut].copy_from_slice(&next[..cut]);
            fs::write(root.join("drops.count"), &partial).unwrap();
            let journal = Journal::load(&root).unwrap();
            assert!(matches!(journal.count, 99 | 100));
            if cut > 0 {
                assert!(read_counter(&root.join("drops.count")).is_err());
            }
        }
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn torn_slots_repair_and_unknown_versions_stop_writes() {
        let root = root();
        fs::write(root.join("drops.count"), encode(99)).unwrap();
        let previous = encode(98);
        let next = encode(100);
        for cut in 0..=SIZE {
            let mut torn = previous.clone();
            torn[..cut].copy_from_slice(&next[..cut]);
            fs::write(root.join("drops.alternate"), torn).unwrap();
            assert!(matches!(Journal::load(&root).unwrap().count, 99 | 100));
            fs::write(root.join("drops.alternate"), &next[..cut]).unwrap();
            assert_eq!(
                Journal::load(&root).unwrap().count,
                if cut == SIZE { 100 } else { 99 }
            );
        }
        fs::write(root.join("drops.alternate"), b"torn").unwrap();
        let mut journal = Journal::load(&root).unwrap();
        assert_eq!(journal.damaged, 1);
        journal.checkpoint(100).unwrap();
        assert_eq!(Journal::load(&root).unwrap().count, 100);
        fs::write(
            root.join("drops.count"),
            b"diagnostic-counter-v2:unsupported",
        )
        .unwrap();
        assert!(Journal::load(&root).is_err());
        fs::write(root.join("drops.count"), b"torn").unwrap();
        fs::write(root.join("drops.alternate"), b"torn").unwrap();
        assert!(Journal::load(&root).is_err());
        fs::remove_dir_all(root).unwrap();
    }
    #[test]
    fn integration_child() {
        let Ok(path) = std::env::var("DIAGNOSTIC_COUNTER_INTEGRATION_ROOT") else {
            return;
        };
        let mut journal = Journal::load(Path::new(&path)).unwrap();
        journal.checkpoint(100).unwrap();
        panic!("expected forced exit");
    }
    #[test]
    fn process_crashes_at_migration_and_existing_slot_preserve_durable_baseline() {
        for (stage, exit) in [("migration_backup", 74), ("partial_slot", 75)] {
            let root = root();
            if stage == "migration_backup" {
                fs::write(root.join("drops.count"), b"99").unwrap();
            } else {
                fs::write(root.join("drops.count"), encode(99)).unwrap();
                fs::write(root.join("drops.alternate"), encode(98)).unwrap();
            }
            let status = std::process::Command::new(std::env::current_exe().unwrap())
                .args([
                    "--exact",
                    "diagnostics::counter::tests::integration_child",
                    "--nocapture",
                ])
                .env("DIAGNOSTIC_COUNTER_INTEGRATION_ROOT", &root)
                .env("DIAGNOSTIC_COUNTER_EXIT_STAGE", stage)
                .status()
                .unwrap();
            assert_eq!(status.code(), Some(exit));
            let mut recovered = Journal::load(&root).unwrap();
            assert_eq!(recovered.count, 99);
            recovered.checkpoint(100).unwrap();
            assert_eq!(Journal::load(&root).unwrap().count, 100);
            assert!(read_counter(&root.join("drops.count")).is_err());
            fs::remove_dir_all(root).unwrap();
        }
    }
    #[cfg(unix)]
    #[test]
    fn symlink_and_special_slots_are_not_followed() {
        use std::os::unix::fs::symlink;
        let root = root();
        let target = root.join("untouched");
        fs::write(&target, b"sentinel").unwrap();
        symlink(&target, root.join("drops.count")).unwrap();
        assert!(Journal::load(&root).is_err());
        assert_eq!(fs::read(&target).unwrap(), b"sentinel");
        fs::remove_file(root.join("drops.count")).unwrap();
        fs::create_dir(root.join("drops.count")).unwrap();
        assert!(Journal::load(&root).is_err());
        fs::remove_dir_all(root).unwrap();
    }
}
