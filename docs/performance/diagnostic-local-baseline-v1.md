# Diagnostic local measurement baseline v1

Recorded 2026-09-10 with 100 samples after five warmups per query/probe case.
The [raw report](diagnostic-local-baseline-v1.json) contains all timings,
source SHA-256 values, base Git revision, dependency/runtime versions and counts.
It is a measurement baseline, not a release gate or proof of full product/native
performance. No provider or network requests are made.

```bash
npm run bench:diagnostics -- --samples 100 --output /tmp/diagnostic-benchmark.json
```

The benchmark uses temporary SQLite databases and production middleware, writer,
retention, query and export implementations. It inserts 12,000 synthetic provider
attempt events (10,000 retained), 1,000 diagnostic trace projections and 1,000
request/operation links. The trace/operation IDs and metrics are explicitly
synthetic fixture data, not canonical runtime executions or adoption evidence.
Raw report output contains measurements and safe configuration, not their
content. `--events` and `--traces` can vary this fixture within bounded limits.

| Case | P50 ms | P95 ms |
| --- | ---: | ---: |
| In-process fixed HTTP route without diagnostic middleware | 0.197 | 0.241 |
| Same route with diagnostic writer running | 0.241 | 0.292 |
| Same route with full/stalled diagnostic queue | 0.236 | 0.292 |
| Event page, 100 rows | 1.509 | 1.608 |
| Event operation filter | 15.710 | 15.964 |
| Index page, 100 rows | 1.073 | 1.187 |
| Scoped snapshot export | 16.560 | 16.822 |

A single full snapshot export measured 302.4 ms and 19,843,076 bytes. It is not a
P95 measurement. The raw report records bounded refusal separately if a selected
fixture exceeds export limits; missing/refused output is never a zero-duration
success. Event/operation filtering is materially slower than unfiltered cursor
reads in this fixture, but stays below current query deadlines on this machine.

HTTP cases alternate execution order to reduce ordering bias. They share a
process and the enabled writer's background work; their signed paired deltas
are retained (negative deltas are not clamped). The case isolates a fixed async
health route through TestClient and real middleware. It does not measure network,
provider, OCR, frontend render, desktop or end-to-end product overhead. Paced
100-event batch timings include DTO construction and waiting for the real writer;
enqueue timings alone exclude DTO construction and disk commit. Normal paced
load reported no dropped events or read/write failures. Queue-full probes retained
identical HTTP body/status while reporting dropped diagnostic events.

The event database plus WAL/SHM measured about 16.6 MB before explicit
maintenance and 15.5 MB afterwards; the index database measured about 1.18 MB.
These are observed file sizes at named points, not peak allocated filesystem
blocks or a quota guarantee. The fixture is approximately 1.27 KB per event,
not the maximum permitted event size. Other fixture databases are not included
in those per-workload numbers.

The pinned-reader experiment is the significant remaining disk-risk finding:
500 additional small events grew WAL to 23,018,472 bytes. A nonblocking checkpoint
reported busy without changing the reader's snapshot. Releasing the reader and
retrying maintenance reduced WAL to zero and total database/WAL/SHM to 581,632
bytes. The experiment stops its own load after observing 64 MiB; that stop is
**not** production quota enforcement. Payload retention and journal reuse targets
cannot certify the desired aggregate budget while readers pin WAL. Aggregate
admission/reservation and disk-state projection remain required work.
