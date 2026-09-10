# Diagnostic quota admission measurement

This [100-sample raw report](diagnostic-quota-admission-v1.json) follows the
[original measurement baseline](diagnostic-local-baseline-v1.md). It records
current source hashes and the 128 MiB event / 64 MiB index admission envelopes.
The final run followed completion of browser acceptance; no deliberate parallel
benchmark/test workload was running. It remains a local measurement, not a
cross-platform or full-product gate.

| Case | P95 ms |
| --- | ---: |
| Fixed route baseline | 0.243 |
| Route with running writer | 0.315 |
| Paced 100-event batch including validation and writer drain | 27.928 |
| Event page | 1.670 |
| Operation filter | 16.088 |
| Scoped export | 16.956 |

Full export was a single 297.3 ms observation,
19,843,076 bytes. Paced workload recorded no dropped events
or read/write failures. Conservative reservations and process locking add
writer work; paired samples and all batch timings are retained for comparison,
without asserting a causal regression percentage across separate runs.

The benchmark's standard 128 MiB envelope does not need to reject its 500-event
pinned-reader workload. Separate quota regressions use a 2 MiB envelope to prove
refusal below the limit and recovery after reader release. Oversized staged
transactions, process-crash lock release and guarded vacuum also have direct
SQLite regression evidence. These tests do not certify desktop spool, legacy
oversize recovery, Windows behavior or a 200 MiB installation-wide quota.
