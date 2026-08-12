# API Reference

## Base URL

- Local backend default: `http://127.0.0.1:8000`
- Frontend reads `NEXT_PUBLIC_AI_BASE_URL`
- No authentication is implemented in v1

## Runtime Configuration

When `VIBE_LEARNER_PLAN_PROVIDER=litellm`, chat/planning behavior is driven by LiteLLM Python SDK and affected by these env vars:

- `OPENAI_EMBEDDING_MODEL`: embedding model used by cross-session memory retrieval (for example `text-embedding-3-small`).

Tool enablement is now managed by `ModelToolConfig` (`GET/PATCH /model-tools/config`) and no longer uses runtime env toggles.

If embeddings are unavailable, the backend falls back to local hashed-vector retrieval.

`POST /runtime-settings/check-openai-models` still probes an OpenAI-compatible `/models` endpoint. LiteLLM SDK direct connections can be used for real inference even when this probe cannot enumerate models.

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
- each item also includes `background_story`
- persona behavior fields such as `system_prompt`, `teaching_style`, `narrative_mode`
- render-related defaults such as `available_emotions`, `available_actions`, `default_speech_style`

### `POST /personas`

Creates a user persona.

Request body:

```json
{
  "name": "string",
  "summary": "string",
  "background_story": "string",
  "system_prompt": "string",
  "teaching_style": ["string"],
  "narrative_mode": "grounded",
  "encouragement_style": "string",
  "correction_style": "string",
  "available_emotions": ["calm", "encouraging"],
  "available_actions": ["idle", "explain"],
  "default_speech_style": "warm"
}
```

Returns the created persona object.

### `PATCH /personas/{persona_id}`

Updates an existing persona.

Request body uses the same shape as `POST /personas`.

Returns the updated persona object.

Notes:

- builtin personas are readonly and return `403` with `detail=persona_readonly_builtin` on update.

### `POST /personas/assist-setting`

Generates an AI-assisted refinement draft for persona setting fields.

Request body:

```json
{
  "name": "string",
  "summary": "string",
  "background_story": "string",
  "teaching_style": ["string"],
  "narrative_mode": "grounded",
  "encouragement_style": "string",
  "correction_style": "string",
  "rewrite_strength": 0.5
}
```

Response body:

```json
{
  "background_story": "string",
  "system_prompt_suggestion": "string"
}
```

### `GET /personas/{persona_id}/assets`

Current placeholder renderer manifest for future Live2D / expression assets.

Response fields:

- `persona_id`
- `renderer`
- `asset_manifest`

## Documents

## Scene Setup and Scene Library

### `GET /scene-setup`

Loads the current draft scene setup state.

Returns a `SceneSetupStateRecord` payload with snake_case fields:

- `updated_at`
- `scene_name`
- `scene_summary`
- `scene_layers[]`
- `selected_layer_id`
- `collapsed_layer_ids[]`
- `scene_profile`

### `PUT /scene-setup`

Saves the current draft scene setup state.

Request body:

```json
{
  "scene_name": "高一物理-力学基础",
  "scene_summary": "从世界整体出发...",
  "scene_layers": [],
  "selected_layer_id": "scene-classroom",
  "collapsed_layer_ids": [],
  "scene_profile": null
}
```

Validation notes:

- `scene_name` requires `min_length=1`
- `scene_summary` requires `min_length=1`
- `scene_layers[]` items must match `SceneLayerStateRecord`

### `GET /scene-library`

Lists saved scene snapshots.

Returns:

```json
{
  "items": [
    {
      "scene_id": "scene-abc123",
      "created_at": "...",
      "updated_at": "...",
      "scene_name": "...",
      "scene_summary": "...",
      "scene_layers": [],
      "selected_layer_id": "...",
      "collapsed_layer_ids": [],
      "scene_profile": null
    }
  ]
}
```

### `GET /scene-library/{scene_id}`

Returns one saved scene item.

### `POST /scene-library`

Creates a new saved scene item.

Request body is the same shape as `PUT /scene-setup`.

### `PUT /scene-library/{scene_id}`

Updates an existing saved scene item.

Request body is the same shape as `PUT /scene-setup`.

### `DELETE /scene-library/{scene_id}`

Deletes one saved scene item.

Returns:

```json
{
  "deleted_scene_id": "scene-abc123"
}
```

### Scene 422 Checklist

Common 422 causes in this surface:

- `scene_name` or `scene_summary` sent as empty string
- missing required layer fields in `scene_layers[]` (especially `scope_label`)
- camelCase layer payload sent directly to backend without snake_case serialization

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

Returns the debug-facing planning context after cleanup.

Response fields:

- `document_id`
- `course_outline[]`: coarse level-1 sections plus level-2 children, kept for `/debug` inspection
- `study_units[]`: plan-facing unit list with summaries and subsection titles
- `detail_map`: detailed per-unit structure and chunk excerpts
- `available_tools[]`: tools the model planner may call

### `GET /documents/{document_id}/planning-trace`

Returns stored plan-generation trace data for the document.

Response fields:

- `document_id`
- `has_trace`
- `summary`
- `trace`

`summary` contains:

- `round_count`
- `tool_call_count`
- `latest_finish_reason`

When `has_trace=true`, `trace` contains:

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
  "objective": "Prepare for midterm"
}
```

Returns:

- `id`, `document_id`, `persona_id`
- learner-facing text fields:
  - `course_title`: generated textbook-grounded plan header title
  - `objective`: learner goal captured from the request, used as supporting goal text
  - `overview`: generated summary paragraph
  - `today_tasks[]`: actionable learner tasks
- referenced `study_units[]`
- planned `schedule[]`, where each item carries nested `schedule_chapters[]`
- derived `study_unit_progress[]`
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

Section source note:

- Study sessions are always scoped by `study_unit_id`.
- Learning Workspace renders a two-level directory: `schedule[]` as the primary list and `schedule_chapters[]` as per-schedule child items.
- Switching a learning chapter only changes local preview/navigation; switching the parent schedule item is what changes session scope.

### `POST /study-sessions`

Creates a study session shell for one document/persona/study-unit scope.

Request body:

```json
{
  "document_id": "doc-123",
  "persona_id": "persona-123",
  "study_unit_id": "unit-123",
  "study_unit_title": "optional study unit title",
  "theme_hint": "optional theme hint"
}
```

Returns the persisted `StudySessionRecord`.

### `GET /study-sessions`

Lists persisted study sessions.

Optional query params:

- `document_id`
- `persona_id`
- `study_unit_id`

### `POST /study-sessions/{session_id}/chat`

Generates one tutor reply for the session.

Request body:

```json
{
  "message": "Explain this section again"
}
```

Notes:

- chat generation now includes recent dialogue turns as model context
- citations are grounded from the document debug artifacts (study-unit/section/chunk page ranges)
- returned `character_events[].scene_hint` carries chapter/page render context for character-layer drawing
- when model payload is invalid or empty, backend returns `502` with `detail=chat_model_invalid_payload`
- frontend is expected to surface this as an explicit error and provide manual retry action

### `POST /study-sessions/{session_id}/attempt`

Appends one learner attempt turn and assistant verdict into the same session transcript.

Request body:

```json
{
  "question_type": "multiple_choice",
  "prompt": "string",
  "topic": "string",
  "difficulty": "easy",
  "options": [{ "key": "A", "text": "string" }],
  "answer_key": "A",
  "accepted_answers": ["A"],
  "submitted_answer": "A",
  "is_correct": true,
  "explanation": "string"
}
```

Returns updated `StudySessionRecord`.

### `PATCH /study-sessions/{session_id}`

Updates an existing study session. Supports study-unit switch and/or scene profile refresh.

Request body:

```json
{
  "study_unit_id": "unit-456",
  "scene_profile": {
    "scene_name": "高一物理-力学基础",
    "scene_id": "scene-classroom",
    "title": "教室层",
    "summary": "...",
    "tags": ["黑板", "实验台"],
    "selected_path": ["世界整体", "校园", "教室"],
    "focus_object_names": ["黑板", "实验台"],
    "scene_tree": []
  }
}
```

Validation notes:

- `study_unit_id` and `scene_profile` are both optional, but at least one must be provided.
- Sending neither returns `400` with `detail=update_payload_empty`.

Returns updated `StudySessionRecord`.

### `GET /documents/{document_id}/file`

Returns the uploaded textbook PDF as an inline file response (`application/pdf`).

Usage:

- Frontend can jump to pages via PDF fragment URLs, e.g. `/documents/{document_id}/file#page=12`.
- The response is served with inline content-disposition so browsers render in embedded PDF viewers instead of forcing download.

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

## Tavern Rooms

Tavern is independent from Study Sessions. It supports free interaction with a room-scoped persona snapshot and uses normalized, append-only messages.

### `POST /tavern/rooms`

Creates a room. `idempotency_key` is required so retries and double clicks return the same room.
Reusing the same key with a different normalized payload returns `409` with
`tavern_idempotency_key_reused:room_creation`.

```json
{
  "title": "夜航酒馆",
  "persona_ids": ["persona-a"],
  "scene_profile": null,
  "opening_prompt": "",
  "idempotency_key": "create-room-123456"
}
```

Returns `TavernRoomDetail` with `room`, ordered `participants`, paged `messages`, `message_count`, and `next_after_sequence`.

### `GET /tavern/rooms`

Returns lightweight summaries without loading transcripts or persona snapshots:

```json
{
  "items": [
    {
      "id": "tavern-...",
      "title": "夜航酒馆",
      "participant_persona_ids": ["persona-a"],
      "participant_names": ["阿澜"],
      "message_count": 2,
      "revision": 1,
      "status": "active",
      "created_at": "...",
      "updated_at": "..."
    }
  ]
}
```

### `GET /tavern/rooms/{room_id}`

Query parameters:

- `after_sequence`: exclusive forward cursor, default `0`;
- `before_sequence`: exclusive backward cursor for loading older pages;
- `tail=true`: return the latest page in ascending display order;
- `limit`: page size from `1` to `200`, default `200`.

`tail`, nonzero `after_sequence`, and `before_sequence` are mutually exclusive. Backward/tail pages expose `next_before_sequence`; forward pages expose `next_after_sequence`. Both directions return messages in ascending transcript order.

### `PATCH /tavern/rooms/{room_id}`

Updates title, cast, scene snapshot, or `active`/`archived` status. `expected_revision` is mandatory; stale writers receive `409` with `tavern_revision_conflict:{current_revision}`.

Removing a participant only changes future scheduling. Historical messages retain their saved `persona_name` and `persona_id`.

### `DELETE /tavern/rooms/{room_id}`

Permanently deletes one room and its participants, runs, and messages. The `expected_revision` query parameter is required; stale deletion returns `409`. Product UI should prefer archive and require confirmation before calling this route.
A room with a pending run returns `409`; its user message and failure/recovery evidence cannot be deleted while model work is in flight.

### `GET /tavern/rooms/{room_id}/runs`

Returns up to `limit` recent runs (`1`–`100`, default `50`) in reverse creation order. This is the recovery/debug boundary after a turn returns `502`: the client can restore the failed status, stable error code, attempts, recovery strategy, and Harness checks without parsing logs.

### `POST /tavern/rooms/{room_id}/turns`

Runs either one direct actor or a facilitated roster-ordered group. `input` is a discriminated trigger:

- `user_message` appends the supplied visible user message;
- `continue` anchors the latest existing message and appends no fake user/director message.

Direct mode requires exactly one target and permits either trigger, so one persona can continue speaking without a fabricated user message. Facilitated mode requires two to four distinct room participants and also permits either trigger. The room's harness policy may impose a lower target ceiling.

```json
{
  "input": {
    "kind": "user_message",
    "content": "今晚适合聊些什么？"
  },
  "mode": "direct",
  "target_persona_ids": ["persona-a"],
  "guidance": "先接住情绪，不急着给建议",
  "idempotency_key": "turn-request-123456",
  "expected_room_revision": 0
}
```

Facilitated continuation example:

```json
{
  "input": {
    "kind": "continue",
    "anchor_message_id": "tavern-message-latest"
  },
  "mode": "facilitated",
  "target_persona_ids": ["persona-c", "persona-a", "persona-b"],
  "guidance": "让角色互相回应，但保留各自立场",
  "idempotency_key": "turn-request-facilitated-1",
  "expected_room_revision": 4
}
```

Targets are a set. The server filters the room roster and persists `scheduled_participant_ids` in `display_order`; caller array order does not control speech order. Every scheduled actor has one normalized `speaker_step`. Validated actors are committed one at a time, so a later failure does not erase prior messages.

Response fields:

- `run`: trigger, server schedule, normalized steps, lineage, context digest, terminal sequence, status, and Harness traces;
- `input_message`: the canonical server-persisted user message for a `user_message` trigger, including assigned sequence/time; `null` for `continue` and `retry`;
- `generated_messages`: messages appended by this run;
- `room_state`: compact `{id,status,revision,last_sequence,updated_at}` mutation state. Fetch transcript pages and full room configuration separately with `GET /tavern/rooms/{room_id}`.

Reliability behavior:

- target-set permutations share one request digest and replay the same run;
- duplicate idempotency keys replay a terminal run without duplicate messages or model calls;
- reusing an idempotency key with a different normalized request returns `409` instead of silently replaying unrelated work;
- stale revisions and another pending room run return `409`;
- a stale `continue.anchor_message_id` returns `409 tavern_continue_anchor_stale`;
- first-actor failure produces `failed`; later-actor failure produces `partial`, keeps prior actor messages, marks the current step `failed`, and marks remaining steps `blocked`;
- schema/provider/Harness failures return `502` only after the terminal evidence is committed;
- replaying that identical failed request returns `200` with the typed terminal recovery envelope. Clients must inspect `run.status`.

Room revision claims are atomic at the database boundary. This applies to SQLite and PostgreSQL and does not depend on one Python process owning an in-memory lock.

### `POST /tavern/rooms/{room_id}/runs/{run_id}/retry`

Creates one child run for only the source run's `failed` and `blocked` actors:

```json
{
  "idempotency_key": "retry-request-123456",
  "expected_room_revision": 5
}
```

The source must be `failed` or `partial`. Retry appends no user message, does not repeat completed actors, preserves the original guidance and root input, and keeps the source terminal. The first child actor replies to the last completed source actor when one exists; subsequent child actors form the normal reply chain.

Retry returns `409` when:

- the room is archived;
- the source is not terminal/retryable or already has a direct child;
- room revision or transcript sequence changed;
- title, scene, harness policy, roster order, or participant prompt hash differs from the source context digest;
- a required participant no longer exists.

### Tavern Harness transport

OpenAI-compatible actor generation first requests strict `json_schema` for `TavernActorReply`. Providers returning `400`/`422` for that transport retry once with `json_object`, followed by the same Pydantic schema validation. Invalid actor payloads receive at most one low-temperature schema repair.

The transport schema follows the OpenAI Structured Outputs subset: every property is required and objects forbid additional properties. Application-only string length bounds remain enforced by Pydantic after decode rather than being sent as unsupported string keywords.

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
- `services/ai/app/api/tavern_routes.py`
- `services/ai/app/models/tavern.py`
- `services/ai/app/models/harness.py`
- `apps/web/lib/api.ts`
- `packages/shared/src/`
