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
silently truncate excess input.

Local import actions distinguish JSON reading from draft application:
`json_import_persona_draft` / `json_import_scene_draft` own nested
`json_import_read_persona` / `json_import_read_scene` spans on the same action and
flow. Read completion is not domain-format acceptance. Outer completion means
the guarded editor callback applied the draft, not a persisted resource commit;
domain rejection fails the outer action, while a superseded valid result cancels
it. Import content, filenames and raw errors are excluded from those events.

Run the audit tests:

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

## Per-database quota admission

Diagnostic event storage reserves 128 MiB and Harness index storage 64 MiB of
file-length budget. These partitions include each database, WAL, SHM, rollback
journal and stable quota lock file. A conservative reservation includes a full
logical-database rewrite plus possible checkpoint growth and WAL-index space.
This can reject a small write before the files reach the numerical limit. It is
an admission envelope, not a promise that all payload/row limits can be filled.

All production schema/retention/writer/receipt/checkpoint transactions use a
process lock and SQLite `BEGIN IMMEDIATE`, require WAL mode, disable cache spill,
and check the envelope before work and again before commit. In-memory staging
also has a SQLite page-count ceiling. Rejection rolls back diagnostic work;
native spool acknowledgement stays false until a diagnostic commit succeeds.
The stable lock inode is retained; process exit releases the operating-system
lock. Lock contention is best-effort refusal rather than an unbounded wait.

Maintenance shares the same lock. A nonblocking checkpoint can first release
pressure; VACUUM migration needs additional temporary/rebuild headroom. Incremental
vacuum runs in one explicitly reserved transaction so multiple vacuum steps do
not append repeated metadata transactions outside the reservation. A later
checkpoint/retry can restore admission after a pinned reader exits. Quota refusal
and lock availability counters are process-local; existing writer drop/failure
checkpoints continue to expose their observed lower bounds after writes recover.
The dedicated quota-state projection is described below.

The implementation/test evidence covers cooperating Python writers and measured
file lengths on this local Unix environment. Existing oversized files are
refused without truncation; they need separate recovery/retention treatment.
External writers, allocated filesystem blocks/metadata, desktop spool concurrency,
Windows/native acceptance and an installation-wide 200 MiB assertion are not
certified by this slice. Current export `disk_size_limit_certified` flags therefore
remain false. Tests cover pinned WAL pressure/refusal/recovery, no spill on staged
oversize, process-crash lock release, guarded vacuum, oversized legacy refusal,
non-WAL rejection and successful real Persona/Harness results during pressure.

Post-admission measurements and raw samples: [quota measurement](performance/diagnostic-quota-admission-v1.md).


## Storage state in Debug

Global Debug → 存储状态 reads `/diagnostics/storage` on demand. Closing or leaving
the view aborts/fences pending replies; refresh removes the earlier observation.
The tab ignores event filters. It displays observed file lengths/budgets,
quota-refusal and lock-availability counts, maintenance busy/failure/completion
counts and legacy migration counts. Positive past counts do not mean a current
block, and a within-budget observation is not a successful-admission promise.

Exports embed `storage_observation`; the audit view exposes it in a collapsed
section without another read. This sampling is independent of the event/index
SQLite snapshots and explicitly excludes desktop spool, filesystem allocation
and metadata, external writers and VACUUM temporary files. The strict browser
schema/decoder checks database identity/order, totals, gap/state coherence and
false certification flags. Counts remain process-local; cross-crash writer
coverage is a separate existing view.


## Desktop spool recovery and concurrency

Native emitters and the Python consumer now share `spool.quota-lock`. Rust uses
standard-library file locking (Rust 1.89 minimum); Unix interoperability with the
Python `flock` protocol is tested. A native emitter waits at most 50 ms for this
process lock and then reports a best-effort failure. The Python consumer defers a
busy scan. Neither deletes the stable lock inode. Each consumer record remains
locked through validation, diagnostic persistence and acknowledgement.

Recognized native event files (`desktop-<hex/hyphen identity>.json` or `.pending`)
share a 256-file / 4 MiB payload ring. New records are at most 16 KiB; a full
record is reserved before creation. Both native cleanup and consumption expire
event files after seven days by filesystem modification time. This is not proof
of original creation time across copying/restoration or clock changes. Directory
scans stop at 1,024 entries instead of growing memory without bound. Unknown
files/types and pre-existing corrupt counters are not silently treated as a
certified installation budget.

`drops.count` is a durable lower bound on native evictions. On Unix, directory
deletions are synced before writing/syncing `drops.pending`, atomically renaming
it to `drops.count` and syncing the directory. A complete interrupted checkpoint
can advance the count; an incomplete/stale temporary checkpoint preserves the
last valid durable count and increments the process failure observation.
Crash gaps between deletion and count persistence can undercount, and saturation
or failed storage cannot establish exact global losses. The original count file
is never reset to zero on invalid contents. Process write-failure counts still
reset with the native instance.

The consumer now recovers complete `.pending` event files after a producer
crash. Invalid/partial files are rejected; acknowledgement still requires
idempotent diagnostic commit. Reads are bounded and use no-follow/nonblocking
opens where supported, regular-file checks and identity checks before unlink.
A replacement file is not acknowledged as the file just committed. These checks
protect the cooperative protocol; arbitrary hostile filesystem modification and
Windows directory-flush/power-loss behavior remain outside current certification.
Wire fields are unchanged; `dropped_before` and `write_failures_before` must be
read with the lower-bound/process-scope limits above.

Verification: full Rust library tests include actual sidecar subprocess exit and
two concurrent native writer processes; backend tests cover pending recovery,
shared lock deferral, replacement preservation, expiry, symlink rejection,
offline retry and duplicate identity. Installation-wide size/legacy recovery and
real native Vault success remain separate pending acceptance.
