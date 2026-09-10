# Optimized native spool measurement

The same actual `DesktopDiagnostics.emit` probe was built and executed with
`cargo test --release`. The report confirms `debug_assertions: false`. No writer
algorithm, retention limit, durability barrier or budget changed. Three warmups
precede 30 samples for sparse, saturated and contended cases. The protocol and
original development failure remain described in the
[original report](diagnostic-render-and-spool-v1.md).

| Operation | P50 ms | P95 ms | Max ms | Budget ms | Result |
| --- | ---: | ---: | ---: | ---: | --- |
| Sparse | 8.01 | 9.06 | 9.14 | 25 | Pass |
| Saturated | 21.84 | 25.06 | 27.15 | 25 | Fail |
| Contended | 51.20 | 51.80 | 51.88 | 100 | Pass |

The saturated gate still fails. The lower median does not close the original
25.21 ms development failure, and the 0.06 ms excess is not rounded into success.
The probe verifies 256 retained events, durable eviction count, 33 observed
contention refusals and recovery after releasing the lock. Native I/O remains
open in both measured build profiles. A compiler profile switch alone is not a
supported fix; no development optimization setting was changed.

```sh
DIAGNOSTIC_SPOOL_BENCH_OUTPUT=/tmp/diagnostic-native-spool-release.json cargo test --release --manifest-path apps/desktop/src-tauri/Cargo.toml --lib spool_performance_probe -- --ignored
```

[Complete raw report](diagnostic-native-spool-release-v1.json) preserves all samples
and stages. Probe log: `/tmp/diagnostic-native-spool-release.log`. Ordinary optimized
native regression log: `/tmp/diagnostic-native-release-regression.log`.

A next implementation investigation should target the counter checkpoint, whose
current replacement requires both file and directory synchronization per eviction.
A possible fixed-size alternating-slot journal must prove checksum/torn-write
rejection, preservation of the previous durable lower bound, legacy counter and
pending-file migration, interprocess exclusion and failure accounting before it
can replace that protocol. This is an unimplemented candidate, not an approved
performance or crash-safety claim. Removing a durability barrier or evicting more
events merely to improve the percentile is not justified by this experiment.

All 11 ordinary optimized native tests passed in 4.51 seconds; four opt-in probes
were ignored by the normal regression command.
