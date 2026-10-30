# Diagnostic storage measurement v1

These provider-free probes use temporary SQLite databases and production
middleware, writers, retention, queries and export code. Reports record runtime
versions, source hashes, limits and raw samples. They measure local file lengths
and request costs; installation-wide disk certification remains in root TODO.

## Backend queries and writer

```bash
npm run bench:diagnostics -- --samples 100 --output /tmp/diagnostic-benchmark.json
```

The fixture inserts 12,000 synthetic events (10,000 retained), 1,000 trace
projections and 1,000 request/operation links. Each case has five warmups and
100 samples. HTTP controls alternate order and retain signed paired deltas.
The fixed TestClient route excludes real network, providers, OCR and UI.
Paced batches include DTO construction and writer drain; enqueue timing alone
does not include disk commit. Refused exports remain explicit failures.

| Case | Initial P95 ms | With quota admission P95 ms |
| --- | ---: | ---: |
| Fixed route without diagnostics | 0.241 | 0.243 |
| Route with running writer | 0.292 | 0.315 |
| Event page, 100 rows | 1.608 | 1.670 |
| Event operation filter | 15.964 | 16.088 |
| Scoped export | 16.822 | 16.956 |

[Initial raw samples](diagnostic-local-baseline-v1.json) and
[quota-admission samples](diagnostic-quota-admission-v1.json) bind different source
versions. Their independent percentiles do not establish a causal overhead delta.
The quota run's paced 100-event batch P95 is 27.928 ms. Its single full export
is 297.3 ms / 19,843,076 bytes, not a P95 measurement.

Pinned readers can prevent WAL truncation. The initial fixture grew WAL to
23,018,472 bytes with 500 small events; releasing the reader allowed maintenance
to reclaim it. The probe's own 64 MiB stop is not runtime enforcement. Quota
regressions use a separate 2 MiB envelope to verify refusal and later recovery.

## Legacy recovery

```bash
UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run --directory services/ai python -m tests.diagnostic_recovery_probe
```

The [recovery fixture](diagnostic-legacy-recovery-v1.json) uses a 144 MiB freelist
against a 128 MiB ordinary envelope and a 512 MiB extra recovery allowance.
It checks event retention, integrity and resumed admission. Elapsed startup /
drain / close and file lengths are observations, not latency or peak-space gates.
`tests.test_diagnostic_recovery` covers reader/space/deadline refusal and process
exit around deletion commit and VACUUM. Recovery rules are defined in
[Diagnostic storage policy](../diagnostic-storage-policy.md).

## Combined installation pressure

```bash
cargo test --manifest-path apps/desktop/src-tauri/Cargo.toml --lib --no-run
# Use the library-test executable printed by Cargo:
UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run --directory services/ai python -m tests.diagnostic_installation_probe --native-test-binary /absolute/path/to/library-test-executable
```

The probe runs production Python event/index writers and the spool consumer
alongside a compiled Rust spool writer. It starts with 60 MiB event and 28 MiB
index freelists plus 256 valid 16 KiB native records. Pinned readers sustain WAL
pressure while native, event and index writers attempt bounded loads. Both DB
quota refusals must occur; after reader release, maintenance and integrity checks
must succeed. Missing index source traces are intentional storage-pressure data.

[Installation samples](diagnostic-installation-v1.json) and
[counter-journal integration samples](diagnostic-journal-installation-v1.json)
record hashes, refusals and scan gaps. Normal envelopes total 196 MiB
(128 + 64 + 4); that sum is not atomic installation-wide enforcement. External
files, filesystem allocation and the extra recovery workspace remain outside it.
Recovery owners share `recovery.quota-lock`; ordinary per-DB writes remain
independent. Native UI, Vault and other platforms need separate acceptance.
