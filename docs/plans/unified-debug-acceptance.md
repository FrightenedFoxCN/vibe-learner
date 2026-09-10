# Unified Debug implementation and acceptance checkpoint

This is a requirement audit of [the active plan](unified-debug.md), not a
replacement scope. The overall goal remains active. Independent quality review
is deferred as requested; implementer tests are not presented as that review.

## Verified release checkpoint

Code revision: `8fdf4f1fe461704c1048a4c6daa777264ba2a8ae`.
On 2026-09-10, `npm run check:release` exited successfully:

- Shared contracts and Web type/reliability gates passed.
- All 13 Harness PR suites passed (three pilots and ten stage regressions).
- All 715 backend tests passed in 58.715 seconds.
- Production Next.js build passed.

This gate does not run native tests or certify all diagnostic interaction chains.
The immediately preceding spool slice separately passed all 10 Rust library
tests, including actual sidecar subprocess exits and concurrent native writers.
The production Chromium diagnostic suite most recently passed all three
scenarios in the storage-state slice. The user's unrelated icon modification is
excluded from implementation commits and this change-scope claim.

## Requirement audit

| Plan requirement | Current evidence | Remaining work / conclusion |
| --- | --- | --- |
| Shared event identities, safe fields, classification and bounded browser/server collection | `models/diagnostic.py`, `packages/shared/src/diagnostic.ts`, classification fixtures; diagnostic/query tests | Foundation implemented; it remains the only completed top-level item. |
| Persona generate → save → reload correlation with Debug closed | `persona-diagnostics.test.jsx`, `diagnostics-live.spec.ts` real mock-backend Chromium chain | Verified for that chain; not evidence for every other feature. |
| All workflow/stage and terminal Harness references | `harness_runtime.py`, `harness_broad_adoption.py`, restartable `diagnostic_index.py`; index/runtime and 13 Harness suites | Shared hooks exist. Per-workflow diagnostic-chain acceptance still needed for Document/OCR/cleanup, Planning, Scene, Study/question/attachment and Tavern. |
| Logical action/flow correlation across requests and navigation | Default `diagnosticFetch` creates a request action context; Persona draft owns an explicit flow; Settings/Vault/import/export adapters exist | Audit other controllers' multi-request actions. A default per-request context with null flow does not prove one logical user flow is correlated. |
| Resources and full association filtering | Persona/Scene/Document/Plan/Session/Tavern saved-resource references; canonical index and request drilldown | Canonical index projections and resource type/ID/role filters now cover the shared Harness vocabulary. Direct event references cover main saved-resource boundaries across these domains. Full fault/alternate-flow acceptance remains. Do not infer committed identity from URL parameters or HTTP success. |
| Provider/tool timing, usage, recovery and missing evidence | Provider parent/attempt spans; 6 Planning and 31 Study tools; audit fixtures/tests | Implemented bounded telemetry with explicit missing cost/endpoint/context evidence. Existing missing-evidence labels must remain honest. |
| Settings/Vault/import/export and desktop lifecycle | Local action adapters; bounded native spool; Python consumer; real sidecar subprocess tests | Actual native Vault create/unlock/save/read-back and native save-dialog acceptance remain unverified. Frontend unavailable/locked-path tests do not establish successful native behavior. |
| Independent DebugProvider and page-view ownership | `debug-provider.tsx`, `owned-debug-snapshot.tsx`, StrictMode/unmount/route tests and Chromium navigation | Implemented and locally verified. Full task closure still depends on the unfinished flow coverage. |
| Global filters, lazy queries, stale-response fencing and association drilldown | Timeline/query hooks, strict schemas, component tests, Chromium operation → request → events, 390px screenshots | Implemented for current filter/resource vocabulary; resource scope above remains incomplete. |
| Retention, pagination, export and statistics | Event/link/index retention, writer epochs, pinned snapshot export, audit observations and P50/P95; browser downloads | Implemented slices with explicit gaps. No generic full-history or business-commit certification is made. |
| Physical disk budget, cleanup and restart recovery | Incremental vacuum/checkpoint, guarded 128 MiB event and 64 MiB index admission; low-budget pinned-reader tests | Cooperating local Python writers are guarded. Bounded in-place legacy recovery now has startup/crash evidence; sources outside its workspace envelope defer safely. Installation-wide accounting/certification remains unfinished. |
| Desktop spool process/crash behavior | Shared file lock, 256-file/4 MiB ring, modification-time expiry, atomic counter checkpoint, `.pending` recovery, two-process Rust tests | Local Unix evidence exists. Counter lower bounds, unknown files, legacy metadata and Windows/directory-sync limits remain explicit; spool now has bounded file-length observations; installation-wide accounting remains unfinished. |
| Offline, crash, write failure, overflow, duplicates and large volume | Browser retry/overflow tests; writer/spool/quota tests; real process crash tests; 12,000-event benchmark | Substantial fault evidence exists. Complete a consolidated requirement-to-test audit, including any uncovered mixed/restart scenarios; don't close from happy-path samples. |
| Performance overhead measurement | Reproducible local baseline and post-quota raw reports under `docs/performance/` | Server middleware/storage/query/export measured. Full-feature/native/browser collection/render overhead and justified acceptance gates remain unverified. |

## Completion sequence retained

1. Complete the diagnostic resource vocabulary/associations and logical-flow
   wiring, then validate each named product flow through its real boundaries.
2. Complete installation accounting and validate the combined storage envelope,
   retaining bounded legacy recovery, safe refusal and explicit crash/restart loss evidence.
3. Exercise the successful native Vault/export paths and measure the remaining
   frontend/native overhead within their actual platform scope.
4. Re-run the necessary broad gates after those changes and repeat this audit.
   Keep deferred independent review separate from implementer verification.

No top-level task is closed by this checkpoint. Full test/build success is a
regression result; the missing acceptance items above remain required work.

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
