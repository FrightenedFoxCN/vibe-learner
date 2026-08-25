# Desktop Cold-start Hotspots v1

## Conclusion

The current macOS ARM64 release DMG has a real desktop-sidecar cold-start
problem. Ten independent samples of the packaged sidecar all reached
`GET /health` successfully, but the median was **7.06 s** and the p95 was
**9.08 s**. This fails `PERF-002`: every one of ten fresh mock `/health`
processes must complete in under two seconds.

This is a sidecar-readiness result, not a full "window is interactive" result.
Because the Tauri application calls `build_desktop_state` synchronously from
its setup path and waits for sidecar health before managing state, this is a
blocking lower bound on the desktop application's visible ready path. WebView
creation, frontend hydration, and vault interaction are intentionally outside
the measured boundary and can only add time.

## Evidence

The raw machine-readable result is
[`performance-samples/desktop-sidecar-cold-start-macos-arm64-2026-08-25.json`](performance-samples/desktop-sidecar-cold-start-macos-arm64-2026-08-25.json).

| Metric | Result |
| --- | ---: |
| Samples / successful samples | 10 / 10 |
| Minimum | 6.65 s |
| Mean | 7.48 s |
| p50 | 7.06 s |
| p95 | 9.08 s |
| Maximum | 9.08 s |
| `PERF-002` threshold | every sample < 2.00 s |

Test host: macOS 26.6.2, Apple M4 (10 CPU cores), 16 GiB RAM, Node 26.7.0,
uv 0.12.3. The artifact was the 185 MB release DMG built on 2026-08-25 from
revision `0524bf9` with the current dirty worktree; its SHA-256 is
`c3967371f533f4c73aa16d083952088a1bf27d5864df00e8f584ff76d4ece0a1`.

Each sample mounted that DMG read-only, spawned its embedded
`vibe-learner-sidecar` as a fresh process, used a fresh temporary
SQLite/storage root, forced the mock planning provider, and stopped the
process after the first HTTP 200 from `/health`. The 200 ms probe cadence
matches the desktop shell, so it can add at most one probe interval to a
successful observation.

The sampler calls no OCR or model endpoint and no OnnxTR model directory was
present. It does not independently prove the absence of startup cost-map or
other outbound requests, which remains an explicit `PERF-002` verification
item. It also does not measure OCR or model inference, vault
initialization/unlock, Tauri/WebView creation, or frontend hydration.

## Observed hot path

1. `apps/desktop/src-tauri/src/lib.rs` starts the sidecar and synchronously
   waits for `/health` in `build_desktop_state`; that function is invoked from
   Tauri setup. The current timeout is 20 seconds, with 200 ms polling,
   300 ms connect timeout, and 500 ms read timeout. The polling is not the
   root cause of a 7–9 second delay, but it makes the wait user-visible before
   any later desktop state is available.
2. The packaged sidecar is a 180 MB PyInstaller **one-file** executable. Each
   cold process must unpack the archive to a temporary directory before Python
   can start. This is the leading packaging-level suspect; the benchmark was
   intentionally run from the final DMG so it includes that cost.
3. After bootstrap, `services/ai/app/sidecar.py` eagerly imports Uvicorn and
   `app.main` before the server can bind its health route. The PyInstaller spec
   also collects all `litellm` and `onnxtr` submodules even though the sampled
   process uses the mock provider and performs no OCR. This broad import and
   collection surface is the leading application-level suspect. The current
   samples demonstrate the end-to-end cost, but do not yet apportion exact
   milliseconds between unpacking, imports, database bootstrap, and route
   initialization.

## Priority actions

1. Complete `PERF-002` before changing the startup target: retain the ten
   fresh-process fixture, add phase timing (one-file extraction, Python import,
   database/bootstrap, and Uvicorn bind), make LiteLLM and OnnxTR truly lazy,
   and verify neither is in `sys.modules` after health readiness.
2. Evaluate a PyInstaller one-directory sidecar (or a separately signed native
   dependency layout) to remove one-file extraction from the critical path.
   This must be measured against the same final DMG fixture; it also provides a
   viable path to a Developer ID signing chain.
3. Consider allowing the native shell to show a deterministic "starting local
   service" state while waiting. This can improve perceived startup but must
   not claim API availability until health succeeds; it does not replace the
   readiness optimization above.

`PERF-002` remains open. This report deliberately makes no claim that the
desktop's total cold-start time is 7.06–9.08 seconds; it establishes that its
mandatory sidecar gate alone costs that much.

## Packaging validation and signing finding

The first ad-hoc signed DMG was structurally valid but its hardened runtime
rejected PyInstaller's extracted `libpython3.12.dylib` with a library-validation
Team-ID mismatch. The final preview configuration keeps ad-hoc signing but
disables hardened runtime, which permits the one-file sidecar to start; the
final DMG passed both `hdiutil verify` and
`codesign --verify --deep --strict` before sampling.

This is appropriate only for the documented preview artifact. A future
Developer ID/notarized distribution must sign the sidecar and all of its native
dependencies with one Developer ID team, then re-enable hardened runtime.
