# AGENTS

## Repo Scan Snapshot

This repository was scanned from the root with `rg --files` on 2026-04-09. The current workspace contains 54 tracked files. The codebase is a small monorepo with three active product surfaces and one docs area:

- `apps/web`: Next.js 16 app-router frontend for upload, debug, plan generation, plan history, and persona-aware study UI.
- `services/ai`: FastAPI backend for document ingestion, OCR parsing, study-unit cleanup, planning, persona APIs, and debug traces.
- `packages/shared`: shared TypeScript contracts used by the frontend.
- `docs`: project docs. Keep architecture and API reference here.

## Key Entry Points

- Web app entry: `apps/web/app/page.tsx`
- Debug page entry: `apps/web/app/debug/page.tsx`
- Frontend API client: `apps/web/lib/api.ts`
- API router: `services/ai/app/api/routes.py`
- Backend container bootstrap: `services/ai/app/core/bootstrap.py`
- Document parsing pipeline: `services/ai/app/services/document_parser.py`
- Study-unit cleanup and plan heuristics: `services/ai/app/services/study_arrangement.py`
- Plan prompting and tool context: `services/ai/app/services/plan_prompt.py`
- Model/tool-call planner: `services/ai/app/services/model_provider.py`
- Shared contracts: `packages/shared/src/`

## Current Runtime Layout

- Frontend runs separately from backend.
- Backend persists local JSON data under `services/ai/data/`.
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

## Configuration Notes

- Python work in this repo is `uv`-first. Do not assume a globally activated virtualenv.
- Planner provider is controlled by `services/ai/.env`.
- `VIBE_LEARNER_PLAN_PROVIDER=mock` keeps planning deterministic and local.
- `VIBE_LEARNER_PLAN_PROVIDER=openai` enables real model planning through the configured OpenAI-compatible base URL.

## Working Conventions

- Keep the backend/frontend contract aligned through `packages/shared/src/` and the response normalizers in `apps/web/lib/api.ts`.
- For new backend routes, update both `services/ai/app/models/api.py` and the frontend client.
- Preserve the split between:
  - learning UI
  - character shell
  - debug console
- Prefer adding new docs under `docs/` instead of expanding root README into a long design memo.

## Page Vocabulary

Use the following standard names when discussing frontend pages and page blocks. Avoid vague terms such as "that panel on the left" when a stable block name exists.

### Page Names

- `/` = `Learning Workspace`
- `/debug` = `Document Debug Console`

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

## Documentation Map

- Project overview: `README.md`
- Docs index: `docs/README.md`
- Architecture: `docs/architecture.md`
- API reference: `docs/api-reference.md`
- Active backlog: `TODO.md`

## Near-Term Risks

- OCR cleanup is still heuristic-heavy and remains the main source of planning noise.
- Tool-enabled planning increases latency and timeout pressure on upstream model providers.
- The frontend now depends on historical debug and plan artifacts; changes to local storage shape should be made carefully.
