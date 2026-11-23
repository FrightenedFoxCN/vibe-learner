# 工作机制与约定

由原 `AGENTS.md` 的 Working Conventions 全文迁出。AGENTS.md 只保留每次都要遵守的铁律，机制细节在这里。

- Keep the backend/frontend contract aligned through `packages/shared/src/` and the response normalizers in `apps/web/lib/api.ts`.
- Follow `docs/data-flow-layers.md` for missing-data defaults: normalize untrusted shapes only through `app/core/coerce.py`, keep domain models strict, and never re-invent semantic defaults in the frontend decoders.
- For new backend routes, update the appropriate bounded model module (for Tavern, `models/tavern.py`), `apps/web/lib/api.ts`, and `packages/shared/src/`.
- All new workflows and migrated existing model/heuristic workflows must follow the shared Harness lifecycle: typed input, versioned context, strict decode, invariant validation, bounded recovery, atomic commit, and trace/eval coverage.
- Construct v3 context only from an admitted `HarnessOperationBindingV1` and an executable `HarnessWorkflowManifestV1` entry. A manifest registration or context fixture is routing/configuration evidence, not production adoption.
- Allocate Harness identity in the same database transaction as domain operation admission. Never derive it from a provider `tool_call_id`, never fabricate it for legacy rows, and retain the immutable binding as an admission tombstone if product retention removes the domain row.
- Artifact grants use the server-resolved local-installation principal and exact operation/artifact/contract/permission scope; they are not bearer tokens. The resolver authorizes before reading protected content and returns typed retention/digest failures.
- Durable effects use one admitted Harness operation plus a global slot for stable journal identity. Keep adapter/contract/target bindings immutable, use database-clock claim fencing, and require exact read-back or compensation evidence before emitting a terminal outcome; unsupported provider read-back remains `uncertain`.
- The versioned Tool Manifest is the single catalog for all six Planning and thirty-one Study tools. Provider schemas, runtime input/result adapters, redacted trace projections, call ceilings, and provider ID correlation must remain consistent with its shared golden fixture.
- Eval samples bind one admitted Harness operation and complete tested-system configuration. Python owns canonical eval identities/digests; infrastructure, case-data, grader, and metric failures must remain distinct from candidate failures and cannot count as candidate success.
- `HarnessOperationRuntime` owns durable fenced v3 lifecycle state; Tavern identity and Planning tool pilot baselines run in PR checks. Legacy recovery migration is projection-only and fail-closed: it requires a real admitted binding plus existing v3 trace attempt, and post-cutoff legacy rows remain read-only.
- Tavern actor generation and Study Chat resolve authorized protected snapshots before provider execution, emit v3 attempts/checks and terminal traces, and run deterministic held-out eval suites. Historical v1/v2 evidence remains read-only compatibility data.
- V3 commit claims must match a registered full operation key and versioned committed projection. Generic resource evidence is insufficient; the Tavern actor Message policy is `primary_output_only`, not proof of all Room/Run/Step effects in its transaction.
- Tavern persona Messages persist server-only operation/effect receipt metadata atomically. Keep it out of API/OpenAPI, and use `get_actor_commit_read_back` so Message/Run/Step/Participant/reply-anchor evidence comes from one database snapshot.
- Treat Harness as a repository-wide lifecycle. Document/OCR/Study Unit, Planning, Persona/Scene, Study and Tavern have production v3 boundaries and frontend decoders. Remaining work is listed only in `TODO.md`; deterministic regression gates do not make model-quality claims.
- Fix the unsafe write/schema boundary before claiming workflow adoption: Study follows concurrent-safe append → operation admission/receipt → typed effect schema → effect commit/staging → v3 trace/eval; Document and Planning have durable admission, atomic committed projections and v3 lifecycle evidence; Scene keeps model proposal, user-authored save, committed projection and API DTO separate.
- Study Session revision and turn sequence are application-owned committed state. Keep them out of Study Chat/model proposal schemas; Session CAS is concurrency infrastructure, not durable request admission or successful Harness commit evidence.
- Interactive Question grading material must remain server-only before submission. Keep model proposal, grading spec, public prompt, committed result, and Turn-bound attempt input separate; the browser must render only persisted Session read-back.
- UX/reliability findings require independent revalidation before closure; developer-authored happy-path tests alone are insufficient.
- Treat `HarnessStage`, `HarnessAttemptPhase`, and stream event types as separate vocabularies. Stages are domain operations such as page extraction or one planning tool execution; generate/decode/validate/repair/commit/rollback are phases inside a stage; progress names such as `page_parsed` are stream events. Keep the Python/TypeScript operation-stage registry and its shared golden fixture atomic.
- An application component contract versions reviewed algorithm behavior; it is not a dependency/model version. An unaudited component uses a null registration and blocks context construction—never invent `pending-*`, `latest`, `unknown`, or a package version as adoption evidence.
- Only digest explicitly reviewed `HarnessSafeManifest` DTOs. User/document/prompt/transcript content belongs behind an authorized artifact resolver; SHA-256 is integrity evidence, not confidentiality or replay availability. Python is the canonical digest authority until a cross-language canonical-bytes contract is added.
- Keep model/heuristic proposals separate from committed records and API responses. Use domain-owned proposal models and the ownership rules here; generated IDs, identity, ordering, revisions, timestamps and committed state effects must not enter model-owned proposal schemas.
- Preserve the split between:
  - learning UI
  - character shell
  - debug console
- Prefer adding new docs under `docs/` instead of expanding root README into a long design memo.
