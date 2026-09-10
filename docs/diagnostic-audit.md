# Diagnostic metric audit

`services/ai/app/services/diagnostic_audit.py` aggregates already validated,
bounded diagnostic inputs. `models/diagnostic_audit.py` owns the closed
`diagnostic-audit-v1` report. The aggregation core and stored snapshot export are implemented;
performance-overhead measurements and full acceptance remain in
[the unified Debug plan](plans/unified-debug.md).

The report retains metric observations and their event/operation/trace/span
references, then groups by observation kind, workflow/stage/phase, provider,
model, available transport configuration, tool contracts/budgets and reviewed
component versions. Unknown context/configuration remains a recorded gap. It
never substitutes current runtime settings for missing historical configuration.

Provider calls, provider attempts, tool calls, Harness stages and Harness
attempts form separate populations. Parent duration includes child work; no
cross-population duration sum is produced. HTTP and diagnostic Harness-reference
events are excluded because they would duplicate those observations. A live
canonical attempt can be measured before its containing stage has a terminal
trace. Removed/unavailable source projections remain unknown.

P50/P95 use nearest rank: sort measured durations and select `ceil(p * n)`, with
one-based ranks. Each group reports measured sample count plus completed,
failed, cancelled, skipped, unknown and recovered counts. Missing duration is
null, not zero. Percentiles include all measured outcomes in that group;
counts expose the outcome mix. Provider recovery is counted once on the parent
call, not on each retry. Repaired Harness stages are separately identified.

Tokens aggregate only provider-attempt terminal observations with
provider-reported values. Input/output/total fields keep separate known sample
counts; absent fields remain null, and no total is inferred by addition. Zero
reported usage remains zero. Failed attempts without usage remain unknown.
Cost and endpoint-configuration gaps are explicit.

Repeated identical event IDs deduplicate; conflicting identities fail the
report. Missing starts/ends are visible. Conflicting span attribution or
configuration produces an unknown observation without duration, tokens or
claimed configuration. Raw content, tool arguments/results and exception text
are not report fields. Metrics establish no business commit proof.

The caller must supply a coherent snapshot and its retention/writer coverage.
The core caps inputs at 10,000 events / 5,000 trace projections and output at
20,000 observations. It does not certify complete installation history or
silently truncate excess input. Run:

```bash
cd services/ai
UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run python -m unittest tests.test_diagnostic_audit
```

## Stored snapshot export

`POST /diagnostics/export` accepts a JSON object with the event query filters
and returns a validated `diagnostic-export-v1` JSON attachment. Event predicates
are shared with the timeline query. The package contains app/schema versions,
filters, events, operation links, retention, writer pages, index projections and
the metric audit. It contains no protected artifacts or raw database files.

Events, links, retention and every writer page use one pinned read transaction.
The Harness index and checkpoint use a second independent pinned transaction;
there is no common business commit timestamp. Missing index storage is an
explicit unavailable coverage gap. Present but corrupt/unreadable storage fails
the export with a fixed error. Exported records are revalidated, including
identity consistency with database keys.

An unfiltered export includes all retained links and index projections, even if
their events expired. Workflow/stage-only exports filter those records by their
stored workflow/stage (legacy links without those fields cannot match). With any
other event filter, links are selected by event request/operation or explicit
operation; index projections describe the resulting related operations,
optionally narrowed by workflow/stage. No recursive traversal occurs. Time,
page, source and severity filters select **events**, not trace time intervals;
contextual traces can predate or outlast the selected events. The index coverage
records that distinction and counts operations without a matching projection.

Bounds: 8 KiB request, 10,000 events, 5,000 links, 5,000 projections, three writer
pages, 16 MiB input payload and 32 MiB serialized output. Limits fail with 413,
never a partial package. Reads have a cooperative five-second deadline including
SQLite progress cancellation; CPU aggregation/serialization checks the deadline
at its boundaries. Missing/corrupt storage returns 503 and invalid filters 422,
without raw exception/input text. Full disk/performance acceptance remains separate from this endpoint.


## Debug snapshot UI

Global Debug → 统计与导出 → 生成诊断快照 explicitly reads the currently applied
event filters. Entering the tab alone performs no export read. Changing applied
filters, leaving the view or closing Debug aborts/fences pending results; refresh
removes the old downloadable snapshot. The download uses the validated displayed
snapshot without another backend read. Browser download/native save handoff does
not certify that a browser download reached permanent storage.

The strict browser decoder uses the Python-generated export schema, requires
complete serialized nested DTOs and verifies filter echo, identity uniqueness,
writer pagination/coverage, event classification and audit sample/count bounds.
The nonrecursive POST transport caps responses at 32 MiB with a 15-second client
timeout plus caller cancellation. Malformed/oversized responses never become
downloads. JSON export stays compact to preserve the backend byte budget.

The view displays up to 100 metric groups with separate outcomes, duration and
usage sample counts, P50/P95, available configuration and gaps; all groups and raw
observations remain in the package. Coverage text distinguishes independent
index timing, event/trace scope and incomplete collection. Chromium acceptance
covers a real mock-provider Persona chain, downloaded JSON and 390px rendering;
this does not certify native save dialogs or all platforms.


## Link and index retention

The diagnostic writer now prunes operation links independently of event cleanup:
seven days from first local insertion, 10,000 rows or 4 MiB UTF-8 payload. Updating
the same request/operation link does not renew its age. The index keeps at most
5,000 projections or 32 MiB payload. Its seven-day age uses canonical update time
when available, otherwise first local observation. Valid old canonical records
are excluded before insertion on every sweep; a later canonical update may
make a trace eligible again. Source timestamps in the future are clamped to
local database observation time; stable rescans do not renew a retained row.

Legacy unknown observation times are counted and begin at migration. Cleanup
uses oldest age then local row order, and retains a newest suffix fitting the
payload budget. Deletions and byte/row counters share their diagnostic
transaction. Index checkpoint advancement and pruning share a transaction;
index read pages now pin the checkpoint and results to one read snapshot.
Capacity-evicted projections may be encountered again in subsequent canonical
sweeps. `removed_rows` counts deletion occurrences, not distinct identities or
excluded source records. Unavailable source timestamps cannot establish age of
canonical history, and no complete-history assertion is made.

Exported `link_retention` shares the event snapshot; nullable `index_retention`
shares the independent index snapshot. The strict browser decoder validates
these records and Debug displays cleanup counts and legacy-time gaps. No domain
rows or canonical traces are removed. These are payload/row retention budgets;
physical SQLite files, freelists and WAL reclamation remain separate work.


## SQLite reclamation

New diagnostic SQLite files enable incremental auto-vacuum before schema
creation. Writer connections use a 256-page WAL autocheckpoint and a 1 MiB
journal reuse target. The event writer, desktop spool persistence and index
worker perform best-effort maintenance **after** diagnostic commits, at most
once per minute per maintenance object; normal event-writer close also attempts
maintenance. It skips active transactions and never commits or rolls back its
caller's work.

A maintenance cycle incrementally vacuums up to 256 free pages and attempts a
nonblocking WAL TRUNCATE checkpoint. Long-lived readers can defer truncation;
their snapshot is preserved and a later cycle retries. Legacy non-auto-vacuum
files require a SQLite VACUUM migration. Migration/reclamation has a cooperative
250 ms budget checked by SQLite progress callbacks, with zero busy timeout;
interruption leaves the database valid and retries later. This is not a hard
wall-clock bound on filesystem calls. Busy timeout/progress handlers are restored.
A large/slow legacy migration may remain deferred across cycles.

Maintenance failures do not relabel committed diagnostics or business results.
Internal maintenance counters are process-local observations, separate from
writer drop/write-failure counters. Physical total size is not certified by
these settings: a pinned reader can retain WAL, live records consume pages,
and multiple databases/spool files require aggregate budget enforcement. That
aggregate admission/quota and performance measurement remain in the active plan.
Regression tests use real SQLite files and verify freelist/file/WAL reduction,
pinned-reader recovery, interrupted legacy migration, active-transaction
preservation and a successful application/Harness result during maintenance
failures.


## Reproducible local measurement

Run `npm run bench:diagnostics -- --samples 100 --output /tmp/diagnostic-benchmark.json`
for provider-free paired middleware probes, a retained writer/index fixture,
query/export timing, file-size observations and a bounded pinned-reader WAL
experiment. See the [baseline and limitations](performance/diagnostic-local-baseline-v1.md)
and its raw samples. These measurements inform the remaining quota and performance
gates; they do not certify full-workflow or native UI overhead.
