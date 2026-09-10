# Native Tauri WebView timeline rendering

An opt-in Cargo example hosts a visible Tauri WebView on macOS, using this
repository's Tauri dependency and a loopback-only benchmark URL. It does not run
production app setup, sidecar, Stronghold/Vault or business workflows. The host
accepts only HTTP on 127.0.0.1 and has its own window label/identifier. A random
per-run URL serves the synthetic page and receives a bounded timing report; the
runner terminates its own child and closes the server after completion.

Both the existing Chromium probe and native runner now call the same extracted
`installSyntheticFetch` and `measureTimeline` functions. They load the real
production React DiagnosticTimeline and strict decoder, preserving all row-count,
500-row cap, browser-error and timing assertions. This is actual native WebKit
rendering, not Playwright's emulated WebKit. The recorded user agent is
AppleWebKit/605.1.15; OS/architecture come from the host, not the compatibility
user-agent platform text. Requested window size is 1280×900; actual content
viewport is 1280×868. The timeline panel remains 560×720.

Each population has three warmups and 30 samples: mount 100 rows, append to 500,
expand an event and unmount. The rich population fills all five nested event
sections and the 4096-character bounded label; each page is up to 725,309 bytes.
Every run verifies document visibility. Timings include layout plus two animation
boundaries, not GPU completion. Native shell startup, production app shell/sidecar,
provider/network work and all-schema-combination extremes remain outside scope.

| Profile / phase | P50 ms | P95 ms | Max ms | Budget ms |
| --- | ---: | ---: | ---: | ---: |
| Small / mount | 50 | 52 | 52 | 150 |
| Small / last append | 50 | 52 | 52 | 150 |
| Small / expand | 33 | 35 | 35 | 100 |
| Small / unmount | 33 | 34 | 35 | 100 |
| Rich / mount | 50 | 51 | 51 | 150 |
| Rich / last append | 50 | 51 | 51 | 150 |
| Rich / expand | 32 | 33 | 34 | 100 |
| Rich / unmount | 33 | 35 | 35 | 100 |

All unchanged gates passed. Neither population is substituted for the unresolved
native spool I/O budget. No production runtime code or durability was changed.

```sh
cargo build --manifest-path apps/desktop/src-tauri/Cargo.toml --example diagnostic_render
node apps/web/tests/diagnostic-native-render-benchmark.mjs /tmp/diagnostic-native-render-small.json
node apps/web/tests/diagnostic-native-render-benchmark.mjs /tmp/diagnostic-native-render-rich.json --rich
```

Raw [small](diagnostic-native-render-small-v1.json) and
[rich](diagnostic-native-render-rich-v1.json) reports include all samples, actual
viewport, user agent, visibility, source bundle and native binary digests.
Build log: `/tmp/diagnostic-native-render-build.log`; execution logs:
`/tmp/diagnostic-native-render-small.log`, `/tmp/diagnostic-native-render-rich.log`.
Chromium small/rich populations are rerun after extracting the shared functions,
with logs `/tmp/diagnostic-render-shared-small.log` and
`/tmp/diagnostic-render-shared-rich.log`; prior Chromium reports remain archived.
