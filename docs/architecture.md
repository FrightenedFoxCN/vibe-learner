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
- storage: local JSON files under `services/ai/data`
- model planning: mock by default, OpenAI-compatible provider when configured

There is no database, queue, Live2D runtime, or TTS service in the current repository. The codebase is still intentionally small and uses file-backed persistence while the parsing and planning loop is being stabilized.

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
- plan-view mapping helpers in `apps/web/lib/plan-panel-data.ts`
- repeated notices and telemetry helpers in `apps/web/lib/learning-workspace-copy.ts` and `apps/web/lib/learning-workspace-telemetry.ts`

See `docs/frontend-learning-workspace.md` before reshaping this boundary.

### AI Service

The backend is responsible for:

- storing uploaded files and JSON records
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
- `weekly_focus`: ordered main study themes (coarse-grained)
- `today_tasks`: actionable learner tasks

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
- `OPENAI_CHAT_TOOLS_ENABLED`
- `OPENAI_CHAT_MODEL_MULTIMODAL`

This is the main mechanism used to keep plans grounded in OCR-cleaned textbook structure while still allowing a model to inspect details before scheduling.

## Storage Layout

Local storage currently lives under `services/ai/data/`:

- `documents.json`
- `plans.json`
- `study_sessions.json`
- `uploads/`
- `document_debug/`
- `planning_trace/`

This storage model is good enough for a single-user local workflow, but it should be treated as a transitional persistence layer rather than the final architecture.

## Current Constraints

- single-user only
- web-first only
- no auth
- no database
- no background queue
- no Live2D SDK
- no TTS runtime

The code is already shaped to support richer persona and character rendering later, but the current priority remains a reliable textbook-to-plan workflow.
