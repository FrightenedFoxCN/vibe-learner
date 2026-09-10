# Alternating native counter checkpoint prototype

The native full-ring gate still fails in development and optimized builds. This
**test-only** module evaluates replacing the per-eviction counter file rename
checkpoint with two alternating fixed-size slots. Production `DesktopDiagnostics`
does not call it; `sha2` is only a dev dependency, using the already locked version.
No retention, event publication, lock or durability behavior changed in the app.

Each slot contains a version prefix, 20 decimal count digits and SHA-256 integrity
checksum. Load selects the greatest valid slot/legacy lower bound. Checkpoint
rejects decreases and overwrites the older/invalid slot while preserving the other
one. Every update calls `sync_all`; newly created slots additionally sync their
parent directory. Existing fixed-name inode updates avoid repeated rename/directory
publication costs. Readers are bounded to record-size+1 and reject malformed,
oversized, non-regular and symlink paths. Checksums detect damage; they do not
provide authentication or a universal hardware-failure guarantee.

Five tests pass, covering exhaustive byte-prefix torn overwrites/truncations,
every-byte bit damage, supplied legacy lower bounds, damaged-slot repair, decrease
rejection, u64 maximum, loss of both slots without a valid baseline, symlink
rejection and a real subprocess exiting after synchronizing a partial overwrite.
The parent recovers the untouched prior checkpoint and successfully continues.
One of the five is the subprocess entry point; this is not five independent crash
scenarios. Simulated bytes/process exit do not prove actual power-loss behavior.

Thirty alternating pairs follow three warmups. The control writes/syncs a new
pending counter, renames and syncs its directory. The candidate updates/syncs an
existing slot. Both results are independently read back; the candidate check does
not use a supplied legacy value that could mask a missing write.

| Checkpoint population | P50 ms | P95 ms | Max ms |
| --- | ---: | ---: | ---: |
| Rename checkpoint | 7.69 | 8.41 | 8.98 |
| Alternating slots | 3.95 | 4.12 | 4.45 |
| Signed paired slots − rename | -3.73 | -2.09 | -1.97 |

This supports further integration work, not closure of the 25 ms full-spool gate.
The measurements exclude scan, lock, eviction barriers, event commit and complete
spool recovery. Creation/migration costs are outside the warmed sample population.
Before adoption, integrate actual legacy `drops.count`/`drops.pending` recovery,
make older binaries reject a newer checkpoint format instead of reading a stale
legacy count, preserve the existing interprocess lock and publish failure/gap
counts. Then validate migration interruptions and full spool tests and timings.
The prototype's separate `drops.slot-*` filenames are not a final migration format.

```sh
cargo test --offline --manifest-path apps/desktop/src-tauri/Cargo.toml --lib counter_prototype
DIAGNOSTIC_COUNTER_BENCH_OUTPUT=/tmp/diagnostic-counter-prototype.json cargo test --offline --manifest-path apps/desktop/src-tauri/Cargo.toml --lib checkpoint_performance_probe -- --ignored
```

[Raw pairs and prototype digest](diagnostic-counter-prototype-v1.json) retain every
observation. Logs: `/tmp/diagnostic-counter-prototype-tests.log`,
`/tmp/diagnostic-counter-prototype-bench.log`,
`/tmp/diagnostic-counter-all-native-tests.log`.

The complete ordinary native suite passed 16 tests in 4.63 seconds, with five
opt-in probes ignored.
