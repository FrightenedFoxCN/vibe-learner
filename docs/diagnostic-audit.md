# Diagnostic metric audit

`services/ai/app/services/diagnostic_audit.py` aggregates already validated,
bounded diagnostic inputs. `models/diagnostic_audit.py` owns the closed
`diagnostic-audit-v1` report. The aggregation core and stored snapshot export are implemented;
browser/UI integration and performance-overhead measurements remain in
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
without raw exception/input text. This endpoint does not yet imply a browser
export/metric UI or full disk/performance acceptance.
