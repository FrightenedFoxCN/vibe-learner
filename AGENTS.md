# AGENTS

## Repo Scan Snapshot

This repository was rescanned from the root on 2026-08-12. The current workspace contains roughly 244 tracked and in-flight project files. The codebase is a monorepo with four active product/runtime surfaces and one docs area:

- `apps/web`: Next.js 16 app-router frontend for upload, debug, plan generation, plan history, and persona-aware study UI.
- `services/ai`: FastAPI backend for document ingestion, OCR parsing, study-unit cleanup, planning, persona APIs, and debug traces.
- `packages/shared`: shared TypeScript contracts used by the frontend.
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
- Harness contracts: `services/ai/app/models/harness.py` and `packages/shared/src/harness.ts`
- Tavern contracts and persistence: `services/ai/app/models/tavern.py`, `services/ai/app/persistence/tavern_repository.py`, and `packages/shared/src/tavern.ts`

## Current Runtime Layout

- Frontend runs separately from backend.
- Backend defaults to local SQLite and can use PostgreSQL through `DATABASE_URL`.
- `LocalJsonStore` is now a compatibility/database wrapper and still mirrors several legacy aggregates to JSON under `services/ai/data/`; do not route new append-heavy domains through `save_list`.
- Uploaded files are stored under `services/ai/data/uploads/`.
- Document debug artifacts live under `services/ai/data/document_debug/`.
- Planning traces live under `services/ai/data/planning_trace/`.

## Main Flows

### 1. Document parsing

`POST /documents` -> `POST /documents/{id}/process` or `POST /documents/{id}/process/stream`

The backend creates a local document record, parses the uploaded PDF, falls back to OCR when needed, strips noisy structure, builds study units, and stores a debug record for replay and inspection.

### 2. Planning

`GET /documents/{id}/planning-context` -> `POST /learning-plans` or `POST /learning-plans/stream`

The planner receives cleaned study units plus finer outline/detail context. When `VIBE_LEARNER_PLAN_PROVIDER=openai`, the planner may call tools such as `get_study_unit_detail` and `read_page_range_content` before returning strict JSON.

### 3. Study interaction

`POST /study-sessions` -> `POST /study-sessions/{id}/chat`

The frontend consumes structured chat replies with citations and `character_events`, not free-form roleplay text parsing.

### 4. Tavern interaction (active implementation)

Tavern is a separate domain from Study Session. Its normalized schema uses `tavern_rooms`, `tavern_participants`, `tavern_messages`, `tavern_runs`, and `tavern_run_steps`; messages are append-only and use a per-room sequence. Direct and facilitated runs are active. Facilitated targets are a set; the server schedules them by participant `display_order`, commits each validated actor separately, and records partial/failed/blocked steps for scoped child retry. Do not add Tavern fields to `StudySessionRecord`.

Read `docs/tavern-architecture.md` and `docs/harness-engineering.md` before modifying Tavern or reliability behavior.

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

## Configuration Notes

- Python work in this repo is `uv`-first. Do not assume a globally activated virtualenv.
- Planner provider is controlled by `services/ai/.env`.
- `VIBE_LEARNER_PLAN_PROVIDER=mock` keeps planning deterministic and local.
- `VIBE_LEARNER_PLAN_PROVIDER=openai` enables real model planning through the configured OpenAI-compatible base URL.

## Working Conventions

- Keep the backend/frontend contract aligned through `packages/shared/src/` and the response normalizers in `apps/web/lib/api.ts`.
- For new backend routes, update the appropriate bounded model module (for Tavern, `models/tavern.py`), `apps/web/lib/api.ts`, and `packages/shared/src/`.
- New model/heuristic workflows must follow the shared Harness lifecycle: typed input, versioned context, strict decode, invariant validation, bounded recovery, atomic commit, and trace/eval coverage.
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
- `/tavern` = `Tavern Workspace` (backend active; frontend page pending `UX-001`)
- Debug is a global overlay, not a standalone page.

### `Tavern Workspace` Block Names

- `Tavern Header`: page title, active room title, create action, and status.
- `Tavern Session Panel`: recent rooms, resume, archive, and room management.
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
- Use `Sidebar` only for the left document list in `/debug`.
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
- Tavern architecture: `docs/tavern-architecture.md`
- Active backlog: `TODO.md`

## Near-Term Risks

- OCR cleanup is still heuristic-heavy and remains the main source of planning noise.
- Tool-enabled planning increases latency and timeout pressure on upstream model providers.
- The frontend now depends on historical debug and plan artifacts; changes to local storage shape should be made carefully.
- Existing Study Session writes use aggregate read-modify-write and can lose concurrent turns; do not reuse that path for Tavern.
- `npm run lint:web` is currently invalid under Next.js 16 and is tracked as `QG-001`.
