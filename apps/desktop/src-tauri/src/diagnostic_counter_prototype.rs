//! Test-only alternating checkpoint candidate. Not used by the production writer.
use super::{identity, sync_directory};
use sha2::{Digest, Sha256};
use std::fs::{self, File, OpenOptions};
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

struct Journal {
    paths: [PathBuf; 2],
    slots: [Option<u64>; 2],
    count: u64,
    damaged: usize,
}
impl Journal {
    // Caller owns the existing installation spool lock throughout load/write.
    fn load(root: &Path, legacy: Option<u64>) -> io::Result<Self> {
        let paths = [root.join("drops.slot-0"), root.join("drops.slot-1")];
        let mut slots = [None, None];
        let mut damaged = 0;
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
                    slots[index] = decode(&bytes);
                    if slots[index].is_none() {
                        damaged += 1;
                    }
                }
                Err(e) if e.kind() == io::ErrorKind::NotFound => {}
                Err(e) => return Err(e),
            }
        }
        let count = slots.iter().copied().flatten().chain(legacy).max();
        if count.is_none() && damaged > 0 {
            return Err(io::Error::other("counter_no_valid_checkpoint"));
        }
        Ok(Self {
            paths,
            slots,
            count: count.unwrap_or(0),
            damaged,
        })
    }
    fn checkpoint(&mut self, count: u64) -> io::Result<()> {
        if count < self.count {
            return Err(io::Error::other("counter_regression"));
        }
        let index = if self.slots[0] <= self.slots[1] { 0 } else { 1 };
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
        file.write_all(&encode(count))?;
        file.set_len(SIZE as u64)?;
        file.sync_all()?;
        if created {
            sync_directory(self.paths[index].parent().unwrap())?;
        }
        self.slots[index] = Some(count);
        self.count = count;
        Ok(())
    }
}

#[test]
fn torn_overwrites_and_truncations_keep_other_checkpoint() {
    let root = std::env::temp_dir().join(identity());
    fs::create_dir_all(&root).unwrap();
    let mut journal = Journal::load(&root, Some(97)).unwrap();
    journal.checkpoint(98).unwrap();
    journal.checkpoint(99).unwrap();
    let old = encode(98);
    let next = encode(100);
    for cut in 0..=SIZE {
        let mut torn = old.clone();
        torn[..cut].copy_from_slice(&next[..cut]);
        fs::write(&journal.paths[0], &torn).unwrap();
        let recovered = Journal::load(&root, Some(97)).unwrap();
        assert!(matches!(recovered.count, 99 | 100));
        fs::write(&journal.paths[0], &next[..cut]).unwrap();
        assert_eq!(
            Journal::load(&root, Some(97)).unwrap().count,
            if cut == SIZE { 100 } else { 99 }
        );
    }
    for offset in 0..SIZE {
        let mut damaged = next.clone();
        damaged[offset] ^= 1;
        fs::write(&journal.paths[0], damaged).unwrap();
        let recovered = Journal::load(&root, Some(97)).unwrap();
        assert_eq!(recovered.count, 99);
        assert_eq!(recovered.damaged, 1);
    }
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn migration_bounds_and_repair() {
    let root = std::env::temp_dir().join(identity());
    fs::create_dir_all(&root).unwrap();
    let mut journal = Journal::load(&root, Some(7)).unwrap();
    journal.checkpoint(8).unwrap();
    journal.checkpoint(9).unwrap();
    assert!(journal.checkpoint(8).is_err());
    fs::write(&journal.paths[0], b"broken").unwrap();
    let mut recovered = Journal::load(&root, Some(7)).unwrap();
    assert_eq!(recovered.count, 9);
    recovered.checkpoint(10).unwrap();
    assert_eq!(Journal::load(&root, Some(7)).unwrap().count, 10);
    recovered.checkpoint(u64::MAX).unwrap();
    assert_eq!(Journal::load(&root, Some(7)).unwrap().count, u64::MAX);
    fs::write(&journal.paths[0], b"broken").unwrap();
    fs::write(&journal.paths[1], b"broken").unwrap();
    assert!(Journal::load(&root, None).is_err());
    fs::remove_dir_all(root).unwrap();
}

#[test]
fn checkpoint_child() {
    let Ok(root) = std::env::var("DIAGNOSTIC_COUNTER_CHILD_ROOT") else {
        return;
    };
    let root = Path::new(&root);
    let mut file = OpenOptions::new()
        .write(true)
        .open(root.join("drops.slot-0"))
        .unwrap();
    file.write_all(&encode(100)[..PREFIX.len() + 20]).unwrap();
    file.sync_all().unwrap();
    std::process::exit(73);
}

#[test]
fn process_exit_mid_overwrite_recovers_previous_and_can_continue() {
    let root = std::env::temp_dir().join(identity());
    fs::create_dir_all(&root).unwrap();
    let mut journal = Journal::load(&root, Some(97)).unwrap();
    journal.checkpoint(98).unwrap();
    journal.checkpoint(99).unwrap();
    let status = std::process::Command::new(std::env::current_exe().unwrap())
        .args([
            "--exact",
            "diagnostics::counter_prototype::checkpoint_child",
            "--nocapture",
        ])
        .env("DIAGNOSTIC_COUNTER_CHILD_ROOT", &root)
        .status()
        .unwrap();
    assert_eq!(status.code(), Some(73));
    let mut recovered = Journal::load(&root, Some(97)).unwrap();
    assert_eq!(recovered.count, 99);
    assert_eq!(recovered.damaged, 1);
    recovered.checkpoint(100).unwrap();
    assert_eq!(Journal::load(&root, Some(97)).unwrap().count, 100);
    fs::remove_dir_all(root).unwrap();
}

#[test]
#[ignore = "opt-in counter checkpoint I/O comparison"]
fn checkpoint_performance_probe() {
    let output = std::env::var("DIAGNOSTIC_COUNTER_BENCH_OUTPUT").unwrap();
    let root = std::env::temp_dir().join(identity());
    fs::create_dir_all(&root).unwrap();
    let mut journal = Journal::load(&root, Some(0)).unwrap();
    let mut pairs = Vec::new();
    for index in 0..33u64 {
        let order = if index % 2 == 0 {
            [false, true]
        } else {
            [true, false]
        };
        let mut elapsed = [0.0; 2];
        for candidate in order {
            let start = std::time::Instant::now();
            if candidate {
                journal.checkpoint(index + 1).unwrap();
            } else {
                let pending = root.join("drops.pending");
                let mut file = File::create(&pending).unwrap();
                write!(file, "{}", index + 1).unwrap();
                file.sync_all().unwrap();
                drop(file);
                fs::rename(pending, root.join("drops.count")).unwrap();
                sync_directory(&root).unwrap();
            }
            elapsed[usize::from(candidate)] = start.elapsed().as_secs_f64() * 1000.0;
            if candidate {
                assert_eq!(Journal::load(&root, None).unwrap().count, index + 1);
            } else {
                assert_eq!(
                    fs::read_to_string(root.join("drops.count"))
                        .unwrap()
                        .parse::<u64>()
                        .unwrap(),
                    index + 1
                );
            }
        }
        if index >= 3 {
            pairs.push(serde_json::json!({"first":if order[0]{"slots"}else{"rename"},"rename_ms":elapsed[0],"slots_ms":elapsed[1],"delta_ms":elapsed[1]-elapsed[0]}));
        }
    }
    fs::write(output, serde_json::to_vec_pretty(&serde_json::json!({"schema_version":"counter-checkpoint-prototype-v1","warmup_pairs":3,"sample_pairs":30,"raw":pairs,"scope":"Checkpoint only; caller lock, event writes, eviction barriers and full spool recovery excluded. Production writer unchanged."})).unwrap()).unwrap();
    fs::remove_dir_all(root).unwrap();
}

#[cfg(unix)]
#[test]
fn symlink_slots_are_rejected_without_touching_target() {
    use std::os::unix::fs::symlink;
    let root = std::env::temp_dir().join(identity());
    fs::create_dir_all(&root).unwrap();
    let target = root.join("untouched");
    fs::write(&target, b"sentinel").unwrap();
    symlink(&target, root.join("drops.slot-0")).unwrap();
    assert!(Journal::load(&root, Some(9)).is_err());
    assert_eq!(fs::read(&target).unwrap(), b"sentinel");
    fs::remove_dir_all(root).unwrap();
}
