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
- Frontend normalization is implemented in `apps/web/lib/api.ts`. Tavern payloads additionally pass through the fail-closed decoder in `apps/web/lib/tavern-decode.ts`; other domains remain under the repository-wide decoder migration tracked by `HRN-WEB-001`.

## Complete operation index

This reference covers **78 business HTTP operations across 59 unique paths**: 68 operations in the main router and 10 under the mounted `/tavern` router. The count is based on explicit `(method, full path)` pairs in `services/ai/app/api/routes.py` and `services/ai/app/api/tavern_routes.py`; generated `/docs`, `/redoc`, `/openapi.json`, implicit `HEAD`, and `OPTIONS` are excluded. FastAPI OpenAPI remains the field-level source for operations that are summarized rather than expanded below.

### Service, storage, model tools, and runtime settings (11)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/health` | Service liveness. |
| `GET` | `/storage/summary` | Inspect persistent/cache/temp category sizes and counts. |
| `POST` | `/storage/cleanup` | Clear requested cache/temp-compatible categories. |
| `GET` | `/model-tools/config` | Read stage/category tool availability and user overrides. |
| `PATCH` | `/model-tools/config` | Update tool overrides. |
| `GET` | `/runtime-settings` | Read effective persisted runtime configuration with secrets redacted. |
| `PATCH` | `/runtime-settings` | Persist runtime changes and rebuild the model provider. |
| `PUT` | `/runtime-settings/session-secrets` | Apply in-memory session secrets without persisting them. |
| `DELETE` | `/runtime-settings/session-secrets` | Remove in-memory session secrets. |
| `POST` | `/runtime-settings/check-openai-models` | Probe an OpenAI-compatible `/models` connection. |
| `GET` | `/model-usage/stats` | Return token/call usage aggregates and recent records. |

### Scene and reusable nodes (11)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/scene-setup` | Load the current draft scene tree. |
| `PUT` | `/scene-setup` | Save the current draft scene tree. |
| `POST` | `/scene-setup/generate` | Generate or extract a scene-tree proposal. |
| `GET` | `/scene-library` | List saved scene snapshots. |
| `GET` | `/scene-library/{scene_id}` | Read one saved scene. |
| `POST` | `/scene-library` | Create a saved scene. |
| `PUT` | `/scene-library/{scene_id}` | Replace a saved scene. |
| `DELETE` | `/scene-library/{scene_id}` | Delete a saved scene. |
| `GET` | `/reusable-scene-nodes` | List reusable layer/object nodes. |
| `POST` | `/reusable-scene-nodes` | Store a reusable node. |
| `DELETE` | `/reusable-scene-nodes/{node_id}` | Delete a reusable node. |

### Documents and parse/plan evidence (13)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/documents` | List documents. |
| `POST` | `/documents` | Upload a document. |
| `POST` | `/documents/{document_id}/process` | Process a document synchronously. |
| `POST` | `/documents/{document_id}/process/stream` | Process through NDJSON events. |
| `PATCH` | `/documents/{document_id}/study-units/{study_unit_id}` | Update one Study Unit title. |
| `GET` | `/documents/{document_id}/status` | Read current document status. |
| `GET` | `/documents/{document_id}/file` | Stream the original PDF inline. |
| `GET` | `/documents/{document_id}/pages/{page_number}/image` | Render/serve one PDF page image. |
| `GET` | `/documents/{document_id}/debug` | Read the persisted parse artifact used by the global Debug Overlay. |
| `GET` | `/documents/{document_id}/process-events` | Read persisted processing stream events. |
| `GET` | `/documents/{document_id}/planning-context` | Read cleaned Study Units, detail map, and planner tools. |
| `GET` | `/documents/{document_id}/planning-trace` | Read the persisted model/tool planning trace. |
| `GET` | `/documents/{document_id}/plan-events` | Read persisted plan stream events. |

### Personas and persona cards (12)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/personas` | List builtin and user personas. |
| `POST` | `/personas` | Create a user persona. |
| `PATCH` | `/personas/{persona_id}` | Update a user persona. |
| `DELETE` | `/personas/{persona_id}` | Delete a user persona when it is not protected/referenced. |
| `GET` | `/personas/{persona_id}/assets` | Read the placeholder character asset manifest. |
| `POST` | `/personas/assist-setting` | Generate setting-field assistance. |
| `POST` | `/personas/assist-slot` | Rewrite one persona slot. |
| `GET` | `/persona-cards` | List reusable persona cards. |
| `POST` | `/persona-cards` | Create one card. |
| `POST` | `/persona-cards/batch` | Create a card batch. |
| `DELETE` | `/persona-cards/{card_id}` | Delete one card. |
| `POST` | `/persona-cards/generate` | Generate/extract persona card proposals. |

### Study Sessions and attachments (10)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/study-sessions` | List/filter Study Sessions. |
| `POST` | `/study-sessions` | Create a Study Session. |
| `PATCH` | `/study-sessions/{session_id}` | Change its Study Unit and/or scene snapshot. |
| `POST` | `/study-sessions/{session_id}/chat` | Generate and append one structured study reply. |
| `POST` | `/study-sessions/{session_id}/chat-with-attachments` | Upload attachments and generate a structured study reply. |
| `POST` | `/study-sessions/{session_id}/attempt` | Append a learner exercise attempt and verdict. |
| `POST` | `/study-sessions/{session_id}/follow-ups/cancel` | Cancel a pending follow-up in session state. |
| `POST` | `/study-sessions/{session_id}/plan-confirmations/{confirmation_id}` | Confirm or reject a pending plan change. |
| `GET` | `/study-sessions/{session_id}/attachments/{attachment_id}/file` | Read a stored attachment. |
| `GET` | `/study-sessions/{session_id}/attachments/{attachment_id}/pages/{page_number}/image` | Render/serve one attachment PDF page image. |

### Learning Plans, streams, exercises, and grading (11)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/learning-plans` | List plans. |
| `POST` | `/learning-plans` | Generate and persist a plan synchronously. |
| `POST` | `/learning-plans/stream` | Generate through NDJSON events. |
| `GET` | `/learning-plans/{plan_id}` | Read one plan. |
| `PATCH` | `/learning-plans/{plan_id}` | Update editable plan fields. |
| `PATCH` | `/learning-plans/{plan_id}/progress` | Update Study Unit progress. |
| `PATCH` | `/learning-plans/{plan_id}/planning-questions/{question_id}` | Answer/update a planning question. |
| `DELETE` | `/learning-plans/{plan_id}` | Delete one plan. |
| `POST` | `/stream-runs/{stream_id}/cancel` | Mark a processing/planning stream as canceled. |
| `POST` | `/exercises/generate` | Generate a structured exercise. |
| `POST` | `/submissions/grade` | Grade one structured submission. |

### Tavern (10)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/tavern/rooms` | Idempotently create a room with persona snapshots. |
| `GET` | `/tavern/rooms` | List room summaries. |
| `GET` | `/tavern/rooms/{room_id}` | Read room detail with bounded message paging. |
| `PATCH` | `/tavern/rooms/{room_id}` | Revision-check room metadata, cast, scene, or archive state. |
| `DELETE` | `/tavern/rooms/{room_id}` | Revision-check permanent deletion. |
| `GET` | `/tavern/rooms/{room_id}/runs` | Read a bounded recent run list. |
| `POST` | `/tavern/rooms/{room_id}/turns` | Start an idempotent direct/facilitated run. |
| `POST` | `/tavern/rooms/{room_id}/runs/{run_id}/retry` | Start a scoped child retry. |
| `POST` | `/tavern/rooms/{room_id}/runs/{run_id}/cancel` | Fence result commits and future recovery. |
| `POST` | `/tavern/rooms/{room_id}/runs/{run_id}/resume` | Resume/take over pending work subject to its lease and claim budget. |

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

Returns the persisted parse/debug artifact used by the global Debug Overlay.

Response fields:

- parser metadata: `parser_name`, `processed_at`, `extraction_method`, `ocr_applied`
- document-level stats: `page_count`, `total_characters`, `dominant_language_hint`
- raw parse artifacts: `pages[]`, `sections[]`, `chunks[]`, `warnings[]`
- cleaned plan-facing `study_units[]`

### `GET /documents/{document_id}/planning-context`

Returns the debug-facing planning context after cleanup.

Response fields:

- `document_id`
- `course_outline[]`: coarse level-1 sections plus level-2 children, kept for Debug Overlay inspection
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

Returns the persisted `StudySessionRecord`. The server owns:

- `revision`, a monotonic per-session CAS watermark;
- `last_turn_sequence`, the current contiguous turn watermark;
- each `turns[].id` and `turns[].sequence`.

These fields are committed-record identity and ordering evidence. They are not model proposal fields, a Study Chat idempotency receipt, or proof that tool/file/provider effects are exactly once.

The browser rejects missing, non-integer, duplicate, empty, gapped, or watermark-mismatched committed turn identity before rendering. This narrow decoder does not yet strictly validate every nested Study Chat citation, Character Event, attachment, or future effect receipt; that broader boundary remains `HRN-WEB-STUDY-DEC-001`.

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
- the final visible turn appends through bounded revision CAS, preserving concurrent session mutations and assigning a unique contiguous turn sequence
- the endpoint does not yet accept a stable client request ID; retries may still replay model/tool/file effects and are tracked by `STUDY-OP-ADMIT-001`
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

Returns `TavernRoomDetail` with `room`, ordered `participants`, paged `messages`, `message_count`, `next_after_sequence`, and `next_before_sequence`.

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

Tavern clients must decode every aggregate from `unknown` and bind it to the requested `room_id`; a TypeScript assertion or default-filled normalizer is insufficient. A malformed enum, identity, ownership link, schedule/step projection, sequence, nullable field, or generated-message projection is a typed decode failure rather than a partial record.

### `PATCH /tavern/rooms/{room_id}`

Updates title, cast, scene snapshot, or `active`/`archived` status. `expected_revision` is mandatory; stale writers receive `409` with `tavern_revision_conflict:{current_revision}`.

Removing a participant only changes future scheduling. Historical messages retain their saved `persona_name` and `persona_id`.

### `DELETE /tavern/rooms/{room_id}`

Permanently deletes one room and its participants, runs, and messages. The `expected_revision` query parameter is required; stale deletion returns `409`. Product UI should prefer archive and require confirmation before calling this route.
A room with a pending run returns `409`; its user message and failure/recovery evidence cannot be deleted while model work is in flight.

### `GET /tavern/rooms/{room_id}/runs`

Returns up to `limit` recent runs (`1`–`100`, default `50`) in reverse creation order. This bounded list supports local recovery/debug after a turn returns `502`: the client can inspect failed status, stable error code, attempts, recovery strategy, and Harness checks without parsing logs. It is not an authoritative retry-chain aggregate; a child outside the window may be omitted, which is tracked by `TAV-RUN-VIEW-001`.

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

Client reconciliation must bind the response to the active room and operation token, discard stale cross-room results, merge messages monotonically, and never allow a terminal run to regress to `pending`. HTTP success describes transport/recovery delivery only; `completed`, `partial`, `failed`, and `canceled` remain distinct domain outcomes.

Room revision claims are atomic at the database boundary. This applies to SQLite and PostgreSQL and does not depend on one Python process owning an in-memory lock.

Pending speaker steps expose `claim_count`. A generating step owns a database-clock lease renewed by heartbeat. A crashed worker can be taken over only after expiry; owner plus claim epoch fence stale commits. Every step permits at most three claims (initial plus two takeovers). Exhaustion persists a terminal `failed`/`partial` run with `tavern_run_claims_exhausted` and a `lease_recovery` Harness trace; HTTP `200` still requires the client to inspect `run.status`.

### `POST /tavern/rooms/{room_id}/runs/{run_id}/resume`

Resumes a pending run after a process or worker interruption. Completed steps and messages are reused, never regenerated. An active lease returns `409 tavern_run_in_progress:{run_id}`. An expired lease is claimed with a new fencing epoch; claim-budget exhaustion returns the durable terminal recovery envelope.

### `POST /tavern/rooms/{room_id}/runs/{run_id}/cancel`

Atomically changes a pending run and its pending/generating steps to `canceled`. Repeating cancel on the same canceled run is idempotent and returns `200`; other terminal states return `409`.

Cancel immediately prevents message commit and prevents later provider fallback/recovery calls. The current synchronous provider transport cannot abort an already-issued upstream request, so that request may continue until its configured timeout even though its result is rejected. UI copy must describe this as canceling receipt of the result, not as guaranteed termination of model compute.

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

The planner registers six backend-only tools:

- `get_study_unit_detail`
- `ask_planning_question`
- `estimate_plan_completion`
- `revise_study_units`
- `read_page_range_content`
- `read_page_range_images`

The actual set offered to one model call is filtered by Model Tool Config and runtime context: detail/debug data is required by the relevant readers and rewriter, while page images additionally require a document path and multimodal planning. The frontend never calls these tools directly. Their outputs are captured in `/documents/{document_id}/planning-trace` and surfaced in the global Debug Overlay.

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
