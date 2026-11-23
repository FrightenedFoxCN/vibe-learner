# 关键入口清单

按子域列出代码入口与所有权。改代码前先在这里定位，再读对应领域文档（见 [docs 索引](README.md) 与 [Harness 工程手册](harness/README.md)）。

- Web app entry: `apps/web/app/page.tsx`
- Debug entry: global `apps/web/components/debug-overlay.tsx`; the old `/debug` page no longer exists.
- Frontend API client: `apps/web/lib/api.ts`
- API router: `services/ai/app/api/routes.py`
- Backend container bootstrap: `services/ai/app/core/bootstrap.py`
- Document OCR checkpoints: `services/ai/app/models/document_checkpoint.py`, `services/ai/app/persistence/document_checkpoint_repository.py`, and `docs/document-checkpoints.md`. Checkpoint-only work does not prove Document commit; resume admits one distinct child operation per source and never replays a completed child.
- Document parsing pipeline: `services/ai/app/services/document_parser.py`
- Document input bounds: `services/ai/app/models/document_input_limits.py`, `services/ai/app/api/document_upload_limit.py`, and `docs/document-input-limits.md`. Keep byte/page preflight before storage/admission; the 1,400-character chunk target is separate from the 65,536-character indivisible-unit limit.
- Document revision/CAS persistence: `services/ai/app/persistence/document_repository.py`; runtime writes must not use `LocalJsonStore.save_list("documents", ...)`.
- Planning physical page scope: `services/ai/app/models/pdf_page_scope.py`, `apps/web/lib/planning-page-scope.ts`, and `docs/planning-page-scope.md`. Physical PDF positions constrain tools/proposals/commits; PDF metadata printed labels are a separate read-only reference.
- Study-unit cleanup and plan heuristics: `services/ai/app/services/study_arrangement.py`
- Study Unit revision confirmation: `services/ai/app/models/study_unit_revision.py`, `services/ai/app/persistence/study_unit_revision_repository.py`, `apps/web/components/study-unit-revision-panel.tsx`, and `docs/study-unit-revision.md`. Planning suggestions never replace the current tool context or shared Document until explicit confirmation.
- Plan revision/CAS: `services/ai/app/persistence/learning_plan_repository.py`, `services/ai/app/services/plan_revision.py`, and `docs/plan-revision.md`.
- Plan prompting and tool context: `services/ai/app/services/plan_prompt.py`
- Model/tool-call planner: `services/ai/app/services/model_provider.py`
- Shared contracts: `packages/shared/src/`
- Harness contracts: `services/ai/app/models/harness.py` and `packages/shared/src/harness.ts`; v1/v2 are read-only compatibility contracts, while v3 is the production contract used by adopted workflows.
- Harness workflow manifest: `services/ai/app/models/harness_manifest.py`, `packages/shared/src/harness-manifest.ts`, and `packages/shared/fixtures/harness/workflow-manifest-v1.json`.
- Harness operation identity: `services/ai/app/models/harness_operation.py`, `services/ai/app/persistence/harness_operation_repository.py`, and `services/ai/alembic/versions/20260825_0013_harness_operation_bindings.py`.
- Harness artifact authorization: `services/ai/app/models/harness_artifact_access.py`, `packages/shared/src/harness-artifact-access.ts`, and the artifact-access fixtures under `packages/shared/fixtures/harness/`.
- Harness protected artifacts and effects: `services/ai/app/persistence/harness_artifact_repository.py`, `services/ai/app/persistence/harness_effect_repository.py`, `services/ai/app/models/harness_effect.py`, and `packages/shared/src/harness-effect.ts`.
- Tool Manifest: `services/ai/app/models/tool_manifest.py`, `services/ai/app/services/tool_provider_projection.py`, `packages/shared/src/tool-manifest.ts`, and `packages/shared/fixtures/harness/tool-manifest-v1.json`.
- Harness eval contracts: `services/ai/app/models/harness_eval.py` and `packages/shared/src/harness-eval.ts`; the eval execution runners and their suite fixtures were removed.
- Operation commit contracts: `services/ai/app/models/tavern_commit.py` and `packages/shared/fixtures/harness/operation-commit-policies-v1.json`.
- Harness engineering guide and source ownership map: `docs/harness/README.md`
- Unified active backlog: `TODO.md`
- Planning/Study output language: `services/ai/app/models/output_language.py`, `services/ai/app/services/output_language.py`, and `docs/output-language.md`. Explicit preferences bind operation identity and save with successful Session commits; source quotations stay verbatim and legacy absent fields preserve fingerprint bytes.
- Versioned performance gates: `docs/performance-budgets-v1.md`
- Populated frontend request-count gates: `docs/performance/web-resource-reads-v1.md`; focus may join owned in-flight reads, while explicit refresh and post-mutation recovery need fresh projection tickets. Do not share a URL-only cache across operation/owner boundaries.
- Harness performance gates: `docs/performance-budgets-v1.md`; run `npm run bench:harness -- --samples 30 --output /tmp/harness-local.json` for provider-free local measurements.
- Tavern contracts and persistence: `services/ai/app/models/tavern.py`, `services/ai/app/persistence/tavern_repository.py`, and `packages/shared/src/tavern.ts`
- Study Session CAS persistence: `services/ai/app/persistence/study_session_repository.py`; new Study Session writes must not return to `LocalJsonStore.save_list("sessions", ...)`.
- Study Chat operation contracts: `services/ai/app/models/study_chat_operation.py`, `services/ai/app/persistence/study_chat_operation_repository.py`, and `apps/web/lib/study-chat-operation-decode.ts`.
- Study browser recovery: `apps/web/hooks/use-study-chat-recovery.ts`, `apps/web/lib/study-request-deadline.ts`, and `docs/study-recovery.md`. Browser timeouts never prove server cancellation; bounded GET recovery must keep the original identity and never replay `uncertain` outcomes.
- Typed effect contracts: `services/ai/app/models/harness_effect.py`, `services/ai/app/models/study_chat_effect.py`, `services/ai/app/services/study_chat_effects.py`, and `packages/shared/src/harness-effect.ts`.
