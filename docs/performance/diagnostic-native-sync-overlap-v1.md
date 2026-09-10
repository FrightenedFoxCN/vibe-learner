# Native pending-file synchronization experiment

The full native spool's original saturated P95 of 25.21 ms exceeds its 25 ms
budget. Prior stage measurements identified filesystem synchronization as the
main cost. This test-only experiment checks whether overlapping two independent
pending-file `sync_all` calls reduces that cost before attempting a runtime
protocol change.

Thirty pairs follow three warmup pairs, alternating sequential/overlap order.
Both modes create/write the same synthetic counter and 512-byte event files and
retain three directory synchronization barriers: before writing pending files,
after publishing the counter, and after publishing the event. Both pending files
are synced before publishing either file. The overlap side uses a scoped thread,
including thread creation/join in its timing. Full file bytes are read back after
each sample. This is a synchronization microexperiment, not actual native emit:
it excludes locking, retention scans, serialization and real crash recovery.

| Population | P50 ms | P95 ms | Max ms |
| --- | ---: | ---: | ---: |
| Sequential sync | 16.71 | 17.88 | 18.59 |
| Overlapping sync | 15.72 | 18.61 | 18.61 |
| Signed paired overlap − sequential | -1.81 | 1.97 | 2.64 |

Although the median is lower, overlapping sync does not improve P95. This is
insufficient evidence to change the production protocol, so it was not adopted.
The production writer retains its original serial ordering and all durability
barriers. Original full-spool failures remain open; this experiment neither
widens the budget nor certifies a crash-safe reordered implementation. No claims
are made about other filesystems or platforms.

```sh
DIAGNOSTIC_SYNC_BENCH_OUTPUT=/tmp/diagnostic-native-sync-overlap.json cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib pending_sync_overlap_probe -- --ignored
```

[Raw paired report](diagnostic-native-sync-overlap-v1.json) retains all observations.
Experiment log: `/tmp/diagnostic-native-sync-overlap.log`.
Ordinary native regression log: `/tmp/diagnostic-native-overlap-tests.log`.

All 11 ordinary native tests passed in 4.53 seconds; four opt-in probes were
ignored by that normal run.
