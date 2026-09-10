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
| Physical disk budget, cleanup and restart recovery | Incremental vacuum/checkpoint, guarded 128 MiB event and 64 MiB index admission; low-budget pinned-reader tests | Cooperating local Python writers are guarded. Pre-existing oversized database recovery and installation-wide accounting/certification still need completion. |
| Desktop spool process/crash behavior | Shared file lock, 256-file/4 MiB ring, modification-time expiry, atomic counter checkpoint, `.pending` recovery, two-process Rust tests | Local Unix evidence exists. Counter lower bounds, unknown files, legacy metadata and Windows/directory-sync limits remain explicit; spool is still unmeasured in the storage DTO. |
| Offline, crash, write failure, overflow, duplicates and large volume | Browser retry/overflow tests; writer/spool/quota tests; real process crash tests; 12,000-event benchmark | Substantial fault evidence exists. Complete a consolidated requirement-to-test audit, including any uncovered mixed/restart scenarios; don't close from happy-path samples. |
| Performance overhead measurement | Reproducible local baseline and post-quota raw reports under `docs/performance/` | Server middleware/storage/query/export measured. Full-feature/native/browser collection/render overhead and justified acceptance gates remain unverified. |

## Completion sequence retained

1. Complete the diagnostic resource vocabulary/associations and logical-flow
   wiring, then validate each named product flow through its real boundaries.
2. Complete old oversize recovery and spool/installation accounting, retaining
   safe refusal and explicit loss evidence through crash/restart.
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
