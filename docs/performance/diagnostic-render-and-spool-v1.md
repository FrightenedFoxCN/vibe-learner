# Diagnostic collector, rendering and native spool v1

These provider-free probes isolate collection, rendering and durable spool I/O.
Each uses production code with synthetic bounded fixtures and records source
hashes, environment and raw observations. Their scopes and timing populations
must remain separate from full application or cross-platform acceptance.

## Chromium collector

```bash
node apps/web/tests/diagnostic-collector-benchmark.mjs /tmp/diagnostic-collector.json
```

The probe bundles `apps/web/lib/diagnostics.ts` unchanged. After 1,000 warmups,
60 samples each create 100 request pairs / 200 events in saturated 1,000-entry
history and pending rings. It also measures snapshot copies and 30 mock-fetch
flushes of 1,000 events. Retention, overflow drops and uploaded counts are asserted.
The synchronous 200-event burst gate is P95 ≤16.7 ms; the
[reference P95](diagnostic-chromium-collector-v1.json) is 1.400 ms. Mock flushes
include JSON work and exclude network. This is not a complete UI frame budget.

## React timeline

```bash
node apps/web/tests/diagnostic-render-benchmark.mjs /tmp/diagnostic-render-small.json
node apps/web/tests/diagnostic-render-benchmark.mjs /tmp/diagnostic-render-rich.json --rich
```

The production `DiagnosticTimeline` and strict decoder run in a 560×720 scroll
container. Each population has three warmups and 30 samples: mount 100 rows,
append to the 500-row cap, expand one event, unmount. Timing includes layout and
two animation boundaries, providing a paint opportunity rather than GPU completion.
The rich fixture fills all five nested event sections and one 4,096-character
fallback label; its largest 100-event response is 725,309 bytes. This is decoder
stress data, not a registered tool or all possible schema combinations.

| Phase | P95 budget ms | Chromium small P95 ms | Chromium rich P95 ms | Native small P95 ms | Native rich P95 ms |
| --- | ---: | ---: | ---: | ---: | ---: |
| Mount | 150 | 51.0 | 50.5 | 52 | 51 |
| Last append | 150 | 50.6 | 50.7 | 52 | 51 |
| Expand | 100 | 33.2 | 30.9 | 35 | 33 |
| Unmount | 100 | 34.1 | 34.0 | 34 | 35 |

Raw reports: [Chromium small](diagnostic-react-render-v1.json),
[Chromium rich](diagnostic-render-rich-v1.json),
[native small](diagnostic-native-render-small-v1.json),
[native rich](diagnostic-native-render-rich-v1.json).

The native runner hosts the same probe in an actual visible Tauri WebView on
loopback HTTP. The local macOS reference viewport is 1280×868. It excludes the
production app shell, sidecar and Vault, and checks visibility and browser errors.
Both runners share `installSyntheticFetch` and `measureTimeline` assertions.

```bash
cargo build --manifest-path apps/desktop/src-tauri/Cargo.toml --example diagnostic_render
node apps/web/tests/diagnostic-native-render-benchmark.mjs /tmp/diagnostic-native-render-small.json
node apps/web/tests/diagnostic-native-render-benchmark.mjs /tmp/diagnostic-native-render-rich.json --rich
```

## Native spool

```bash
DIAGNOSTIC_SPOOL_BENCH_OUTPUT=/tmp/diagnostic-native-spool.json cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib spool_performance_probe -- --ignored
DIAGNOSTIC_SPOOL_BENCH_OUTPUT=/tmp/diagnostic-native-spool-release.json cargo test --release --manifest-path apps/desktop/src-tauri/Cargo.toml --lib spool_performance_probe -- --ignored
```

The real `DesktopDiagnostics.emit` includes lock admission, counter recovery,
scan/sort, durable eviction, counter checkpoint and event publication. Three
warmups precede 30 samples in sparse, saturated (256-event) and contended cases.
Successful emit P95 must be ≤25 ms; contended refusal P95 must be ≤100 ms, allowing
headroom above the 50 ms lock deadline. Reports assert retention, eviction counts,
contention refusals and recovery after releasing the lock; gate failure exits
nonzero after writing the report. These are local regression gates, not hard
filesystem latency bounds or cold migration certification.

| Implementation / build | Sparse P95 ms | Saturated P95 ms | Contended P95 ms | Gate |
| --- | ---: | ---: | ---: | --- |
| Rename counter / development | 10.01 | 25.21 | 50.99 | Fail |
| Rename counter / optimized | 9.06 | 25.06 | 51.80 | Fail |
| Alternating counter / development | 9.00 | 20.03 | 51.76 | Pass |
| Alternating counter / optimized | 9.97 | 20.07 | 51.83 | Pass |

The current [alternating-slot counter](../diagnostic-native-counter.md) preserves
locking, retention and publication barriers. Raw reports retain both original
[development](diagnostic-native-spool-v1.json) /
[optimized](diagnostic-native-spool-release-v1.json) failures and integrated
[development](diagnostic-native-journal-dev-v1.json) /
[optimized](diagnostic-native-journal-release-v1.json) results. Do not sum stage
percentiles into a total percentile or relax durability to meet the timing gate.
