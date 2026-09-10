# Unified Debug implementation and acceptance checkpoint

This is a requirement audit of [the active plan](unified-debug.md), not a
replacement scope. The overall goal remains active. Independent quality review
is deferred as requested; implementer tests are not presented as that review.

## Current evidence checkpoint (2026-09-10)

Audited source revision: `c20ef1f` (current requirement reconciliation). This replaces the old summary matrix;
chronological sections below remain historical evidence with their original scope.
Only `OBS-FOUNDATION-001` is checked in the implementation plan. The other three
items remain open; implemented slices are distinguished from final acceptance.

The current complete release run is `/tmp/diagnostic-release-c20ef1f.log` on
`c20ef1f`: all 745 backend tests passed in 62.455 seconds, shared/Web reliability
and type gates, all 13 Harness PR suites, and the production build passed.
The current real Chromium suite passed all 16 cases in 24.9 seconds
(`/tmp/diagnostic-browser-c20ef1f.log`). All 11 ordinary native tests passed in
4.66 seconds, with four opt-in probes ignored (`/tmp/diagnostic-native-c20ef1f.log`).
Actual macOS Vault creation, save/lock/unlock, clear/restart/read-back and native
save-dialog export have their separately scoped evidence below. These fresh
checks do not close the failed native saturated-spool budget or missing native
WebView overhead measurement.

The earlier targeted audit `uv run --directory services/ai python -m unittest discover -s
tests -p 'test_diagnostic*.py'` passed all 110 diagnostic tests in 9.976 seconds
using the configured temporary uv cache. Output:
`/tmp/diagnostic-consolidated-audit-tests.log`. This targeted run covers the
diagnostic fault/query/export suites named below, not the full backend suite.

The unrelated desktop icon modification is excluded from all these commits.
Independent quality review remains deferred by the user. No implementer test,
benchmark or native inspection is represented as that review.

## Requirement-to-evidence audit

Paths in this table are relative to repository root. Passing tests establish only
their described cases; an unavailable measurement or platform remains unknown.

| Requirement | Inspected authoritative evidence | Current conclusion |
| --- | --- | --- |
| Shared identities, categories, safe fields and initialization before container construction | `services/ai/app/models/diagnostic.py`, `packages/shared/src/diagnostic.ts`, classification fixture; `test_diagnostics.py` formatter, closed-contract, lifecycle and context tests | Foundation complete. Untrusted browser hints are not authority or admission IDs. |
| Bounded client/server append collection and failure isolation | `diagnostics.ts`, `core/diagnostics.py`; queue, thread-start and failed-transaction tests in `test_diagnostics.py` and `test_diagnostic_failure_isolation.py` | Implemented; business commits survive diagnostic failures in tested actual application cases. |
| Document, OCR and Study Unit cleanup | Real Chromium upload/parse/plan chain and corrupt-PDF correction; `test_diagnostic_document_flows.py`; `diagnostic_ocr_probe.py` and archived `unified-debug-ocr-v1.json` | Successful real local OCR and six canonical stage references verified; unavailable OCR and failed stream/retry have explicit not-committed evidence. OCR quality across documents is not certified. |
| Planning and tools | Real Chromium parse → plan stream → Session action; `test_diagnostic_tool.py` exercises all 37 known tools' rejection telemetry plus actual Planning/Study success and budget failure | Plan identity, committed resource and tool observations verified within the named cases. Tool success does not establish an effect commit. |
| Persona and Scene | Actual mock-backend Chromium generation/application/save/reload/CAS conflict; Persona/Scene hook diagnostic tests | Tested chains have editor-owned flows, separate actions and persisted resource identity; no generated content copied into global events. |
| Study, attachments and interactive questions | Chromium lost-reply reload recovery, multipart success/rejection, answer CAS conflict/retry and automatic callback recovery | These branches have persisted read-back, callback flow retention and grading/content exclusion checks. No provider exactly-once claim. |
| Tavern direct, partial/retry, cancellation and restart | Chromium direct/recovery, partial child retry and cancel; `test_diagnostic_tavern_flows.py`, `test_diagnostic_tavern_crash.py` | Canonical IDs and committed Message sequence inspected; actual child process exit and expired-lease takeover covered. Unflushed crash events remain unknown. |
| Settings and native Vault | Safe-projection adversarial tests and actual controller Chromium test; native UI/save package plus `unified-debug-native-v1.json` and `unified-debug-native-save-v1.json` | Existing Vault unlock/read-back, two settings/Vault saves, lock and subsequent unlock verified on macOS. Isolated native creation and clear-secrets now verified, including restart/unlock read-back; missing Stronghold remove permission was fixed. See the create/clear evidence below. |
| JSON import and export actions | `bounded-json-import.ts`, `diagnostic-actions.test.ts`, `export-json.ts`; browser package download and native save-dialog file validated against `DiagnosticExportV1` | Read/JSON syntax/size outcomes and export handoff verified. Full Persona/Scene import actions now include domain validation and guarded draft application; both actual-browser cases verify failed/completed/cancelled terminal events and no save request. |
| Native startup/sidecar exit and offline spool | `src/diagnostics.rs`, `diagnostic_desktop_spool.py`, real sidecar exit tests, native saved startup/shutdown events | Local Unix lifecycle and retry/acknowledgement verified. Spool empty and stable refusal counters indicate recovery, not proof of complete collection. Other platforms/power-loss semantics unverified. |
| Provider timing, usage source, retry and configuration | `test_diagnostic_provider.py` plus `test_diagnostic_audit.py` real observer retry input | Parent/attempt identity, measured duration, reported-token-only aggregation and explicit missing fields verified. No current live MiniMax request or cost evidence; missing endpoint/configuration evidence is retained. |
| Canonical index rebuild, late commits and resource links | `test_diagnostic_index.py`, query/export tests, browser operation → request → event drilldown | Source-owned projection, restart deduplication, late updates, deletion/unavailability and bounded resource vocabulary covered. Index is never substituted for current commit read-back. |
| Independent Debug ownership and lazy querying | `debug-provider.tsx`, `owned-debug-snapshot.tsx`, route/StrictMode tests and actual navigation browser case | Implemented and locally verified; stale owner cleanup and responses cannot replace a current page. Closed Debug still collects, without preloading all domain data. |
| Page/global timeline, filters, pagination and association expansion | 13 query tests, 10 timeline tests and real global-timeline Chromium scenario | Current filter vocabulary, strict nested decode, pagination limits, resource drilldown, 390px layout and unavailable-state rendering verified. |
| Retention, cleanup and missing coverage | Event/link/index retention tests, writer epochs, exact byte limits and actual process-exit tests | Seven-day/row/payload retention and atomic loss counters verified; no full-history or zero-loss claim. |
| Physical storage and oversize recovery | Quota/disk/recovery/directory tests; real Rust+Python installation probe under pinned SQLite readers | Per-DB/spool admission and bounded recovery/observation implemented. Normal envelopes total 196 MiB; 200 MiB remains a reference, not a proven hard installation cap. Unknown files and up-to-512 MiB recovery workspace remain explicit exceptions. |
| Export and grouped audit statistics | `test_diagnostic_export.py`, `test_diagnostic_audit.py`, strict browser decoding, real browser/native saved files | Pinned event snapshot plus independent canonical index snapshot, raw observations, P50/P95 and outcome/unknown groups verified. Parent/child durations and retry token counts are not added twice. |
| Offline, process exit, disk failure, overflow, duplicates and volume | Failure-isolation/desktop/quota/retention/recovery tests; actual Tavern crash recovery; 12,000-event and combined-storage probes | Required fault categories have concrete scoped evidence. Concurrent snapshots and retry identity are covered; failures are not treated as business rollback or lossless logging. |
| Performance overhead | Backend baseline/quota reports; six request-chain populations; small/wide React timeline reports; native spool/Vault measurements | Persona, isolated Scene, Document→Planning, Study and direct/facilitated Tavern have passing scoped mock-backend paired measurements. Small and wide nested event rendering pass Chromium budgets. Original Scene GC-affected failure remains archived. Native saturated spool still has the original 25.21 ms failure against 25 ms; rejected sorting/sync experiments do not close it. Native Tauri WebView small/wide event populations now pass their scoped rendering budgets. |
| Final checks, commits and archive | Git history and named raw reports/logs | Stepwise commits and evidence exist. A fresh final broad gate and completion audit are required after remaining implementation/acceptance work. |

## Remaining completion work

1. Resolve the native saturated-spool performance failure. Native WebView
   small/wide event overhead evidence is now complete within its stated scope. Keep all failed observations; do not weaken
   durability or widen budgets solely to produce a passing result.
2. Complete current release/native/browser gates, reconcile each top-level plan
   item against the evidence and archive the final result. Deferred independent
   review remains separate.

Native creation/clear, the six scoped backend workflow populations and wide
nested-event Chromium measurement are completed evidence, not pending tasks.
Storage claim reconciliation is recorded in [the storage policy](../diagnostic-storage-policy.md):
owner-specific quotas and recovery are verified, while a 200 MiB installation
hard cap is not certified. This distinction follows the original candidate-default
language and does not change implementation limits or erase their exceptions.

The table does not reopen verified chains merely because unrelated gates are
unfinished, and it does not narrow any requirement to the subset already tested.

## Canonical resource projection slice

The diagnostic Harness index and export now include separately bounded context
subjects, attempted outputs and committed outputs from validated canonical
executions. They preserve nullable revisions and sequence points/ranges, exclude
payload digests and receipts, and explicitly require canonical read-back. This
historical projection is neither current resource state nor proof of all effects.
Old index rows return `not_backfilled` until the next source sweep. A sweep that
finds a removed source clears its resource projection; unavailable source reads
also return an explicit gap rather than cached output claims.

Verification: 23 targeted backend tests passed, including real Persona generation,
restart/backfill, source deletion/recovery, query/export schema drift and retention.
Browser query tests cover the nested vocabulary, null revisions, size limits and
rejection of digests/unreviewed fields; Web type checking passed. This slice does
not yet add cross-domain event resource emitters, resource filters or logical-flow
acceptance, and closes no top-level requirement.

## Canonical resource filtering slice

Harness index queries and Timeline now filter by shared resource type, ID and
optional canonical role. Type/ID match one reference; attempted and committed
roles are never substituted. Pagination and stale-response fencing remain active,
and absent/unavailable/unbackfilled resources cannot silently match. A bounded
read-only SQL scan resolves the filtered trace to the existing operation/request
association drilldown. Event and export selectors explicitly retain their direct
resource-event semantics; cross-domain event emitters remain follow-up work.

Verification: 13 backend query/index/export tests, 12 browser query decoder tests,
9 Timeline component tests, Web type checking and production build passed. All
three production Chromium scenarios passed, including selecting a resource from
the real Persona canonical index through the new controls at 390px width. The
resource screenshot was inspected (`/tmp/unified-debug-resource-index.png`);
there was no horizontal overflow. This validates the index query path, not every
product flow or the unfinished event/flow wiring.

## Scene diagnostic flow slice

Scene draft generation, application of its candidate, field rewrite and library
create/update now share an editor-owned flow with separate action contexts.
Explicit saved-scene loads and imports reset that flow. Context is passed through
the actual API adapters; identity allocation failure leaves editing usable. Scene
library save references use the returned persisted identity/revision, with no
proposal content, private input or invented revision.

Verification: all 26 Scene hook/component tests passed, including flow retention,
reset, rewrite supersession and ID allocation failure; 13 backend diagnostic
query/index/export tests, 12 browser query tests and production Web build passed.
All four real Chromium diagnostics scenarios passed. The new scenario exercises
Scene generation → candidate application → create → update with Debug disabled,
checks one flow/three actions, persisted resource revisions, content exclusion,
and an actual CAS conflict without a new saved-resource event. Saved-scene load
is a local library snapshot operation, not an HTTP reload. This slice does not
close the remaining product flows, native gates or independent review.

## Document and Planning action chain slice

The main Plan Workspace action now passes one captured flow/action through
upload → process stream → learning-plan stream → initial Study Session creation.
Goal-only generation uses the same context owner. Cancellation, supersession and
unmount capture the old flow/page with a separate cancellation action; a new run
gets its own flow. The independent upload-and-process helper also shares one
context. No diagnostic identity is added to model input or durable admission.

Verification: eight Plan generation hook tests and the production Web build
passed. Tests cover the four-step action across page replacement and old/new
flow isolation during supersession. All five production Chromium diagnostic
scenarios passed; the new one uploads the checked-in one-page synthetic PDF,
executes actual parsing and mock-provider planning streams, creates a persisted
Session, and verifies browser/server request identity plus Document/Planning
Harness correlation. It excludes file name, PDF text and objective content from
the diagnostic result. The first run stopped at a test locator before generation;
the role-based locator was corrected and the entire suite rerun successfully.

This proves the successful text-PDF main chain. OCR/failure diagnostic acceptance,
other domain resource emitters, Study chat/question/attachment and Tavern flow
wiring, native gates and the other outstanding audit items remain unfinished.

## Study send/recovery correlation slice

Study Chat sends (JSON or attachments) and operation queries now share a random
flow for the existing Session/client-request pair, using bounded tab-scoped
session storage. Each actual request gets its own action and current page-view;
refresh can retain the flow without retaining prompt/message/attachment content.
Question submission and its required Session read-back share a captured action.
The diagnostic map is separate from durable admission and pending recovery state;
its seven-day / 128-entry / 64-KiB limits can create honest correlation gaps.

Verification: diagnostic API tests cover reload, Session scoping, expiry,
capacity, corrupt/denied storage, JSON/attachment request headers and question
read-back decoder failure with no content leakage. Existing recovery tests and
production build passed. All six production Chromium diagnostics scenarios
passed: the new test commits a real mock-provider Study reply, deliberately loses
the HTTP response, refreshes, recovers by querying the original request, verifies
the retained flow/new action/new page and exactly one matching persisted Turn.
This proves that recovery scenario; full attachment staging and interactive
question product acceptance, Tavern and the other audit gaps remain unfinished.

## Tavern mutation/read-back correlation slice

Tavern mutations, their result refreshes and foreground Run polling now capture
one diagnostic context. A same-room cancellation replacing the current mutation
retains its flow with a new action. Room load/refresh and automatic resume group
their own related requests. The explicit server-authorized terminal replay keeps
the same URL/body/context; it does not broaden the replay policy. Later page
loads or child retries currently start new flows and use canonical operation/Run
lineage for historical association, not an invented persisted flow guarantee.

Verification: 40 Tavern state/decoder regressions passed (one optional externally
populated backend test skipped); eight diagnostic API tests and production Web
build passed. All seven real Chromium diagnostic scenarios passed. The new
Tavern scenario creates a room and tests normal turn completion plus an actually
committed turn whose HTTP response is deliberately lost. Both result-refresh
paths carry the original flow/action, canonical Tavern references are visible,
message content is excluded from diagnostics, and each user message exists once.
The initial browser run exposed a test assumption that an empty composer could
send; that wait was corrected and the complete suite passed. Facilitated partial
failure/child retry, active cancellation/lease recovery diagnostic acceptance and
other remaining audit requirements are not closed by these direct-turn tests.

## Cross-domain saved-resource event slice

Direct diagnostic events now reference saved Document, Learning Plan, Study
Session and Tavern Room/Run/Message records alongside Persona/Scene. Source is
an actual returned record or decoded committed Study receipt, not a transaction
internal candidate, URL or HTTP status. Message sequence and parent Room identity
remain exact; types without authoritative revision use null and reject invented
revision values. Queries and exports share browser/backend ownership checks.
The Timeline can expand a resource event into its same-request events, then use
existing canonical operation links. Replayed observations are not new commits.

Verification before the broad gate: 43 backend diagnostic/query/export/index and
Tavern API tests, 13 browser query tests, 10 Timeline tests and production build
passed. All seven real Chromium scenarios passed with new assertions for
Document/Plan/Session references and Tavern Message sequence/Room correspondence.
Failure-isolation tests prove writer errors cannot replace the caller's outcome;
strict decoder tests reject invented revisions and incomplete message scope.
Remaining workflow fault acceptance, old oversize recovery, native success and
performance gates remain as listed above; this does not close the overall goal.


The cumulative `npm run check:release` gate also passed after this resource slice:
shared/Web contracts, reliability/type gates, all 13 Harness PR suites, the full
backend suite (718 tests in 57.909 seconds) and production Web build. Raw output is retained at
`/tmp/unified-debug-domain-release.log`. Native tests and the still-open acceptance
items are outside this gate; overall completion remains unproven.


## Desktop spool storage observation slice

Storage queries and exports now scan the conventional sibling `desktop-spool`
directory without reading file contents. At most 1,024 entries contribute event,
metadata and unknown regular-file counts/lengths. Unknown names and paths are not
returned. The directory is pinned with a no-follow descriptor on supported Unix
platforms; symlinks, nested directories, filesystem failures and scan overflow
produce explicit incomplete/unavailable gaps. Unsupported platforms do not fall
back to following paths. Absent directories are distinguished from read failures.
The observation is read-only, independently sampled and not an admission or full
installation disk-budget guarantee. Unknown files are counted, not deleted.

Verification: 14 backend storage/export tests and eight desktop spool regressions,
13 browser query tests and 10 Timeline component tests passed. Tests cover real
pending files, metadata, unknown files, symlinks, scan overflow, absence/failure,
strict response totals and schema/export compatibility. Production Web build also
passed. This slice changes neither native writes nor retention. Old oversized DB
recovery, installation accounting, native acceptance and the other audit gaps
remain open.

## Legacy oversize recovery slice

Events and index startup now attempt a separate bounded recovery when normal
admission refuses the existing file. Event startup stays alive and retries after
reader/space deferral; the index uses its existing retry loop. Maintenance can
also request the same throttled recovery. Checkpoint release that restores normal
admission does not shorten retention. Otherwise the diagnostic retention owners first preserve the normal retained set
and compact free pages. Only if ordinary admission still fails do they keep a
smaller newest suffix under physical pressure, committing existing removal
counters with deletions before another compaction. In-place SQLite VACUUM reclaims pages; no open DB is
renamed/replaced and canonical repositories are never written by recovery.

This is an explicit transient exception to the steady-state admission envelope:
recovery reserves up to 512 MiB additional workspace above independently observed
starting file lengths, checks available space, disables cache spill, caps source page
growth, uses memory temporary storage, and applies a cooperative five-second SQL
deadline. Attempts are throttled to once per minute. Readers, workspace shortage,
overlarge sources or SQL failure defer/fail safely; these cases do not certify a
200 MiB installation maximum. Successful recovery means ordinary reservation
passes again, not that the whole installation is certified. Storage query/export
and UI expose process-local attempts/completions/deferrals/failures plus the
possible temporary overage and workspace envelope.

Eleven direct recovery tests cover real event/index startup, preserved/newest
records and durable loss evidence, space/workspace refusal, deadline rollback,
active transaction ownership, reader release without restarting the writer,
unchanged ordinary admission, lossless freelist compaction versus necessary
pressure eviction, the initialization/close race, and hard subprocess exits before deletion commit,
after deletion commit, and during VACUUM. Restart verifies SQLite integrity and
no repeated deletion counts. The broader targeted diagnostic run passed 36 tests
before the final preservation/race regressions; all eleven final recovery tests
passed. Browser query and Timeline suites passed (13 and 10 tests).

A reproducible local 144 MiB freelist probe is archived under
`docs/performance/diagnostic-legacy-recovery-v1.json` with its scope note. It is one
observation, not native/browser overhead acceptance or an installation budget
certification. Full fault-flow, native success, aggregate accounting/performance
and deferred independent review remain open.


The first full gate exposed a startup/close race: a stop observed before schema
initialization discarded accepted queued events. Initialization now makes one
attempt and drains accepted events after success; only failed retry attempts stop
on closure. Existing shutdown/coverage tests and a deterministic paused-startup
race validate the fix. The next broad gate passed, followed by the final
preserve-first refinement and its dedicated tests; final gate results follow.

Final `npm run check:release` passed on the final recovery implementation:
shared/Web reliability and type gates, all 13 Harness PR suites, 732 backend tests
in 59.325 seconds, and production Web build. Raw output:
`/tmp/diagnostic-recovery-release-final.log`. All seven production Chromium
scenarios also passed against the isolated real mock backend, including the
storage view and diagnostic download (`/tmp/diagnostic-recovery-browser.log`).
This closes this bounded recovery implementation slice; the overall goal and the
remaining installation, workflow-fault, native and performance acceptance remain
active.

## Diagnostic directory accounting slice

The storage query/export now includes a separate no-follow recursive inventory of
the diagnostic directory. It counts regular-file lengths for configured database
families, the desktop-spool subtree and other files, including unknown nested
files, without returning names/paths or reading/deleting content. This inventory
is not a sum of the independently sampled database/spool panels. A configured
index outside this directory is an explicit coverage gap.

The scan has a global 4,096-entry bound, four levels below the root, and a
cooperative 100 ms deadline. Descriptor-pinned directories and inode checks avoid
following replaced directory links. Filesystem errors, links/special files,
depth/time/entry limits preserve explicit gaps. Partial observations can prove
that observed lengths already exceed the 200 MiB reference, but cannot certify
that complete usage is below it. Sparse files use logical file length; physical
blocks, external changes and transient recovery workspace remain uncertified.

Verification: 19 backend directory/storage/export tests, 13 browser query tests,
10 Timeline tests and production Web build passed. Cases include real database,
spool and unknown nested files; sparse files above 200 MiB; directory/file links;
external database configuration; all scan bounds; absence and unavailable roots;
strict totals, classification and gap/budget-state decoding. The directory total
is an observation, not aggregate admission enforcement. Combined writer budget
and recovery-overage validation, remaining workflow/native/performance acceptance
and deferred independent review are still open.

`npm run check` also passed, including shared/Web reliability/type checks and all
13 Harness PR suites. All seven production Chromium scenarios passed with the
new directory totals in storage and exported JSON. The 390px directory screenshot
was inspected (`/tmp/unified-debug-directory.png`) and no horizontal overflow was
observed. Logs: `/tmp/diagnostic-directory-{python,query,timeline,build,check,browser}.log`.
The full backend release checkpoint remains the preceding recovery slice; this
read-only inventory slice used the targeted backend verification listed above.

## Combined storage / cross-runtime pressure slice

Same-directory legacy recovery owners now share a stable process-lock inode before
taking their per-DB lock. One recovery workspace proceeds at a time; ordinary
writes in other DBs remain independently admitted. Existing crash tests also
exercise release of this shared lock. The event writer now explicitly closes its
SQLite connection on thread exit rather than waiting for garbage collection;
the installation probe exposed the previous lock retention during setup.

A reproducible Python/Rust probe uses the real default event/index budgets, pinned
60/28 MiB legacy freelists, a full native spool and concurrent native writes,
event/index updates and spool consumption. It requires actual quota refusals,
checks sampled 200 MiB reference usage, releases readers and verifies both SQLite
files. Missing-source index rows are intentional storage load, not canonical
commit evidence. See [combined probe](../performance/diagnostic-installation-v1.md)
and its raw report with source and binary hashes. Normal limits total 196 MiB plus bounded
metadata; this is neither an atomic peak measurement nor control of unknown files
or a 200 MiB transient recovery cap. Broad certification is not inferred.

Targeted validation passed 42 backend tests and all 11 Rust library tests before
the final cross-runtime probe. New regressions cover two competing recovery owners,
ordinary writes during recovery, and explicit connection release without GC.
The full gate and final probe results follow. Workflow fault/alternate-flow,
native Vault/export success, frontend/native performance and deferred independent
review remain open.

Final verification passed: `npm run check:release` completed shared/Web checks,
all 13 Harness PR suites, 739 backend tests in 61.046 seconds and production Web
build; all 11 Rust library tests passed. The final cross-runtime probe completed
with 1,880 raw samples and a maximum observed 108,231,185 bytes (about 103.22 MiB).
Both DB quota counters recorded real refusals; intentional overload produced
reported drops and consumer failures, not an assertion of complete collection.
Final inventory was complete and both SQLite integrity checks passed. Logs:
`/tmp/diagnostic-installation-{release,native,python}.log`; the probe's raw report
is archived with the implementation. This does not certify an atomic disk peak,
unknown external files, Windows behavior or transient recovery below 200 MiB.

## Study attachments and interactive-question acceptance slice

Question-attempt responses now emit a Session resource observation only after the
saved receipt has passed response validation, using its own Session identity and
committed revision. No answer, grading material, prompt or newly fabricated
Harness identity is included. Stale-revision failure emits no saved resource.

Two additional real Chromium scenarios passed (nine total). The attachment case
sends a real multipart text file, checks its persisted public Turn attachment and
content, verifies Study Harness/Session correlation, then submits unsupported
media. That rejection is an HTTP 200 **not_committed** receipt, not a transport
error: the Session revision stays unchanged and diagnostics have no saved-resource
claim. The test checks both successful and rejected requests for content/name
exclusion. Existing backend attachment effect tests separately exercise staging,
read-back, tamper rejection and uncertain-operation recovery.

The question case uses a scripted, typed mock-provider question in the disposable
acceptance server only. Admission, protected snapshot, proposal handling, Session
commit, question CAS, grading, HTTP decoding, UI read-back and automatic callback
use production paths. Before submission, the public question excludes grading
fields/explanation. A deliberately stale revision produces a real 409 and leaves
the question unanswered; retry persists the result and triggers one committed
interactive callback. POST and mandatory Session read-back share the action/flow.
Generation, answer, failure and callback diagnostics exclude prompt/grading
sentinels. The callback currently owns a separate flow and is associated through
Session/canonical records; inherited callback-flow wiring remains follow-up work.
This is scripted-output integration evidence, not independent model-quality review.

Verification: 42 backend question/effect/diagnostic-query tests and all nine
production Chromium scenarios passed. The first browser run exposed test
assumptions about HTTP rejection status and the public Turn field name; assertions
were corrected to the actual `not_committed` receipt and `learner_message_kind`,
then all scenarios passed. Logs: `/tmp/diagnostic-study-alternates-{python,browser}.log`.
No shared/public response shape changed. Remaining callback-flow wiring,
Document/OCR fault paths, Tavern partial/retry/cancel/recovery, native success and
performance acceptance remain open; no top-level goal item is closed here.

## Immediate question callback flow and reload recovery slice

An immediately executed question callback now inherits the successful answer's
random diagnostic flow, while allocating its own action. The callback request's
bounded tab-local diagnostic mapping preserves that flow across reload/query
recovery. Existing request mappings cannot be rebound by a later parent hint;
invalid hints fall back to ordinary allocation. No diagnostic metadata enters
chat admission JSON, request fingerprint, durable pending-operation state or the
model/public response schema. Diagnostic entropy failure still permits answer
read-back and callback handling. Paused callbacks aggregate into a later learner
action and retain that action's separate flow; this slice covers immediate callbacks.

All ten production Chromium scenarios passed in 15.4 seconds. The added scenario
lets the real callback commit, aborts its response, reloads the page, and verifies
query-only recovery with the answer flow, new action/page-view, exactly one callback
POST and the original committed Turn. The existing CAS/retry scenario additionally
checks distinct callback action and callback-specific resource observation by
request ID, plus exclusion of grading/prompt material. Unit regressions cover
mapping reload/non-rebinding, malformed hints, transport/body separation, hidden
send/query propagation and entropy failure. `npm run check` and production Web
build passed. Logs: `/tmp/diagnostic-callback-{check,build,browser}.log`.

This supersedes the separate immediate-callback flow limitation above. Remaining
Document/OCR faults, Tavern partial/retry/cancel/recovery, native Vault/export,
performance acceptance and deferred independent review remain open.

## Document parser fault and retry HTTP acceptance

`test_diagnostic_document_flows.py` exercises the real multipart upload, threaded
NDJSON route, parser, durable admission and Harness runtime in a temporary local
installation. A corrupt PDF and forced OCR with the engine disabled each produce
HTTP 200 plus terminal `stream_error` and persisted Document `failed`. Their
process diagnostics retain the supplied flow and server request identity, reference
real canonical operations/traces, and contain no saved-resource observation,
filename or document-content sentinel. The Document parse parent is failed and
`not_committed`; separately admitted child-stage operations are checked against
their own canonical records rather than assumed to share one operation identity.

Retrying the OCR-unavailable document without forced OCR succeeds through real text
extraction with the same supplied flow, a new action and disjoint admitted operation
identities. Its parse parent has committed evidence and its saved-resource event
references the original Document. This is backend HTTP evidence; browser ownership
of the retry action and successful real OCR-engine execution remain to be tested.
No production behavior changed in this slice. All 25 diagnostic/document operation
and stage-metrics tests passed in 2.034 seconds; log:
`/tmp/diagnostic-document-fault-python.log`. The initial test draft incorrectly
assumed one operation per entire parse and exceeded the query page limit; the final
assertions follow the actual bounded query and independent stage-admission contracts.

## Plan Workspace failed upload correction in Chromium

The real browser now exercises corrupt PDF upload → terminal parse failure →
corrected file submission → successful Plan/initial Session. It verifies the
visible failure notice, absence of Planning/Session POSTs after the failed parse,
persisted failed Document and no process-request saved-resource observation.
Upload/process share the first flow; changing the file and explicitly submitting
again creates a new Document and a new flow shared by all four successful requests.
This is a new user submission, distinct from the backend same-Document retry above.
Failed-flow diagnostics exclude file/content/objective sentinels. The first draft
used the initial file label after selection; the final test follows the actual
“更换教材文件（PDF）” control. All eleven production Chromium scenarios passed in
14.2 seconds; `/tmp/diagnostic-document-browser.log`. No production change was
required. Real OCR-engine success, Tavern faults, native and performance acceptance
remain open.

## Tavern partial-run replay and child-retry HTTP acceptance

A disposable full application now runs three real admitted actor slots with a
scripted provider failure on the second call. The HTTP 502 parent retains the first
committed Message; replay of the exact request returns `partial` with completed,
failed and blocked steps without another provider call. Child retry executes only
the second and third actors, adds no input Message, and finishes `completed`.
Diagnostic references match the real parent/child Harness bindings and canonical
trace IDs. The parent includes both committed and not-committed actor evidence;
HTTP failure is not treated as evidence that no actor committed. Failed response
has no direct saved-resource observation, while replay and retry observations
match precisely their returned Message IDs, per-room sequence points and Room
scope. Supplied flow remains shared with separate actions and server request IDs.
Persona/Room/message/guidance content and provider exception text are excluded.

All 36 diagnostic and Tavern facilitated tests passed in 7.343 seconds; log:
`/tmp/diagnostic-tavern-fault-python.log`. Existing facilitated tests exercise
cancel/lease/recovery behavior, but this added diagnostic acceptance specifically
covers partial/replay/child retry. Browser retry flow ownership and diagnostic
cancel/restart correlation still need direct verification. No production behavior
changed; native/OCR/performance and deferred independent review remain open.

## Tavern concurrent cancel and late-result HTTP acceptance

A full-application test holds a scripted synchronous provider call behind an event
barrier while another real HTTP request cancels the admitted run. Releasing the
provider returns a valid reply, but commit fencing rejects the original worker
with HTTP 409; no actor Message persists and the Room retains only its input
Message. A later resume is HTTP 200 replay of `canceled`, with no generated Messages
or further provider call. The initial test's assumed resume conflict was corrected
to this existing terminal read-back contract.

Turn, cancel and resume diagnostic events retain the supplied flow and their own
server request/action identities. Cancel/resume resource observations identify
exactly the Room, Run and persisted input Message; the failed worker emits no
saved-resource event. Harness references resolve to the admitted operation and
canonical traces, whose actor commit outcomes are `not_committed`. Room/message
and injected exception sentinels stay out of diagnostics. This proves late-result
fencing in a live process, not cancellation of an upstream synchronous request or
process-restart recovery.

All 37 diagnostic/facilitated tests passed in 7.381 seconds; after strengthening
resource-set and canonical trace assertions, both diagnostic Tavern tests passed
again in 0.448 seconds. Logs: `/tmp/diagnostic-tavern-cancel-{python,final}.log`.
No production change was needed. Browser cancellation ownership, restart/lease
correlation, OCR/native success and performance gates remain open.

## Canceled Tavern application restart read-back

The concurrent-cancel test now closes the entire FastAPI application and creates a
fresh Container, database connections, diagnostics store and provider against the
same temporary installation. Resume still reads back `canceled` with zero new
provider calls and the immutable admitted binding unchanged. Every original turn
diagnostic event ID survives; the new read-back has distinct event/request IDs,
retains its explicitly supplied flow and observes exactly the persisted Room, Run
and user Message. Two diagnostic Tavern scenarios passed in 0.503 seconds; log:
`/tmp/diagnostic-tavern-restart-python.log`. This is orderly application restart and
terminal read-back evidence, not process-crash recovery or live lease takeover.
Those fault boundaries and browser flow ownership remain required follow-up work.

## Tavern abrupt process exit and expired-lease diagnostic recovery

`test_diagnostic_tavern_crash.py` starts a child with the full HTTP application,
commits the first actor, and calls `os._exit(73)` inside the second provider call.
The parent opens a fresh application against the same installation, verifies the
completed/generating steps and first immutable Message, expires only that run's
abandoned generating lease using the existing recovery-test technique, and resumes
through HTTP. The second step's claim count becomes two; exactly one provider call
finishes the remaining actor. First Message bytes and admitted operation binding
remain unchanged.

The persisted original diagnostic prefix has real operation/trace references and
no request-finished event. Recovery uses a new server request identity with the
explicitly supplied flow and the same admitted operation. Both requests' trace IDs
resolve against the canonical runtime; recovered resource references match returned
Message IDs/sequence points. Room/message content is excluded. The child explicitly
drains the diagnostic queue before abrupt exit so this verifies recovery of a known
persisted prefix, not survival of an unwritten queue tail. Lease expiry is advanced
in test data, not awaited in wall-clock time. Browser flow ownership and real
upstream provider idempotency are outside this scenario.

All nine diagnostic Tavern and cross-domain process-recovery tests passed in
15.569 seconds; `/tmp/diagnostic-tavern-crash-python.log`. No production changes
were necessary. Browser Tavern branches, successful OCR/native paths, performance
and consolidated final acceptance remain open.

## Tavern partial/retry ownership in the real browser

The disposable browser provider now injects one failure on the second actor for
an exact test-only message. The Chromium case creates a two-person Room and
explicitly selects both responders. It observes the real failed request followed
by automatic same-request replay to `partial`; both POSTs share action and flow.
Clicking “仅重试未完成角色” creates a new user action/flow, shared by its retry POST
and subsequent Room/recovery reads. The child completes only the missing actor,
adds no user Message and retains the original committed Message unchanged. Both
flows have persisted Run and Harness references and exclude the trigger and
exception text. Parent/child operation identity is separately verified by the
HTTP diagnostic tests above; distinct user actions need not share a flow.

All twelve production Chromium scenarios passed in 15.4 seconds; log:
`/tmp/diagnostic-tavern-partial-browser.log`. Initial test drafts assumed the
creation form was already open, every participant was automatically a responder,
and the notice omitted its revision suffix; the final test follows the actual
new-Room action, explicit Participant Roster selection and rendered notice.
Production behavior did not change. Browser cancellation, OCR/native success,
performance and consolidated final acceptance remain open.

## Tavern browser cancellation ownership

The disposable provider waits, for one exact test-only message, until its real
lease continuation check fails (bounded by ten seconds). Chromium sends a turn,
waits for the actual cancel control, clicks it, and observes a saved `canceled`
run and the original turn's HTTP 409. Only the user Message remains. Cancellation
allocates a different action while inheriting the active turn flow; its three
or more Room/list/recovery GETs retain the cancellation action and flow. Persisted
diagnostics contain the canceled Run observation, original request's 409 and
Tavern Harness references, with no actor Message observation or trigger content.
The production cancel controller and server are unchanged; this uses a cooperative
test provider and does not claim hard cancellation of an upstream request.

All thirteen production Chromium scenarios passed in 17.8 seconds; log:
`/tmp/diagnostic-tavern-cancel-browser.log`. This completes the explicit browser
partial/retry/cancel cases identified in the preceding Tavern slices. Successful
real OCR/native paths, performance and consolidated full-scope acceptance remain
open; no top-level goal item is closed by this checkpoint.

## Real local OCR success acceptance

The opt-in `tests.diagnostic_ocr_probe` uses installed ONNXTR and the existing local
`db_mobilenet_v3_large`/`parseq` models, without a fake OCR result. It rasterizes
synthetic text into a one-page image-only PDF (asserting no embedded PDF text),
uploads through HTTP, forces OCR through the real stream route, and reads persisted
Document/debug records. OCR is applied to one page and the synthetic heading is
actually recognized; the Document parse parent has canonical committed evidence.
Diagnostic references resolve to real parse/extraction/section/chunk/OCR/cleanup
traces and the saved Document request. File name, text sentinels and recognizable
content are excluded from the diagnostic events.

The successful local observation took 3.020 seconds and returned 14 flow events;
this is a single functional sample, not a latency gate or representative OCR quality
measurement. Model SHA-256 fingerprints and result are archived in
[raw OCR report](../acceptance/unified-debug-ocr-v1.json). Reproduce from repo root:
`UV_CACHE_DIR=/tmp/vibe-learner-uv-cache uv run --directory services/ai python -m tests.diagnostic_ocr_probe --output /tmp/diagnostic-real-ocr.json`.
The probe requires the named cached models and fails if they are absent; it is
separate from ordinary deterministic unit tests. Log: `/tmp/diagnostic-real-ocr.log`.
The initial probe used the wrong owner for `ocr_applied`; the final check reads the
persisted debug record where that field belongs. Native success, overhead and
consolidated acceptance remain open; no independent quality claim is made.

## Chromium collection overhead

An opt-in headless Chromium probe executes the actual collector bundle with
saturated bounded queues and verifies overflow/upload accounting. Sixty raw burst
samples give P95 1.400 ms for 100 requests/200 events, within the predefined 16.7 ms
collection-only frame budget. Snapshot and serialization/flush samples are also
retained; flush uses a local acknowledgement stub and excludes network. See
[method and report](../performance/diagnostic-chromium-collector-v1.md).
This does not close React/native/full-workflow overhead acceptance. Native UI
verification is ongoing in an isolated application; prior bundled sidecar output
is not evidence for the current source backend.

## Native-discovered event schema admission recovery

The isolated native application first used an older packaged sidecar and a Web
port outside the desktop allowlist; those setup results do not certify the current
backend. Switching the temporary app package to the source sidecar on port 3000
exposed a real collector startup gap: connection setup retried quota contention,
but a refusal while admitting the subsequent schema transaction terminated the
writer. The observed event file had no tables and two quota-unavailable counts;
other diagnostic storage continued operating.

Connection configuration and transactional schema initialization now share one
startup retry loop. Failures roll back before waiting; successful startup still
drains accepted events even if close races initialization, while repeated refusal
stops promptly on close and accounts for discarded events. Two regressions cover
actual separately-held quota-lock contention in the schema window and close during
schema refusal. All 33 diagnostic recovery/disk/core tests passed in 3.819 seconds.
The isolated native app was restarted with the fix and its event table contained
39 events; a later query also observed the real Vault-unlock start and excluded
the synthetic saved-key sentinel. Full release verification follows separately.
This fixes retry handling; it does not claim all possible native startup failures
are resolved or complete Vault/export acceptance.

Schema-retry release verification passed: `npm run check:release` completed
shared/Web checks, all Harness PR suites, 745 backend tests in 78.999 seconds and
production Web build. Log: `/tmp/diagnostic-schema-release.log`. Continued native
inspection found a separate Settings current-page debug projection exposing raw
runtime secret/probe endpoint fields; only a synthetic invalid key was used in the
isolated app. That projection requires correction before native/full acceptance.

## Native Vault unlock latency investigation

The observed 45.953-second unlock was reproduced in a standalone Stronghold
snapshot probe without application tables. Optimizing three development crypto
dependencies reduced real existing-Vault native unlock to 972 ms; read-back took
1 ms. The UI confirmed unlocked state after restart. Cryptographic settings and
snapshot compatibility are unchanged. See [measurements and reproduction](../performance/desktop-vault-dev-v1.md).
All 11 ordinary native tests and both opt-in timing probes passed. This closes the
specific slow-unlock investigation, not the remaining Settings debug projection,
native export, full overhead or consolidated acceptance work.

## Settings safe projection and native diagnostic export

The Settings current-page snapshot previously passed whole runtime settings,
numeric drafts, provider probe caches and desktop state into Debug. Native
inspection found the synthetic test key both in settings and an `endpointKey`.
The adapter now constructs explicit summaries: configured-key booleans, committed
numeric values and draft validity, probe counts and allowlisted readiness states,
and desktop/error presence. Arbitrary URLs, model names, paths, drafts, timestamps,
provider/error text and future fields are not copied. Unknown enum values map to
`unknown`. Product controller state is left intact.

Two adversarial projection tests cover raw secrets across those fields, future
fields and malformed enum/numeric inputs. Ten Settings tests, `npm run check`
(including shared/Web reliability and all 13 Harness suites), production build,
and all 14 real Chromium diagnostic scenarios passed. The new browser case feeds
synthetic settings into the actual controller, checks rendered Debug and reload,
and leaves the live backend's settings untouched.

The isolated macOS app restarted against the new production Web build, unlocked
its existing test Vault, and displayed only safe summaries. Screenshot inspection
confirmed the current-page rendering; persisted unlock/read-back took 860/1 ms.
The global export was saved through the actual macOS save dialog to
`/tmp/unified-debug-native-acceptance.json`. The 95,379-byte file contains 122
unique events and passes `DiagnosticExportV1.model_validate_json`. Both spelling
variants of the synthetic test key are absent, including the actual value whose
underscores were dropped during earlier native typing. This corrects the weaker
earlier sentinel-exclusion observation. No real provider credential was used.
The package honestly reports zero Harness metrics for this settings-only run.

The [archived native result](../acceptance/unified-debug-native-v1.json) contains
the package digest, counts and Vault event metadata, not its secret or raw UI state.
Logs: `/tmp/settings-debug-tests.log`, `/tmp/settings-debug-check.log`,
`/tmp/settings-debug-build.log`, `/tmp/settings-debug-browser.log`.
Native create/save/lock evidence, remaining performance and consolidated scope
audit remain open. Current native spool failure counters also require inspection;
successful export does not certify complete collection.

## Native save, lock and subsequent unlock

The isolated native Settings page toggled Debug off, waited for saved state, then
restored Debug on and waited for saved state. Each normal settings save executes
the real Vault save, session-secret synchronization and settings HTTP update.
Both Vault child spans share their enclosing settings action/flow and point to
the correct parent span. Observed settings/Vault durations were 766/754 ms and
735/728 ms. Lock completed in 731 ms, the UI showed locked, and a subsequent
unlock restored the configured-key state. Desktop settings GET deliberately
returns blank keys, so this read-back checks configured flags and UI state rather
than claiming an HTTP plaintext equality test.

The native download handoff also has its matching completed event; its 18.643 s
includes the human/UI save-dialog interval and is not serialization latency.
All six named action kinds have completed events. Their diagnostic records omit
the actual synthetic key. [Save-chain metadata](../acceptance/unified-debug-native-save-v1.json)
archives identities, parent links and measured times.

The five desktop-spool failures match five event-database `quota_unavailable`
observations. They remained unchanged across these subsequent saves and reads;
the native spool contains zero pending event files, writer queue is zero, writer
is alive, read failures and quota-refusals are zero, and maintenance succeeded.
The consumer retries a refused external persistence call without acknowledging or
deleting the spool file. These observations support recovered admission contention,
not five proven lost events. Exact historical per-attempt causes were not logged;
the lower-bound/unknown coverage labels remain. No speculative counter reset or
storage mutation was performed.

Native creation diagnostics, performance coverage and the consolidated audit
remain required. The earlier raw Settings projection issue is fixed, and native
save/lock and diagnostic save-dialog paths now have concrete evidence.

## React and native spool overhead checkpoint

The production React timeline/query decoder now has a reproducible Chromium
measurement at the 500-row cap. Thirty samples per operation pass predeclared
150 ms mount/append and 100 ms expand/unmount P95 budgets. Native synchronous
spool emission was also measured through the real writer: sparse/contended cases
pass, but saturated-ring P95 25.21 ms exceeds its 25 ms budget. The failed report
is retained and native overhead remains open. See [method and raw reports](../performance/diagnostic-render-and-spool-v1.md).
These scopes do not replace native creation, maximum nested-record rendering,
full-workflow overhead or the consolidated requirement audit.

Native stage investigation found filesystem synchronization dominates saturated
emission. The unchanged runtime measured P95 23.09 ms in a later sample set;
filename-only sorting did not establish a scan improvement and was reverted.
Test-only stage instrumentation and both raw reports are retained in the
[investigation](../performance/diagnostic-native-spool-stages-v1.md). The original
25.21 ms failed observation remains part of the evidence; no runtime durability
change or performance-acceptance closure is claimed.

## Complete Persona and Scene import actions

`json_import_persona_draft` and `json_import_scene_draft` now wrap bounded JSON
reading, the existing domain normalizer and the existing guarded draft-application
callback. The original read action is a child span on the same captured action,
flow and page view. JSON reading can complete while the enclosing import fails
validation. A valid but superseded import returns false from the original fence
and records cancellation; only successful draft application records completion.
This is not a persisted Persona/Scene commit, and emits no saved-resource claim.
Original exceptions and UI handling are preserved. Python/TypeScript action names
and generated query/export schema fixtures changed together.

Three targeted tests use the real normalizers, verify rejection before mutation,
parent/child correlation, content exclusion and the original page during a delayed
cancelled import. Two new production Chromium cases exercise actual file inputs
for Persona and Scene: valid JSON with invalid domain structure, valid import,
a delayed valid read superseded by a replacement, and no business save requests.
All four terminal outcomes are read back from the real diagnostic backend; all
read children have matching parent identity and input filenames/content are absent.

Verification: 3 targeted import tests, 23 backend diagnostic/query/export tests,
`npm run check` (shared/Web reliability/type gates and all 13 Harness PR suites),
production Web build, and all 16 Chromium diagnostic scenarios passed (24.8 s).
Logs: `/tmp/diagnostic-import-{tests,backend,check,build,browser}.log`.
The prior import-action audit gap is resolved. Remaining native creation/clear,
whole-workflow overhead and final acceptance requirements stay open.

## Persona full request-chain overhead

Thirty paired enabled/disabled samples now execute actual mock-provider generation,
save generated card contents as a Persona and reload persisted content. Both sides
retain canonical Harness; the control only bypasses diagnostic collection/workers.
The signed paired P95 overhead is 18.88 ms against a predeclared 50 ms budget,
with maximum delta 64.77 ms explicitly retained. Candidate generation has actual
`not_applicable` commit status, while Persona persistence is verified separately.
See [method and complete raw report](../performance/diagnostic-persona-workflow-v1.md).
This fills one backend workflow comparison; it does not close all-workflow,
browser/native, saturated-spool or remaining native functional acceptance.

## Fresh release gate and isolated native creation setup

The full `npm run check:release` completed successfully on `4fe96d7`; its results
are summarized at the top. A separate temporary native bundle,
`/tmp/Vibe Diagnostic Creation.app`, uses identifier
`com.vibelearner.diagnostic-creation-acceptance` and its own application-support
storage, leaving the previous acceptance Vault untouched. It runs the current
source sidecar and production Web server on port 3000. Restarting the old Web
process after the release build resolved a stale static-resource mismatch.

The actual app displays unconfigured Vault and the create/unlock form. Before
handing off credential creation, a read-only health query verified the writer is
alive, queue/drops/read failures are zero, and 29 events are persisted. Five spool
persistence retry failures are visible, matching the already investigated startup
contention pattern; no claim of lossless startup is made. Native build log:
`/tmp/diagnostic-creation-build.log`; readiness observation:
`/tmp/diagnostic-creation-ready.json`. The UI creation itself is still pending and
must not be represented by this setup as completed.

The computer-use tool's credential-creation rule requires the user to enter,
confirm and submit a new credential. Once the user creates this isolated Vault,
verify actual create/read-back events before proceeding with test-secret clearing.
Other outstanding measurements remain independent work while awaiting that action.

## Scene full request-chain overhead

The shared probe now also generates a Scene, saves the entire generated tree and
reads it back through the actual routes. Thirty pairs passed persistence,
correlation, content exclusion and no-drop checks, but the paired P95 overhead
was 67.74 ms, exceeding the unchanged 50 ms gate. This failure remains open pending
request-stage attribution; no passing rerun substitutes for resolving it.
See [Scene method and raw evidence](../performance/diagnostic-scene-workflow-v1.md).
The Persona branch passed a one-pair compatibility smoke after three warmups.
No production code changed in this slice; the earlier full release result remains
scoped to its recorded revision. Remaining native functional and performance work
is not closed by these measurements.

## Native creation and clear-secrets completion

The user created the isolated Vault, and actual persisted `vault_create` start and
completed events share action/flow/span identity; duration was 762 ms. A synthetic
API key was then saved through Settings. Lock/unlock and a full app restart/unlock
restored all four effective configured flags, proving data existed before clearing.

The first actual Clear action failed: Tauri rejected `remove_store_record` because
`stronghold:default` does not grant it. Added only
`stronghold:allow-remove-store-record` to the main-window capability. The isolated
application rebuilt successfully (`/tmp/diagnostic-clear-build.log`) and was
replaced/restarted with the same test storage. Clear then completed in 705 ms.
After another complete app restart and authorized unlock, the UI reported no API
key and all four backend configured flags remained false. The original acceptance
Vault was not modified; this disposable Vault remains configured but empty/unlocked.

[Native create/clear evidence](../acceptance/unified-debug-native-create-clear-v1.json)
archives 170-event validation count and only safe action metadata, retaining both
failed and completed clear outcomes. Every terminal action has matching start
identity. All stored events passed `DiagnosticEventV1`; the synthetic secret was
absent. Read-back proves configured state, not a plaintext API comparison. No live
provider call was made. The actual rebuilt native UI verifies the capability fix;
prior full release tests remain historical, and final broad acceptance plus open
Scene/saturated-spool and other performance work remain outstanding.

## Scene overhead attribution and sample isolation

Optional request-stage timing and GC callbacks found all four >50 ms chains in
a new shared-process run overlapped generation-2 collections during generation
(46–62 ms), in both diagnostic modes. Identical process isolation for each sample
retains default GC and all domain/diagnostic assertions; 30 pairs passed the same
50 ms gate at P95 6.23 ms, max 8.28 ms, without measured generation-2 collections.
See [complete methods and both raw populations](../performance/diagnostic-scene-stages-v1.md).
Original failures remain archived. This supplies isolated first-chain evidence
and explains a measured source of cross-sample variance. It makes no long-lived
GC guarantee; remaining domain/native performance acceptance stays open.

## Document → Planning full request-chain overhead

Thirty isolated pairs now upload and actually parse a synthetic one-page text
PDF, reload Document state, generate a mock Learning Plan over its Study Unit,
and reload the saved Plan. Stream evidence and full committed projections agree
with persisted read-back. All 4 operation references resolve to 7 canonical
terminal traces, with Document/Planning parents committed. Every enabled sample
has 25 correlated content-free events and zero drop/read/write failure counts.
The unchanged paired P95 overhead gate passed at 10.92 ms, maximum 12.12 ms.
[Method and raw report](../performance/diagnostic-document-plan-workflow-v1.md)
retain all pairs and stage/GC observations. Text parsing and mock Planning are
measured here; actual OCR recognition and live-provider/tool latency remain
outside this sample. Existing Persona/Scene paths received compatibility smokes.
Study/Tavern, native/rendering and final acceptance continue.

## Tavern direct/facilitated full request-chain overhead

Separate 30-pair isolated populations create Room → run user turn → reload Room
messages → reload Run. Actual mock-provider direct and three-actor facilitated
paths retain real operation admission and canonical commit. Full typed Run and
Message read-backs, actor order, contiguous sequences and diagnostic room/sequence
references match. P95 signed overhead is 5.74 ms direct and 10.26 ms facilitated;
both pass 50 ms. Every enabled sample has zero drops/read/write failures.
[Method and both raw populations](../performance/diagnostic-tavern-workflow-v1.md)
retain all samples and code digests. This does not certify live-provider latency
or reopen separately tested fault paths. Study/native performance remains open.

## Study full request-chain overhead

Thirty isolated pairs create Session → chat → query receipt → reload Session
using actual mock-provider admission/commit. The entire committed receipt and
Session match read-back; Turn ID/sequence, reply, citations and Character Events
agree, with exactly one revision increment and appended Turn. Prerequisite
Document traces are excluded by a pre-chain snapshot. All samples reference one
new committed `study_chat_reply` trace. Enabled emits 16 correlated events with
zero drops/read/write failures. P95 signed overhead is 22.07 ms, maximum 24.87 ms,
passing the unchanged 50 ms gate. [Method/raw report](../performance/diagnostic-study-workflow-v1.md)
retain all samples, stage/GC observations and three source digests. Existing
workflow branches receive compatibility smokes; remaining native/rendering and
final acceptance continue.

## Native sync-overlap experiment rejected

A test-only 30-pair microexperiment overlaps independent counter/event pending
file syncs while keeping both file syncs before publication and the same three
directory barriers. P95 is 18.61 ms overlapping versus 17.88 ms sequential; the
median improvement does not establish a tail benefit. No runtime protocol change
was adopted. [Method and raw report](../performance/diagnostic-native-sync-overlap-v1.md)
retain the experiment's narrow scope; actual saturated emit still has its original
25.21 ms failure against 25 ms. Native/rendering and final acceptance remain open.

## Wide nested event rendering

The existing production React/strict decoder benchmark now has a synthetic nested
profile: all five nested event sections, a 4096-character bounded label and up to
725,309 bytes per 100-row page, accumulating to the actual 500-row cap. Thirty
samples pass the unchanged mount/append/expand/unmount budgets, with P95
50.5/50.7/30.9/34.0 ms. [Method and raw samples](../performance/diagnostic-render-rich-v1.md)
retain exact scope. This covers wide event content, not every schema combination,
separate index/association views or native WebView; no decoder bound is weakened.

## Current release reconciliation

After the workflow/native-clear/rendering additions, `check:release`, all 16 real
Chromium cases and all 11 ordinary native tests passed again on `c20ef1f`, as
recorded at the top. The performance row and remaining checklist now reflect the
completed six backend populations and wide nested-event rendering. The original
candidate storage limit is reconciled with owner-specific enforcement and
recovery exceptions in the linked storage policy; no installation hard-cap claim
is made. Remaining actual blockers are native saturated-spool performance,
native WebView overhead and the final requirement-by-requirement closure audit.
The goal remains active; no top-level completion box is changed by this checkpoint.

## Native WebView overhead completion

The isolated Cargo example uses an actual visible Tauri WebView and the same
production React timeline/strict decoder and extracted measurement functions as
Chromium. Both small and wide nested event populations pass 30-sample gates at
500 rows, with actual viewport/visibility and bundle/native-binary digests.
Rich P95 mount/append/expand/unmount is 51/51/33/35 ms, within unchanged
150/150/100/100 ms budgets. [Method and both raw reports](../performance/diagnostic-native-render-v1.md)
distinguish native engine rendering from production-shell startup and GPU
completion. This closes the named native WebView measurement gap; saturated-spool
I/O and the final requirement closure audit remain open.
