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

The planner receives cleaned study units plus finer outline/detail context. When `GAL_LEARNER_PLAN_PROVIDER=openai`, the planner may call tools such as `get_study_unit_detail` and `read_page_range_content` before returning strict JSON.

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
- `GAL_LEARNER_PLAN_PROVIDER=mock` keeps planning deterministic and local.
- `GAL_LEARNER_PLAN_PROVIDER=openai` enables real model planning through the configured OpenAI-compatible base URL.

## Working Conventions

- Keep the backend/frontend contract aligned through `packages/shared/src/` and the response normalizers in `apps/web/lib/api.ts`.
- For new backend routes, update both `services/ai/app/models/api.py` and the frontend client.
- Preserve the split between:
  - learning UI
  - character shell
  - debug console
- Prefer adding new docs under `docs/` instead of expanding root README into a long design memo.

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
