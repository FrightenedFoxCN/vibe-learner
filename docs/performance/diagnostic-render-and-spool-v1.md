# Debug rendering and native spool measurements

Local macOS ARM64 measurements on 2026-09-10 complement the collector and backend
reports. Raw samples include failures; these measurements do not certify other
platforms, complete application workflows or independent quality review.

## Production React timeline

The opt-in probe bundles the actual `DiagnosticTimeline`, query decoder and React
production runtime. It mounts the timeline in a 560×720 scroll container, receives
100 synthetic transport events per page, appends up to 500 rows, expands a row,
and unmounts. The server keeps advertising more pages so the probe verifies the
UI's own 500-row cap. Three warmups precede 30 samples for each operation.
Every sample includes layout and two animation frame boundaries after the expected
DOM state; these provide a paint opportunity, not a GPU-completion measurement.

| Operation | P50 (ms) | P95 (ms) | Predeclared P95 budget (ms) |
| --- | ---: | ---: | ---: |
| Mount and display first 100 rows | 50.0 | 51.0 | 150 |
| Append final page to reach 500 rows | 50.0 | 50.6 | 150 |
| Expand one row at capacity | 32.6 | 33.2 | 100 |
| Unmount 500 rows | 33.3 | 34.1 | 100 |

All four local gates passed. Budgets leave headroom within a 200 ms interactive
response target. Timings include frame waiting and strict decoding, not just React
CPU time; they exclude backend/network, Next shell, native WebView and GPU finish.
The fixture represents normal transport rows, not maximum nested Harness records.
Initial harness runs failed because a standalone browser bundle lacked the Next
public environment substitution; the final probe explicitly supplies its isolated
base URL and fails on browser runtime errors. No production code was changed.

```sh
node apps/web/tests/diagnostic-render-benchmark.mjs /tmp/diagnostic-react-render.json
```

[Raw browser report](diagnostic-react-render-v1.json) includes all samples, browser
version, bundled inputs and bundle digest. Log: `/tmp/diagnostic-react-render.log`.

## Native synchronous spool

The actual Rust `DesktopDiagnostics.emit` executes file-lock admission, directory
scan, record write/sync and rename/sync. Sparse-ring measurements have 4–33 files;
the saturated ring contains 256 events and persists one eviction per emission.
A separately opened lock descriptor holds the same lock throughout the contention
case. All 33 contended emissions are counted as failures, and a subsequent emission
succeeds after release. Three warmups precede 30 measurements per case.

| Operation | P50 (ms) | P95 (ms) | Predeclared P95 budget (ms) | Result |
| --- | ---: | ---: | ---: | --- |
| Sparse-ring emit | 8.20 | 10.01 | 25 | Pass |
| Saturated-ring emit | 23.98 | 25.21 | 25 | **Fail** |
| Contended emit | 50.61 | 50.99 | 100 | Pass |

The successful-emit budget limits three startup events to a nominal 75 ms
contribution. The contention budget allows scheduling headroom above the existing
50 ms lock deadline. Neither is a hard filesystem latency bound. Saturated emission
exceeded its gate; the overall report remains failed. Its path includes durable
deletion and counter checkpoints as well as the new event. No sync was removed,
budget increased or passing rerun substituted. Further investigation is required
before closing native overhead acceptance. The probe excludes sidecar consumption
and native WebView interaction, and uses the normal development profile.

```sh
DIAGNOSTIC_SPOOL_BENCH_OUTPUT=/tmp/diagnostic-native-spool.json cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib spool_performance_probe -- --ignored
```

The command exits nonzero when a budget is exceeded, after saving its report and
cleaning temporary files. [Raw native report](diagnostic-native-spool-v1.json)
retains the failed sample set, source digest and compiler version. Log:
`/tmp/diagnostic-native-spool.log`. The benchmark is opt-in, separate from ordinary
regression tests and user storage.
All 11 ordinary native library tests passed in 4.65 seconds after adding the probe;
the three opt-in timing probes remain skipped by that ordinary test command.
