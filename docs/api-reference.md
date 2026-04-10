# API Reference

## Base URL

- Local backend default: `http://127.0.0.1:8000`
- Frontend reads `NEXT_PUBLIC_AI_BASE_URL`
- No authentication is implemented in v1

## Response Conventions

- Standard endpoints return JSON.
- Streaming endpoints return `application/x-ndjson`.
- Error payloads from FastAPI follow `{"detail": ...}`.
- Frontend normalization is implemented in `apps/web/lib/api.ts`.

## Health

### `GET /health`

Returns:

```json
{
  "status": "ok"
}
```

## Personas

### `GET /personas`

Returns all builtin and user-created persona profiles.

Response shape:

- `items[]`
- each item includes `id`, `name`, `source`, `summary`
- persona behavior fields such as `system_prompt`, `teaching_style`, `narrative_mode`
- render-related defaults such as `available_emotions`, `available_actions`, `default_speech_style`

### `POST /personas`

Creates a user persona.

Request body:

```json
{
  "name": "string",
  "summary": "string",
  "system_prompt": "string",
  "teaching_style": ["string"],
  "narrative_mode": "grounded",
  "encouragement_style": "string",
  "correction_style": "string"
}
```

Returns the created persona object.

### `GET /personas/{persona_id}/assets`

Current placeholder renderer manifest for future Live2D / expression assets.

Response fields:

- `persona_id`
- `renderer`
- `asset_manifest`

## Documents

### `GET /documents`

Lists uploaded documents.

Each document includes:

- base metadata: `id`, `title`, `original_filename`, `stored_path`
- processing state: `status`, `ocr_status`, `debug_ready`
- derived counts: `page_count`, `chunk_count`, `study_unit_count`
- cleaned plan-facing `sections[]`
- cleaned `study_units[]`

### `POST /documents`

Uploads one file using multipart form data.

Form field:

- `file`

Returns a `DocumentRecord`.

### `POST /documents/{document_id}/process`

Runs parsing synchronously.

Optional request body:

```json
{
  "force_ocr": false
}
```

Returns the processed `DocumentRecord`.

### `POST /documents/{document_id}/process/stream`

Runs parsing as an NDJSON stream.

Request body:

```json
{
  "force_ocr": false
}
```

Current stream event stages may include:

- `document_processing_started`
- parser-emitted stages from the document parser
- `study_units_built`
- `document_processing_completed`
- `stream_completed`
- `stream_error`

Each line is one JSON object:

```json
{
  "stage": "document_processing_started",
  "payload": {
    "document_id": "doc-123",
    "force_ocr": false
  }
}
```

The final success event also includes a document payload:

```json
{
  "stage": "stream_completed",
  "payload": {
    "document_id": "doc-123",
    "status": "processed"
  },
  "document": {
    "...": "DocumentRecord"
  }
}
```

### `GET /documents/{document_id}/status`

Returns the current `DocumentRecord`.

### `GET /documents/{document_id}/debug`

Returns the persisted parse/debug artifact used by the `/debug` page.

Response fields:

- parser metadata: `parser_name`, `processed_at`, `extraction_method`, `ocr_applied`
- document-level stats: `page_count`, `total_characters`, `dominant_language_hint`
- raw parse artifacts: `pages[]`, `sections[]`, `chunks[]`, `warnings[]`
- cleaned plan-facing `study_units[]`

### `GET /documents/{document_id}/planning-context`

Returns the planner input context after cleanup.

Response fields:

- `document_id`
- `course_outline[]`: coarse level-1 sections plus level-2 children
- `study_units[]`: plan-facing unit list with summaries and subsection titles
- `detail_map`: detailed per-unit structure and chunk excerpts
- `available_tools[]`: tools the model planner may call

### `GET /documents/{document_id}/planning-trace`

Returns stored plan-generation trace data for the document.

Response fields:

- `document_id`
- `plan_id`
- `model`
- `created_at`
- `rounds[]`

Each round contains:

- `round_index`
- `finish_reason`
- `assistant_content`
- `thinking`
- `elapsed_ms`
- `timeout_seconds`
- `tool_calls[]`

Each tool call contains:

- `tool_call_id`
- `tool_name`
- `arguments_json`
- `result_json`

## Learning Plans

### `GET /learning-plans`

Lists persisted learning plans.

### `GET /learning-plans/{plan_id}`

Returns one stored learning plan.

### `POST /learning-plans`

Creates a learning plan synchronously.

Request body:

```json
{
  "document_id": "doc-123",
  "persona_id": "persona-123",
  "objective": "Prepare for midterm",
  "deadline": "2026-04-30",
  "study_days_per_week": 5,
  "session_minutes": 45
}
```

Returns:

- `id`, `document_id`, `persona_id`
- learner-facing text fields:
  - `course_title`: generated textbook-grounded plan header title
  - `objective`: learner goal captured from the request, used as supporting goal text
  - `overview`: generated summary paragraph
  - `weekly_focus[]`: ordered weekly study topics
  - `today_tasks[]`: actionable learner tasks
- referenced `study_units[]`
- planned `schedule[]`
- `created_at`

Text-field naming and display rules are defined in `docs/plan-text-contract.md`.

Possible mapped backend errors:

- `503 plan_model_rate_limited`
- `504 plan_model_timeout`
- `502 plan_model_network_error`
- `502 plan_model_upstream_error`
- `502 plan_model_invalid_json`
- `502 plan_model_invalid_payload`
- `500 plan_generation_failed`

### `POST /learning-plans/stream`

Creates a learning plan as an NDJSON stream.

Request body matches `POST /learning-plans`.

Current stream event stages may include:

- `learning_plan_started`
- `study_units_ready`
- `heuristic_plan_built`
- `model_round_started`
- `model_tool_call`
- `model_round_completed`
- `model_plan_applied`
- `learning_plan_completed`
- `stream_completed`
- `stream_error`

The final success line includes the full plan:

```json
{
  "stage": "stream_completed",
  "payload": {
    "document_id": "doc-123",
    "plan_id": "plan-123"
  },
  "plan": {
    "...": "LearningPlanRecord"
  }
}
```

## Study Sessions

### `POST /study-sessions`

Creates a study session shell for one document/persona/section.

Request body:

```json
{
  "document_id": "doc-123",
  "persona_id": "persona-123",
  "section_id": "unit-123"
}
```

Returns the persisted `StudySessionRecord`.

### `POST /study-sessions/{session_id}/chat`

Generates one tutor reply for the session.

Request body:

```json
{
  "message": "Explain this section again"
}
```

Response body:

```json
{
  "reply": "string",
  "citations": [
    {
      "section_id": "string",
      "title": "string",
      "page_start": 1,
      "page_end": 2
    }
  ],
  "character_events": [
    {
      "emotion": "calm",
      "action": "explain",
      "intensity": 0.6,
      "speech_style": "warm",
      "scene_hint": "desk",
      "line_segment_id": "seg-1",
      "timing_hint": "after_text"
    }
  ]
}
```

## Exercises

### `POST /exercises/generate`

Request body:

```json
{
  "persona_id": "persona-123",
  "section_id": "unit-123",
  "topic": "binary search"
}
```

Returns:

- `exercise_id`
- `section_id`
- `prompt`
- `exercise_type`
- `difficulty`
- `guidance`
- `character_events[]`

### `POST /submissions/grade`

Request body:

```json
{
  "persona_id": "persona-123",
  "exercise_id": "exercise-123",
  "answer": "string"
}
```

Returns:

- `score`
- `diagnosis[]`
- `recommendation`
- `character_events[]`

## Planner Tool Surface

The planner currently exposes two tool names to the upstream model:

- `get_study_unit_detail`
- `read_page_range_content`

These tools are backend-only. The frontend never calls them directly. Their outputs are captured in `/documents/{document_id}/planning-trace` and surfaced on `/debug`.

## Source Of Truth

When updating this API, keep these files aligned:

- `services/ai/app/api/routes.py`
- `services/ai/app/models/api.py`
- `services/ai/app/models/domain.py`
- `apps/web/lib/api.ts`
- `packages/shared/src/`
