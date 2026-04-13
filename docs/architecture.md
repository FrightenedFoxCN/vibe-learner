# Architecture

## Monorepo Structure

- `apps/web`: Next.js 16 frontend. Contains the learner workspace, character shell, `/debug` inspection page, and plan history UI.
- `services/ai`: FastAPI backend. Owns document upload, PDF parsing, OCR fallback, study-unit cleanup, persona APIs, plan generation, and debug trace persistence.
- `packages/shared`: shared TypeScript contracts consumed by the web app.
- `docs`: architecture and API docs for the current implementation.

## Runtime Shape

The current system runs as a local-first split application:

- frontend: `apps/web`
- backend: `services/ai`
- storage: PostgreSQL for structured records plus local file storage under `services/ai/data`
- model planning: mock by default, OpenAI-compatible provider when configured

There is still no queue, Live2D runtime, or TTS service in the current repository. The backend now uses a PostgreSQL-backed ORM persistence layer for business records while keeping uploaded binaries and runtime temp files on local disk.

## Core Boundaries

### Web

The frontend is responsible for:

- upload and process flows
- displaying cleaned study units and generated plans
- rendering persona and character shell state
- showing `/debug` parsing and planner traces
- normalizing backend snake_case payloads into frontend camelCase contracts

The web client should treat the backend as the only source of truth for document processing, plan history, and character events.

Within the `Learning Workspace`, frontend responsibilities are further split into explicit layers:

- page composition in `apps/web/components/learning-workspace.tsx`
- async workflow orchestration in `apps/web/hooks/use-learning-workspace-controller.ts`
- reducer-driven state transitions in `apps/web/lib/learning-workspace-reducer.ts`
- pure state helpers in `apps/web/lib/learning-workspace-state.ts`
- provider-level page-cache persistence in `apps/web/lib/learning-workspace-page-cache.ts`
- plan-view mapping helpers in `apps/web/lib/plan-panel-data.ts`
- repeated notices and telemetry helpers in `apps/web/lib/learning-workspace-copy.ts` and `apps/web/lib/learning-workspace-telemetry.ts`

See `docs/frontend-learning-workspace.md` before reshaping this boundary.

### AI Service

The backend is responsible for:

- storing uploaded files and PostgreSQL-backed structured records
- extracting textbook text from PDF or OCR fallback
- cleaning noisy OCR structure into plannable study units
- generating planning context and planner tool-call traces
- serving persona definitions and character event payloads
- persisting study sessions and learning plans

### Shared Contracts

`packages/shared` holds the frontend-facing contract types for:

- learning records
- persona profiles
- character events

Backend response models still live in Python and must stay aligned with these shared types.

Learning-plan text fields also follow a fixed cross-layer contract:

- `course_title`: generated textbook-grounded plan header title
- `objective`: learner-authored goal shown as supporting metadata
- `overview`: summary paragraph
- `today_tasks`: actionable learner tasks
- `schedule[].title`: primary executable plan directory
- `schedule[].schedule_chapters[].title`: nested learning chapter directory inside each schedule item

See `docs/plan-text-contract.md` before renaming fields or changing which text is rendered as a title versus summary.

## End-To-End Flow

### 1. Document ingestion

`POST /documents` stores the upload and creates a document shell.

### 2. Parsing and cleanup

`POST /documents/{id}/process` or `/process/stream` runs:

1. text extraction
2. OCR fallback when needed
3. section detection
4. chunk generation
5. study-unit cleanup through `StudyArrangementService`

The backend writes:

- a `DocumentRecord`
- a `DocumentDebugRecord`
- derived study units used later for planning

### 3. Plan generation

`POST /learning-plans` or `/learning-plans/stream` runs:

1. heuristic first-pass plan construction
2. model planning pass
3. optional tool calls for finer unit detail or page-range reads
4. filtered schedule application back onto known study units
5. trace persistence under `planning_trace`

### 4. Tutor interaction

`POST /study-sessions` creates a session shell.

`POST /study-sessions/{id}/chat` returns:

- `reply`
- `citations`
- `character_events`

The frontend should never parse roleplay instructions out of plain text. Character performance stays structured.

Current behavior additions:

- frontend routes dialogue by active plan section and reuses historical sessions per plan-section key when available
- chat failures are surfaced explicitly for user retry, rather than hidden by synthetic fallback assistant text
- transcript view is reverse chronological for faster review of recent turns
- `/plan` and `/study` page-local draft state now survives route changes; serializable subsets also recover after same-tab refresh through `sessionStorage`

## Character Layer

The repository already reserves a stable character-event protocol for future richer rendering:

- `emotion`
- `action`
- `intensity`
- `speech_style`
- `scene_hint`
- `line_segment_id`
- `timing_hint`

The frontend currently renders a placeholder character adapter. This preserves the separation needed to later swap in Live2D or TTS without rewriting the study UI.

## Planning Context And Tooling

The planner no longer receives only flat chapter titles. Its model-visible core input is:

- cleaned `study_units`
- a per-unit `detail_map`
- tool access for deeper reads

The `/debug` planning context still exposes `course_outline` for inspection, but the model prompt itself is intentionally centered on cleaned `study_units`.

Current model tools:

- `get_study_unit_detail`
- `read_page_range_content`

Study chat model tools now include:

- `ask_multiple_choice_question`
- `ask_fill_blank_question`
- `read_page_range_content`
- `read_page_range_images` (when chat multimodal mode is enabled and document path is available)

Chat model runtime behavior is configurable through environment variables, including:

- `OPENAI_CHAT_MAX_TOKENS`
- `OPENAI_CHAT_HISTORY_MESSAGES`
- `OPENAI_CHAT_TOOL_MAX_ROUNDS`
- `OPENAI_CHAT_MODEL_MULTIMODAL`

Per-tool enablement is managed by `ModelToolConfig` rather than runtime environment toggles.

OpenAI-compatible requests now also include a transport-level transient retry layer inside `OpenAIModelProvider`:

- retries are limited to network errors, timeouts, and transient upstream HTTP statuses (`408`, `409`, `425`, `500`, `502`, `503`, `504`)
- rate-limit and payload/schema failures are still surfaced directly
- final public error mapping stays unchanged, while stream payloads can expose `retry_attempts` for debug visibility

Additional semantic recovery paths now exist across plan/chat/setting generation:

- content-filter, empty-response, and invalid-structured-output cases may trigger one constrained retry path
- successful recoveries are recorded as typed debug data (`model_recoveries`) and are intended for debug panels only
- unsuccessful recoveries still surface through the ordinary page-level error path

This is the main mechanism used to keep plans grounded in OCR-cleaned textbook structure while still allowing a model to inspect details before scheduling.

## Storage Layout

Structured data now lives in PostgreSQL tables managed through SQLAlchemy and Alembic. Main buckets include:

- `documents`
- `learning_plans`
- `study_sessions`
- `personas`
- `document_debug_records`
- `planning_traces`
- `stream_reports`
- `runtime_settings`
- `model_tool_configs`

Local filesystem storage under `services/ai/data/` is now limited to file-like assets and temp material:

- `uploads/`: uploaded textbook binaries
- `chat_attachments/`: learner chat attachments
- `_tmp/`: OCR/runtime temporary files
- `cache/`: reserved local cache directory

The backend also exposes `/storage/summary` and `/storage/cleanup` so cache and temp layers can be inspected and cleared without touching persistent domain records.

## Current Constraints

- single-user only
- web-first only
- no auth
- no database
- no background queue
- no Live2D SDK
- no TTS runtime

The code is already shaped to support richer persona and character rendering later, but the current priority remains a reliable textbook-to-plan workflow.
