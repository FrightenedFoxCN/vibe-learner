# AGENTS

## Repo Scan Snapshot

This repository was last materially updated on 2026-09-03. The codebase is a monorepo with four active product/runtime surfaces and one docs area:

- `apps/web`: Next.js 16 app-router frontend for upload, global debug, planning, study, persona/scene editing, and Tavern interaction.
- `services/ai`: FastAPI backend for document ingestion, OCR parsing, Study Unit cleanup, planning, persona/scene APIs, Study Chat, Tavern orchestration, and Harness evidence.
- `packages/shared`: shared TypeScript contracts used by the frontend, including Tavern and Harness projections.
- `apps/desktop`: Tauri 2 desktop shell, bundle scripts, icons, and Rust sidecar integration.
- `docs`: project docs. Keep architecture and API reference here.

## Key Entry Points

- Web app entry: `apps/web/app/page.tsx`
- Debug entry: global `apps/web/components/debug-overlay.tsx`; the old `/debug` page no longer exists.
- Frontend API client: `apps/web/lib/api.ts`
- API router: `services/ai/app/api/routes.py`
- Backend container bootstrap: `services/ai/app/core/bootstrap.py`
- Document parsing pipeline: `services/ai/app/services/document_parser.py`
- Study-unit cleanup and plan heuristics: `services/ai/app/services/study_arrangement.py`
- Plan prompting and tool context: `services/ai/app/services/plan_prompt.py`
- Model/tool-call planner: `services/ai/app/services/model_provider.py`
- Shared contracts: `packages/shared/src/`
- Harness contracts: `services/ai/app/models/harness.py` and `packages/shared/src/harness.ts`; v1/v2 are compatibility contracts, while v3 is the hardened context target for future workflow adoption.
- Harness workflow manifest: `services/ai/app/models/harness_manifest.py`, `packages/shared/src/harness-manifest.ts`, and `packages/shared/fixtures/harness/workflow-manifest-v1.json`.
- Harness operation identity: `services/ai/app/models/harness_operation.py`, `services/ai/app/persistence/harness_operation_repository.py`, and `services/ai/alembic/versions/20260825_0013_harness_operation_bindings.py`.
- Harness artifact authorization: `services/ai/app/models/harness_artifact_access.py`, `packages/shared/src/harness-artifact-access.ts`, and the artifact-access fixtures under `packages/shared/fixtures/harness/`.
- Harness protected artifacts and effects: `services/ai/app/persistence/harness_artifact_repository.py`, `services/ai/app/persistence/harness_effect_repository.py`, `services/ai/app/models/harness_effect.py`, and `packages/shared/src/harness-effect.ts`.
- Tool Manifest: `services/ai/app/models/tool_manifest.py`, `services/ai/app/services/tool_provider_projection.py`, `packages/shared/src/tool-manifest.ts`, and `packages/shared/fixtures/harness/tool-manifest-v1.json`.
- Harness eval contracts: `services/ai/app/models/harness_eval.py`, `packages/shared/src/harness-eval.ts`, and the eval contract/taxonomy fixtures under `packages/shared/fixtures/harness/`.
- Harness eval execution: `services/ai/app/services/harness_eval_runner.py`; use `npm run eval:harness` with an explicit registry and selected suite, or its `:pr`, `:manual`, and `:nightly` profile aliases.
- Operation commit contracts: `services/ai/app/models/tavern_commit.py` and `packages/shared/fixtures/harness/operation-commit-policies-v1.json`.
- Harness schema ownership: `docs/harness-schema-ownership.md`
- Harness active roadmap: `docs/harness-roadmap.md`
- Versioned performance gates: `docs/performance-budgets-v1.md`
- Tavern contracts and persistence: `services/ai/app/models/tavern.py`, `services/ai/app/persistence/tavern_repository.py`, and `packages/shared/src/tavern.ts`
- Study Session CAS persistence: `services/ai/app/persistence/study_session_repository.py`; new Study Session writes must not return to `LocalJsonStore.save_list("sessions", ...)`.
- Study Chat operation contracts: `services/ai/app/models/study_chat_operation.py`, `services/ai/app/persistence/study_chat_operation_repository.py`, and `apps/web/lib/study-chat-operation-decode.ts`.
- Typed effect contracts: `services/ai/app/models/harness_effect.py`, `services/ai/app/models/study_chat_effect.py`, `services/ai/app/services/study_chat_effects.py`, and `packages/shared/src/harness-effect.ts`.

## Current Runtime Layout

- Frontend runs separately from backend.
- Backend defaults to local SQLite and can use PostgreSQL through `DATABASE_URL`.
- `LocalJsonStore` is now a compatibility/database wrapper and still mirrors several legacy aggregates to JSON under `services/ai/data/`; do not route new append-heavy domains through `save_list`. For Study Sessions specifically, `save_list("sessions")` is insert-only legacy import, rejects same-ID divergence, and never replaces/deletes runtime rows.
- Study Sessions are database-authoritative. The legacy `sessions.json` is import compatibility only; normal Session writes use row CAS and do not synchronously rewrite the full JSON list.
- Uploaded files are stored under `services/ai/data/uploads/`.
- Document debug artifacts live under `services/ai/data/document_debug/`.
- Planning traces live under `services/ai/data/planning_trace/`.

## Main Flows

### 1. Document parsing

`POST /documents` -> `POST /documents/{id}/process` or `POST /documents/{id}/process/stream`

The backend creates a local document record, parses the uploaded PDF, falls back to OCR when needed, strips noisy structure, builds study units, and stores a debug record for replay and inspection.

### 2. Planning

`GET /documents/{id}/planning-context` -> `POST /learning-plans` or `POST /learning-plans/stream`

The planner receives cleaned study units plus finer outline/detail context. With the real LiteLLM provider enabled (legacy `openai` configuration is normalized to `litellm`), it may call any configured member of the six-tool Planning catalog before returning a strict `LearningPlanProposalV1`.

### 3. Study interaction

`POST /study-sessions` -> `POST /study-sessions/{id}/chat`

The frontend consumes structured chat replies with citations and `character_events`, not free-form roleplay text parsing. Chat requests use durable operation admission and query-only recovery for ambiguous outcomes. All currently registered Study database effects share the final Turn/Session transaction; Scene mutation and operation-owned attachment staging have separate strict commit/read-back or compensation boundaries, while upstream provider calls remain `uncertain` without provider idempotency/read-back. Interactive-question UX waits for persisted Session read-back and never receives the server-only grading specification; its wire, corruption, concurrency, idempotency, and legacy-migration gates have passed independent revalidation, while the broader Study v3/live-decoder boundary remains open.

### 4. Tavern interaction (active implementation)

Tavern is a separate domain from Study Session. Its normalized schema uses `tavern_rooms`, `tavern_participants`, `tavern_messages`, `tavern_runs`, and `tavern_run_steps`; messages are append-only and use a per-room sequence. Direct and facilitated runs are active. Facilitated targets are a set; the server schedules them by participant `display_order`, commits each validated actor separately, and records partial/failed/blocked steps for scoped child retry. Generating steps use database-clock leases, heartbeat renewal, owner/claim fencing, and at most three claims. Cancel immediately fences persistence and later recovery calls; an already-issued synchronous provider request is best-effort and may run until its own timeout. Do not add Tavern fields to `StudySessionRecord`.

Read `docs/harness-engineering.md` and `docs/harness-schema-ownership.md` before modifying any reliability or model-owned schema boundary. Also read `docs/tavern-architecture.md` for Tavern changes.

## Local Development Commands

Install JavaScript dependencies from repo root:

```bash
npm install
```

Install backend dependencies with `uv`:

```bash
cd services/ai
uv sync
```

Run the frontend:

```bash
npm run dev:web
```

Run the backend:

```bash
cd services/ai
uv run uvicorn app.main:app --reload
```

Run backend tests:

```bash
npm run test:ai
```

Build the frontend:

```bash
npm run build:web
```

Targeted Tavern schema tests:

```bash
cd services/ai
uv run python -m unittest tests.test_tavern_schema
```

Targeted Tavern runtime tests:

```bash
cd services/ai
uv run python -m unittest tests.test_tavern_api tests.test_tavern_facilitated
```

Tavern frontend state and strict-decoder tests:

```bash
npm run test:web:tavern
```

Repository frontend reliability tests, including Tavern and the domain-owned
Document, Planning, Persona/Scene, Study, and stream decoders:

```bash
npm run test:web:reliability
```

The Study decoder validates Session/Turn identity and ordering plus current
citations, Character Events, attachments, interactive-question projections,
projected state, and committed chat-operation read-back. Its independent live
wire gate and the still-private effect-batch receipt boundary remain open.

Run the optional live-backend decoder acceptance against a populated local service. The database must already contain a Tavern room with messages and at least one terminal run; without `TAVERN_TEST_API_URL` this case is intentionally skipped:

```bash
TAVERN_TEST_API_URL=http://127.0.0.1:8000 npm run test:web:tavern
```

## Configuration Notes

- Python work in this repo is `uv`-first. Do not assume a globally activated virtualenv.
- Planner provider defaults come from `services/ai/.env`; database-authoritative runtime settings can override them without a restart.
- `VIBE_LEARNER_PLAN_PROVIDER=mock` keeps planning deterministic and local.
- `VIBE_LEARNER_PLAN_PROVIDER=litellm` enables real model planning through the configured OpenAI-compatible base URL; `openai` remains a normalized compatibility alias.

## Working Conventions

- Keep the backend/frontend contract aligned through `packages/shared/src/` and the response normalizers in `apps/web/lib/api.ts`.
- For new backend routes, update the appropriate bounded model module (for Tavern, `models/tavern.py`), `apps/web/lib/api.ts`, and `packages/shared/src/`.
- All new workflows and migrated existing model/heuristic workflows must follow the shared Harness lifecycle: typed input, versioned context, strict decode, invariant validation, bounded recovery, atomic commit, and trace/eval coverage.
- Construct v3 context only from an admitted `HarnessOperationBindingV1` and an executable `HarnessWorkflowManifestV1` entry. A manifest registration or context fixture is routing/configuration evidence, not production adoption.
- Allocate Harness identity in the same database transaction as domain operation admission. Never derive it from a provider `tool_call_id`, never fabricate it for legacy rows, and retain the immutable binding as an admission tombstone if product retention removes the domain row.
- Artifact grants use the server-resolved local-installation principal and exact operation/artifact/contract/permission scope; they are not bearer tokens. The resolver authorizes before reading protected content and returns typed retention/digest failures.
- Durable effects use one admitted Harness operation plus a global slot for stable journal identity. Keep adapter/contract/target bindings immutable, use database-clock claim fencing, and require exact read-back or compensation evidence before emitting a terminal outcome; unsupported provider read-back remains `uncertain`.
- The versioned Tool Manifest is the single catalog for all six Planning and thirty-one Study tools. Provider schemas, runtime input/result adapters, redacted trace projections, call ceilings, and provider ID correlation must remain consistent with its shared golden fixture.
- Eval samples bind one admitted Harness operation and complete tested-system configuration. Python owns canonical eval identities/digests; infrastructure, case-data, grader, and metric failures must remain distinct from candidate failures and cannot count as candidate success.
- V3 commit claims must match a registered full operation key and versioned committed projection. Generic resource evidence is insufficient; the Tavern actor Message policy is `primary_output_only`, not proof of all Room/Run/Step effects in its transaction.
- Tavern persona Messages persist server-only operation/effect receipt metadata atomically. Keep it out of API/OpenAPI, and use `get_actor_commit_read_back` so Message/Run/Step/Participant/reply-anchor evidence comes from one database snapshot.
- Treat Harness as a repository-wide lifecycle, not a Tavern feature. `build_harness_context` and v3 fixtures are foundation only; do not mark Document/OCR/Study Unit/Planning/Persona/Scene/Study Chat/Tavern/Frontend Decode adopted until their own `docs/harness-roadmap.md` gates pass.
- Fix the unsafe write/schema boundary before claiming workflow adoption: Study follows concurrent-safe append → operation admission/receipt → typed effect schema → effect commit/staging → v3 trace/eval; Document and Planning now have durable admission plus atomic committed projections but still need their own v3 lifecycle evidence; Scene separates model proposal, user-authored save, committed projection, and API DTO before Harness adoption.
- Study Session revision and turn sequence are application-owned committed state. Keep them out of Study Chat/model proposal schemas; Session CAS is concurrency infrastructure, not durable request admission or successful Harness commit evidence.
- Interactive Question grading material must remain server-only before submission. Keep model proposal, grading spec, public prompt, committed result, and Turn-bound attempt input separate; the browser must render only persisted Session read-back.
- UX/reliability findings require independent revalidation before closure; developer-authored happy-path tests alone are insufficient.
- Treat `HarnessStage`, `HarnessAttemptPhase`, and stream event types as separate vocabularies. Stages are domain operations such as page extraction or one planning tool execution; generate/decode/validate/repair/commit/rollback are phases inside a stage; progress names such as `page_parsed` are stream events. Keep the Python/TypeScript operation-stage registry and its shared golden fixture atomic.
- An application component contract versions reviewed algorithm behavior; it is not a dependency/model version. An unaudited component uses a null registration and blocks context construction—never invent `pending-*`, `latest`, `unknown`, or a package version as adoption evidence.
- Only digest explicitly reviewed `HarnessSafeManifest` DTOs. User/document/prompt/transcript content belongs behind an authorized artifact resolver; SHA-256 is integrity evidence, not confidentiality or replay availability. Python is the canonical digest authority until a cross-language canonical-bytes contract is added.
- Keep model/heuristic proposals separate from committed records and API responses. Read the ownership registry before allowing generated IDs, identity, ordering, revisions, timestamps, or state effects into a proposal schema.
- Keep application-owned IDs, speaker identity, revision, sequence, and committed state effects out of model-owned schemas.
- Preserve the split between:
  - learning UI
  - character shell
  - debug console
- Prefer adding new docs under `docs/` instead of expanding root README into a long design memo.

## Page Vocabulary

Use the following standard names when discussing frontend pages and page blocks. Avoid vague terms such as "that panel on the left" when a stable block name exists.

### Page Names

- `/` = `Navigation Home`
- `/plan` = `Plan Workspace`
- `/study` = `Study Dialog`
- `/persona-spectrum` = `Persona Spectrum`
- `/scene-setup` = `Scene Setup`
- `/tavern` = `Tavern Workspace` (frontend and backend active)
- Debug is a global overlay, not a standalone page.

### `Tavern Workspace` Block Names

- `Tavern Header`: page title, active room title, create action, and status.
- `Tavern Session Panel`: recent rooms and room switching. Archive/restore is currently in `Tavern Header`; broader room management remains backlog work.
- `Tavern Setup Panel`: persona multi-select, optional scene, title, and room creation.
- `Tavern Conversation Panel`: ordered user/director/persona/system transcript.
- `Participant Roster`: cast, target selection, and per-persona generation state.
- `Interaction Composer`: visible message, optional next-round guidance, recipient preview, and send/stop actions.
- `Reliability Details`: collapsed user-readable Harness recovery summary; raw trace belongs in debug UI.

### `Learning Workspace` Block Names

- `Hero Header`: the top banner area in `apps/web/components/learning-workspace.tsx` with product title, status notice, and debug link.
- `Persona Selector`: the persona dropdown block rendered by `apps/web/components/persona-selector.tsx`.
- `Study Column`: the main left-column flow container on the home page.
- `Document Setup Panel`: the upload-and-generate block rendered by `apps/web/components/document-setup.tsx`.
- `Plan History Panel`: the historical plan selection block rendered by `apps/web/components/plan-history.tsx`.
- `Plan Overview Panel`: the current plan summary block inside `LearningWorkspace`, showing overview, main themes, and today tasks.
- `Study Console`: the chapter chat/request block rendered by `apps/web/components/study-console.tsx`.
- `Character Shell`: the right-column teacher/persona block rendered by `apps/web/components/character-shell.tsx`.
- `Character Event Snapshot`: the JSON event preview area inside `Character Shell`.

### `Document Debug Console` Block Names

- `Debug Hero Header`: the top banner with page title, current status message, and back link.
- `Document List Sidebar`: the left-side document picker.
- `Parse Summary Card`: the summary block titled `解析摘要`.
- `Process Stream Panel`: the block titled `流式处理反馈`.
- `Plan Stream Panel`: the block titled `流式生成学习计划`.
- `Section Guess Panel`: the block titled `章节猜测`.
- `Study Unit Cleanup Panel`: the block titled `学习编排清洗结果`.
- `Planning Outline Panel`: the block titled `计划输入目录`.
- `Planning Tools Panel`: the block titled `计划工具与章节详情`.
- `Planning Trace Panel`: the block titled `计划模型 Trace`.
- `Parse Warning Panel`: the block titled `解析告警`.
- `Chunk Inspector Panel`: the block titled `切块结果`.
- `Page Extraction Panel`: the block titled `逐页抽取`.

### Naming Rules

- Use `Panel` for standalone content cards inside a page.
- Use `Header` for the top banner area of a page.
- Use `Sidebar` only for the document picker inside the global `Document Debug Console` overlay.
- Use `Shell` only for the persona/character container, not for ordinary study cards.
- Use `Study Unit` for cleaned planning units, not `section`, unless referring to raw parser-detected `sections`.
- Use `Section` for raw parse structure or cited textbook structure.

### Data-Term Mapping

- `Document`: uploaded textbook file plus derived processing status.
- `Section`: raw parser-detected chapter/subchapter structure in debug artifacts.
- `Study Unit`: cleaned planning unit derived from sections and OCR text cleanup.
- `Learning Plan`: persisted planner output.
- `Study Session`: interactive tutor session bound to one document, persona, and active section.
- `Character Event`: structured performance instruction consumed by the character layer.
- `Tavern Room`: durable free-interaction container with an optional scene and persona snapshots.
- `Tavern Participant`: room-scoped immutable persona snapshot plus prompt hash.
- `Tavern Message`: append-only attributed message with a monotonic room sequence.
- `Tavern Run`: idempotent, revision-checked generation attempt with a server-owned schedule, normalized speaker steps, context digest, and Harness traces.
- `Tavern Speaker Step`: one scheduled persona attempt with pending/generating/completed/failed/blocked state and a reply anchor.
- `Harness Trace`: workflow-neutral validate/repair evidence; it applies across parsing, planning, generation, study, Tavern, and frontend decoding.

## Documentation Map

- Project overview: `README.md`
- Docs index: `docs/README.md`
- Architecture: `docs/architecture.md`
- API reference: `docs/api-reference.md`
- Harness engineering: `docs/harness-engineering.md`
- Harness schema ownership: `docs/harness-schema-ownership.md`
- Harness active roadmap: `docs/harness-roadmap.md`
- Tavern architecture: `docs/tavern-architecture.md`
- Active product backlog: `TODO.md`

## Near-Term Risks

- OCR cleanup is still heuristic-heavy and remains the main source of planning noise.
- Tool-enabled planning increases latency and timeout pressure on upstream model providers.
- The frontend now depends on historical debug and plan artifacts; changes to local storage shape should be made carefully.
- Study Session aggregate writes use revision CAS and contiguous turn sequencing; compatibility reads share repository projection validation, and committed Turn content is immutable except the dedicated interactive-answer fields. Study Chat has durable request admission plus typed DB/Scene/file-effect slices, while provider-call exactly-once and workflow v3 evidence remain open. Tavern keeps its separate normalized Room/Run/Step/Message repository.
- Most production workflows still predate the v3 Harness runtime. Do not infer repository-wide adoption from the Tavern v1 path or the v2/v3 schema fixtures.
- Harness resource references need evidence policies; never pass a constant `revision=0` for a resource that has no authoritative revision.
- Use `HARNESS_RESOURCE_EVIDENCE_POLICIES` before constructing v3 context or commit evidence. A Tavern Room revision covers metadata and run-admission CAS, not transcript drift; a Tavern Message is currently unsupported as a context subject until a room-scoped protected transcript snapshot can be resolved. One committed Tavern Message uses one room-scoped sequence point, never a range. Unsupported resources may appear as honest `not_committed` attempts but cannot claim committed or rolled-back proof.
- Resource evidence policy validates generic proof shape, not operation truth. Production v3 commit evidence must match a registered workflow/stage/output/payload key, an allowed resource set, and a versioned committed-projection DTO that proves all application-owned scope fields. The current Tavern actor policy proves one committed Message as `primary_output_only`, not every Room/Run/Step side effect.
- Use `npm run check` for shared/Web reliability and type gates, and `npm run check:release` for the full backend test plus production Web build gate. `npm run lint:web` is only a compatibility alias.
