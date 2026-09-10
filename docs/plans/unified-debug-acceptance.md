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
| Resources and full association filtering | Persona save/update emits saved identity/revision; operation links and timeline drilldown work | Canonical index projections and resource type/ID/role filters now cover the shared Harness vocabulary. Direct event references still only emit Persona saves; cross-domain event associations and flow acceptance remain. Do not infer committed identity from URL parameters or HTTP success. |
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
