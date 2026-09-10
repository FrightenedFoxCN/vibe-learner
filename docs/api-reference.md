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

`POST /runtime-settings/check-openai-models` probes an OpenAI-compatible `/models` endpoint. With optional `model` and `features` (`plan`, `study`, `persona`, `scene`, `tavern`), it also sends minimal representative requests through the same LiteLLM path and returns per-feature `ready`, `unsupported`, or `failed` readiness, typed reason codes, notes, and explicit parameter adjustments. Listing a model, passing authentication, and proving a feature request callable remain separate results. LiteLLM SDK direct connections can still be used for real inference when a provider cannot enumerate models.

## Response Conventions

- Standard endpoints return JSON.
- Streaming endpoints return `application/x-ndjson`.
- Error payloads from FastAPI follow `{"detail": ...}`.
- Frontend projection is coordinated by `apps/web/lib/api.ts`. Tavern,
  Document/Debug, Planning, Persona/Scene, and Study HTTP projections pass
  through domain-owned fail-closed decoders before rendering. Document and
  Planning live NDJSON plus persisted v1 reports additionally pass the strict
  versioned stream state machine. Subject/draft-revision/field-target fences
  reject stale async results. Independent real-wire closure, remaining endpoint
  inventory, Frontend Decoder component registration, and v2/v3 trace
  forwarding/resource evidence remain tracked under `HRN-WEB-001`.

## Complete operation index

This reference covers **79 business HTTP operations across 60 unique paths**: 68 operations in the main router and 11 under the mounted `/tavern` router. The count is based on explicit `(method, full path)` pairs in `services/ai/app/api/routes.py` and `services/ai/app/api/tavern_routes.py`; generated `/docs`, `/redoc`, `/openapi.json`, implicit `HEAD`, and `OPTIONS` are excluded. FastAPI OpenAPI remains the field-level source for operations that are summarized rather than expanded below.

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
| `POST` | `/runtime-settings/check-openai-models` | Probe `/models` and optional model + feature representative requests without persisting credentials. |
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

### Learning Plans, streams, exercises, and grading (12)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/learning-plans` | List plans. |
| `POST` | `/learning-plans` | Generate and persist a plan synchronously. |
| `POST` | `/learning-plans/stream` | Generate through NDJSON events. |
| `GET` | `/learning-plan-operations/{client_request_id}` | Query one admitted plan operation and its committed plan snapshot. |
| `GET` | `/learning-plans/{plan_id}` | Read one plan. |
| `PATCH` | `/learning-plans/{plan_id}` | Update editable plan fields. |
| `PATCH` | `/learning-plans/{plan_id}/progress` | Update Study Unit progress. |
| `PATCH` | `/learning-plans/{plan_id}/planning-questions/{question_id}` | Answer/update a planning question. |
| `DELETE` | `/learning-plans/{plan_id}` | Delete one plan. |
| `POST` | `/stream-runs/{stream_id}/cancel` | Mark a processing/planning stream as canceled. |
| `POST` | `/exercises/generate` | Generate a structured exercise. |
| `POST` | `/submissions/grade` | Grade one structured submission. |

### Tavern (11)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/tavern/rooms` | Idempotently create a room with persona snapshots. |
| `GET` | `/tavern/rooms` | List a stable cursor page of room summaries. |
| `GET` | `/tavern/rooms/{room_id}` | Read room detail with bounded message paging. |
| `PATCH` | `/tavern/rooms/{room_id}` | Revision-check room metadata, cast, scene, or archive state. |
| `DELETE` | `/tavern/rooms/{room_id}` | Revision-check permanent deletion. |
| `GET` | `/tavern/rooms/{room_id}/runs` | Read a bounded recent run list. |
| `GET` | `/tavern/rooms/{room_id}/run-recovery` | Read authoritative retry-chain leaves independently of recent-run paging. |
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
- each item includes opaque `id`, non-negative `revision`, `name`, `source`, and `summary`
- relationship fields are `relationship` and `learner_address`
- behavior is represented by `system_prompt`, `reference_hints`, and ordered `slots[]`
- render-related defaults such as `available_emotions`, `available_actions`, `default_speech_style`

### `POST /personas`

Creates a user persona.

Request body:

```json
{
  "name": "string",
  "summary": "string",
  "relationship": "string",
  "learner_address": "string",
  "system_prompt": "string",
  "reference_hints": ["string"],
  "slots": [
    {
      "kind": "teaching_method",
      "label": "教学方法",
      "content": "string",
      "weight": 50,
      "locked": false,
      "sort_order": 0
    }
  ],
  "available_emotions": ["calm", "encouraging"],
  "available_actions": ["idle", "point"],
  "default_speech_style": "warm"
}
```

The server allocates an opaque `persona-<uuid>` identity; the name never enters
the resource path. Unknown fields, blank names, coerced slot values, non-finite
or out-of-range weights, and negative ordering are rejected. Returns the
created persona at `revision=0`.

### `PATCH /personas/{persona_id}`

Updates an existing persona.

This is a full replacement despite the compatibility `PATCH` method name.
Request body uses the same editable fields as `POST /personas` and also requires:

```json
{
  "expected_revision": 0
}
```

Returns the updated persona with `revision = expected_revision + 1`. A stale
write returns `409` with `detail.code=persona_revision_conflict` and the current
revision. Renaming does not change the opaque persona ID.

Notes:

- builtin personas are readonly and return `403` with `detail=persona_readonly_builtin` on update.

### `DELETE /personas/{persona_id}?expected_revision={revision}`

Deletes an unreferenced user persona at the exact expected revision. Stale
deletes return the same `persona_revision_conflict`; referenced personas return
`409 persona_in_use`, and builtin personas remain readonly.

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

- `revision`
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
  "contract_version": "scene-committed-save-v1",
  "expected_revision": 3,
  "scene_name": "高一物理-力学基础",
  "scene_summary": "从世界整体出发...",
  "scene_layers": [{"id": "scene-layer-123", "reuse_id": "scene-layer-reuse-123", "...": "..."}],
  "selected_layer_id": "scene-classroom",
  "collapsed_layer_ids": []
}
```

Validation notes:

- the contract is strict and rejects extra fields, including caller-authored `scene_profile`
- every layer/object requires an application ID and reuse ID
- all IDs are globally unique; selected/collapsed layer IDs must exist
- depth, layer/object counts, child counts, primitive types, and text size are bounded
- `expected_revision` must match the latest GET; stale writes return `409 scene_revision_conflict`

### `POST /scene-setup/generate`

Generates an unpersisted Scene candidate from `keywords` or `long_text` input.
The model-facing `scene-tree-proposal-v1` contains no application IDs. It uses
`selected_path` (zero-based indexes from the root array), strict bounded tree
content, and optional reusable-node references that must resolve through the
application allow-list. The response is the application-projected tree with
server-assigned layer/object/reuse IDs; invalid proposals return
`502 setting_model_invalid_payload` and persist nothing.

### `GET /scene-library`

Lists saved scene snapshots.

Returns:

```json
{
  "items": [
    {
      "scene_id": "scene-abc123",
      "revision": 2,
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

Request body is the same strict committed shape as `PUT /scene-setup`, with
`expected_revision: 0`.

### `PUT /scene-library/{scene_id}`

Updates an existing saved scene item.

Request body is the same strict committed shape as `PUT /scene-setup`, with the
latest Scene Library item revision.

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
- missing required layer/object ID or reuse identity
- stale or missing `expected_revision`
- duplicate IDs, invalid selected/collapsed references, or an oversized/deep tree
- model proposal fields (`selected_path`, `reusable_node_ref`) sent to a committed-save endpoint
- committed fields (`id`, `reuse_id`, `scene_profile`) sent as model proposal output
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

The service durably admits one process operation before parsing. The final
Document and Debug projections commit atomically with a terminal operation
receipt; cleanup or projection failure records `not_committed` and returns the
Document to a durable non-`processing` state. An interrupted request restores
its pre-process Document projection. A concurrent active process for the same
Document returns `409`, and abandoned operations are terminalized during
service startup. The operation journal is server-only and does not add fields
to `DocumentRecord`.

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
- `stream_cancelled`

Each line is a `stream-event-v1` object. The service owns `operation_id`,
`event_id`, and the monotonic `event_sequence`; `subject` binds every frame to
the requested Document. `payload_digest` is the backend canonical SHA-256 of
`payload` under `document-process-stream-payload-v1`:

```json
{
  "event_schema_version": "stream-event-v1",
  "operation_id": "stream-a1b2c3d4e5f6",
  "event_id": "stream-a1b2c3d4e5f6:event:1",
  "event_sequence": 1,
  "stream_kind": "document_process",
  "subject": {
    "subject_type": "document",
    "subject_id": "doc-123"
  },
  "stage": "document_processing_started",
  "payload_contract_version": "document-process-stream-payload-v1",
  "payload_digest": "<sha256>",
  "payload": {
    "document_id": "doc-123",
    "force_ocr": false
  },
  "terminal_evidence": null,
  "committed_projection": null,
  "created_at": "2026-08-25T00:00:00+00:00"
}
```

The final success event is valid only when its terminal evidence binds the
committed Document projection and exact digest:

```json
{
  "event_schema_version": "stream-event-v1",
  "operation_id": "stream-a1b2c3d4e5f6",
  "event_id": "stream-a1b2c3d4e5f6:event:9",
  "event_sequence": 9,
  "stream_kind": "document_process",
  "subject": {
    "subject_type": "document",
    "subject_id": "doc-123"
  },
  "stage": "stream_completed",
  "payload_contract_version": "document-process-stream-payload-v1",
  "payload_digest": "<sha256>",
  "payload": {
    "document_id": "doc-123",
    "status": "processed"
  },
  "terminal_evidence": {
    "commit_status": "committed",
    "domain_operation_id": "document-process-op-123",
    "domain_operation_status": "committed",
    "evidence_scope": "primary_output_only",
    "resource_type": "document",
    "resource_id": "doc-123",
    "commit_contract_version": "document-process-commit-v1",
    "projection_contract_version": "document-record-v1",
    "projection_digest": "<sha256>"
  },
  "committed_projection": {
    "...": "DocumentRecord"
  },
  "created_at": "2026-08-25T00:00:05+00:00"
}
```

`stream_error` and `stream_cancelled` are terminal and carry `not_committed` or
`uncertain` evidence without a committed projection. The evidence is a narrow
transport read-back with `primary_output_only` scope; it does not claim Harness
v3 adoption or prove every Document/Debug transaction effect. Persisted
`stream-report-v1` snapshots retain the latest 120 events plus the total
`last_event_sequence`, so a trimmed/reconnected reader can detect gaps. Old
reports without an explicit version remain readable as legacy records without
invented operation, sequence, or digest evidence.

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
  "client_request_id": "learning-plan-019ff5f5f4c14ec3",
  "expected_document_updated_at": "2026-08-24T10:00:00+00:00",
  "objective": "Prepare for midterm"
}
```

`client_request_id` identifies one generation intent and must remain stable for
terminal read-back. Document-backed requests also carry the exact
`expected_document_updated_at` returned with the selected Document. Reusing a
request ID with different content, starting a sibling operation for the same
Document, or submitting a stale watermark is rejected with `409`.

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

- `409 learning_plan_stale_document`
- `409 learning_plan_operation_active`
- `409 learning_plan_request_conflict`
- `409 learning_plan_projection_prerequisite_missing`
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
- `planning_question_asked`
- `model_tool_call`
- `model_round_completed`
- `model_plan_applied`
- `learning_plan_completed`
- `stream_completed`
- `stream_error`
- `stream_cancelled`

Planning lines use the same `stream-event-v1` envelope with
`stream_kind=learning_plan` and
`payload_contract_version=learning-plan-stream-payload-v1`. Document-backed
requests use a `document` subject; goal-only requests use the stable
`learning_plan_request` subject from `client_request_id`. The final success line
binds the full Plan as the committed projection:

```json
{
  "event_schema_version": "stream-event-v1",
  "operation_id": "stream-f6e5d4c3b2a1",
  "event_id": "stream-f6e5d4c3b2a1:event:12",
  "event_sequence": 12,
  "stream_kind": "learning_plan",
  "subject": {
    "subject_type": "document",
    "subject_id": "doc-123"
  },
  "stage": "stream_completed",
  "payload_contract_version": "learning-plan-stream-payload-v1",
  "payload_digest": "<sha256>",
  "payload": {
    "document_id": "doc-123",
    "plan_id": "plan-123"
  },
  "terminal_evidence": {
    "commit_status": "committed",
    "domain_operation_id": "learning-plan-op-123",
    "domain_operation_status": "committed",
    "evidence_scope": "primary_output_only",
    "resource_type": "learning_plan",
    "resource_id": "plan-123",
    "commit_contract_version": "learning-plan-commit-v1",
    "projection_contract_version": "learning-plan-record-v1",
    "projection_digest": "<sha256>"
  },
  "committed_projection": {
    "...": "LearningPlanRecord"
  },
  "created_at": "2026-08-25T00:01:00+00:00"
}
```

The digest is produced by Python, the canonical authority. Browser clients may
use the supplied event ID/digest pair for replay equality but must not use
`JSON.stringify` to claim cross-language digest verification.

### `GET /learning-plan-operations/{client_request_id}`

Returns the durable operation state (`running`, `committed`, `not_committed`,
`interrupted`, or `uncertain`), projection state, provider-start watermark,
terminal error code, and the original committed Plan snapshot when available.
This endpoint is query-only recovery; an `uncertain` operation must not be
blindly replayed with a new request identity.

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

The browser rejects missing, non-integer, duplicate, empty, gapped, or watermark-mismatched committed Turn identity before rendering. The current Study decoder also validates Session/Document/Persona/Plan/Study Unit identity, attachments and citations, Character Events/tool calls, interactive-question public projections, projected state, follow-up/affinity/confirmation state, recursive Scene budgets, and committed exchange/Turn read-back. The internal committed effect batch is intentionally not part of the public wire; independent live-wire closure remains separate from this implemented decoder.

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
  "message": "Explain this section again",
  "client_request_id": "study-chat-019ff5f5f4c14ec3",
  "expected_session_revision": 7
}
```

Notes:

- chat generation now includes recent dialogue turns as model context
- citations are grounded from the document debug artifacts (study-unit/section/chunk page ranges)
- returned `character_events[].scene_hint` carries chapter/page render context for character-layer drawing
- `client_request_id` identifies one browser intent and must remain stable across transport retry, reconnect, and terminal read-back; reusing it with a different payload or revision is rejected
- `expected_session_revision` fences admission against a stale Session; the final visible Turn still commits through bounded revision CAS with an application-owned ID and contiguous sequence
- admission is persisted before provider execution; a duplicate committed request returns the same terminal receipt without invoking the model again
- after timeout, disconnect, `admitted`, `running`, or `uncertain`, query the original operation; do not automatically repeat this POST or mint a new key
- request-schema and stale-revision failures are rejected before admission with 4xx; attachment validation after durable admission but before execution returns a `not_committed` receipt; deterministic scheduled-follow-up, Session, revision, and Scene conflicts are validated before the provider claim and therefore do not become false `uncertain` operations
- the browser preserves HTTP status plus typed error code for pre-admission failures: explicit Session/request/revision/active-slot conflicts and request validation offer “refresh Session state” instead of querying an operation that was never created; the learner draft remains editable, while sending waits for refresh and then uses a new request identity
- transport loss, response decode failure, provider failure, and timeout are not pre-admission proof and therefore remain query-only; an explicit `404 study_chat_operation_not_found` from the operation GET ends the query loop and also requires a Session refresh
- after execution starts, invalid/empty model output, provider/network failure, and provider timeout persist as an `uncertain` receipt with HTTP 200; the internal failure is retained in `error_code` so the client can decode and query the operation instead of interpreting a transient HTTP error as permission to replay
- frontend surfaces terminal/uncertain state explicitly; a new POST is allowed only when the receipt is `not_committed` and `safe_to_retry=true`

Response shape (abridged; `result` is the complete existing `StudyChatExchangeResponse` wire and is non-null only for `committed`):

```json
{
  "operation_id": "study-chat-op-019ff5f5f552",
  "session_id": "session-123",
  "client_request_id": "study-chat-019ff5f5f4c14ec3",
  "status": "committed",
  "safe_to_retry": false,
  "admitted_session_revision": 7,
  "committed_session_revision": 8,
  "committed_turn_id": "turn-123",
  "committed_turn_sequence": 4,
  "result": {
    "reply": "...",
    "citations": [],
    "character_events": [],
    "session": {
      "id": "session-123",
      "revision": 8,
      "last_turn_sequence": 4,
      "turns": [{ "id": "turn-123", "sequence": 4 }]
    }
  },
  "error_code": "",
  "created_at": "2026-08-12T14:00:00Z",
  "updated_at": "2026-08-12T14:00:02Z",
  "completed_at": "2026-08-12T14:00:02Z"
}
```

All receipt fields are present. Nullable commit/result fields and `completed_at` are explicit `null` outside the states where they apply; they are not omitted or encoded as empty strings.

### `POST /study-sessions/{session_id}/chat-with-attachments`

Runs the same admitted Study Chat operation as the JSON endpoint with multipart attachments. The form includes `client_request_id` and `expected_session_revision` in addition to the existing message/follow-up fields and files. File name, media type, size, and SHA-256 manifest participate in the canonical request identity.

Attachment limits are enforced before provider execution:

- at most 4 files;
- at most 12 MiB per file;
- at most 24 MiB across the request.

The request manifest is durably admitted before files are written. Attachment/file-effect identity, public attachment ID, and staging directory are derived from the operation and input slot; failed partial writes and terminal `not_committed`/`uncertain` operations are cleaned within the Session-scoped staging root. A committed read-back verifies the manifest, Turn attachment projection, bounded path, file existence, and SHA-256 digest. It returns the same `StudyChatOperationReceipt`; retry and query rules are identical. Study Chat emits production v3 evidence for its Session/Turn primary output, while this file boundary does not make an upstream provider call exactly once or extend that claim to every attachment effect.

### `GET /study-sessions/{session_id}/chat-operations/{client_request_id}`

Reads the durable receipt for the original Study Chat request without claiming, executing, or replaying it. Use this route after a timeout, disconnect, refresh, or any `admitted` / `running` / `uncertain` response. Session and request identity must match the URL; unknown or mismatched operations fail closed.

Operation status semantics:

- `admitted`: durable but not yet claimed; query only
- `running`: claimed/executing; query only
- `committed`: terminal; `result` and committed Turn evidence are present
- `not_committed`: terminal; retry is allowed only when `safe_to_retry=true`
- `uncertain`: terminal ambiguity after execution may have started; never automatically replay

This receipt proves admission identity and final Study Turn/result read-back. Memory, affinity, follow-up create/complete/cancel, projected-state set/focus/overlay/clear, plan confirmation, and Study Scene replacement use typed proposals and server-only committed projections; database effects share the final Turn/Session transaction, while Scene rows add their own CAS and exact snapshot read-back. Attachments use the separate operation-owned staging/cleanup/digest boundary described above. The public response intentionally omits the internal effect batch and Harness trace; both remain server-side. Generated-image and upstream provider calls remain external effects: without provider idempotency or authoritative read-back, a started ambiguous call is `uncertain` and is never automatically replayed. The v3 commit policy proves only the Session/Turn primary output.

### `GET /study-sessions/{session_id}`

Returns the current public `StudySessionRecord` projection for one Session. Interactive questions expose prompt/options plus an optional committed `result`; the server-only grading spec is never serialized. The frontend uses this read after an Attempt response so a response loss can replay the same Attempt identity and then recover the authoritative Session without submitting a second answer.

### `POST /study-sessions/{session_id}/attempt`

Grades and commits one answer against an existing interactive-question Turn. The request is `extra=forbid`, targets an application-owned Turn ID, binds the expected Session revision, and carries a stable browser-owned attempt key. It never accepts prompt/options/answer material, a client verdict, or explanation.

Request body:

```json
{
  "turn_id": "turn-...",
  "expected_session_revision": 4,
  "client_attempt_id": "study-attempt-...",
  "submitted_answer": "A"
}
```

Returns the narrow `study-question-attempt-response-v1` projection:

```json
{
  "schema_version": "study-question-attempt-response-v1",
  "attempt_id": "study-question-attempt-...",
  "client_attempt_id": "study-attempt-...",
  "session_id": "session-...",
  "turn_id": "turn-...",
  "submitted_answer": "A",
  "is_correct": true,
  "feedback_text": "回答正确",
  "explanation": "string",
  "before_revision": 4,
  "committed_revision": 5,
  "committed_at": "2026-08-24T00:00:00+00:00"
}
```

The server grades with `unicode-nfkc-casefold-whitespace-v1`: multiple choice compares the committed option key, and fill-blank compares a normalized answer against the private accepted-answer set. Session result state and the durable `study_question_attempts` row commit in one transaction. Same key + same normalized input reads the original response without advancing revision; same key + different input, a second identity for an answered Turn, a cross-Session Turn, or a stale revision fails closed. The browser strictly decodes this response, reads the current Session, and displays a verdict only when the returned Attempt identity/result is present on the exact Turn.

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

Returns lightweight summaries without loading transcripts or persona snapshots. Query parameters:

- `limit`: page size from `1` to `50`, default `30`;
- `cursor`: opaque continuation cursor from the preceding page.

Pages are ordered by `(updated_at DESC, id DESC)`. The cursor is closed-versioned,
integrity checked, and bound to that pair; malformed, modified, or no-longer-known
anchors return `400` instead of silently restarting at the first page. Each page
uses bounded batched aggregation and returns at most 50 summaries.

```json
{
  "contract_version": "tavern-room-list-v1",
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
  ],
  "next_cursor": "opaque-cursor-or-null"
}
```

`next_cursor = null` means no further page is available. The browser appends
pages with ID deduplication, keeps an independently loaded selected Room visible,
and retains at most 100 summary buttons; full selected Room state still comes
from `GET /tavern/rooms/{room_id}`.

### `GET /tavern/rooms/{room_id}`

Query parameters:

- `after_sequence`: exclusive forward cursor, default `0`;
- `before_sequence`: exclusive backward cursor for loading older pages;
- `tail=true`: return the latest page in ascending display order;
- `limit`: page size from `1` to `200`, default `200`.

`tail`, nonzero `after_sequence`, and `before_sequence` are mutually exclusive. Backward/tail pages expose `next_before_sequence`; forward pages expose `next_after_sequence`. Both directions return messages in ascending transcript order.

Tavern clients must decode every aggregate from `unknown` and bind it to the requested `room_id`; a TypeScript assertion or default-filled normalizer is insufficient. A malformed enum, identity, ownership link, schedule/step projection, sequence, nullable field, or generated-message projection is a typed decode failure rather than a partial record.

### `PATCH /tavern/rooms/{room_id}`

Updates title, cast, scene snapshot, or `active`/`archived` status. `expected_revision` is mandatory; stale writers receive `409` with structured `code=tavern_revision_conflict`, the authoritative `current_revision`, and `recovery_action=reload_room`.

Removing a participant only changes future scheduling. Historical messages retain their saved `persona_name` and `persona_id`.

### `DELETE /tavern/rooms/{room_id}`

Permanently deletes one room and its participants, runs, and messages. The `expected_revision` query parameter is required; stale deletion returns `409`. Product UI should prefer archive and require confirmation before calling this route.
A room with a pending run returns `409`; its user message and failure/recovery evidence cannot be deleted while model work is in flight.

### `GET /tavern/rooms/{room_id}/runs`

Returns up to `limit` recent runs (`1`–`100`, default `50`) in reverse creation order. This is the bounded debug/history window and is not used as retry-chain truth.

### `GET /tavern/rooms/{room_id}/run-recovery`

Returns up to `limit` root-chain projections (`1`–`100`, default `50`) after loading and validating complete room lineage. Each item includes the ordered `run_ids`, immutable root status, authoritative `leaf_run`, derived chain status and recovery action, plus completed/unfinished participant IDs. A recent-run page may contain only a child, but this projection still binds it to the root and suppresses retry after a completed child.

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
- schema/provider/Harness failures return `502` only after the terminal evidence is committed; the structured detail contains `code`, `run_id`, `child_run_id`, `current_revision`, and `recovery_action`;
- replaying that identical failed request returns `200` with the typed terminal recovery envelope. Clients must inspect `run.status`.

The web client automatically replays exactly once only when a `502` explicitly declares `recovery_action=replay_same_request` and a committed `run_id`. It reuses the identical URL/body, revision, and idempotency key. Network failures, malformed envelopes, and other recovery actions are never treated as authorization to invoke the mutation again.

Client reconciliation must bind the response to the active room and operation token, discard stale cross-room results, merge messages monotonically, and never allow a terminal run to regress to `pending`. HTTP success describes transport/recovery delivery only; `completed`, `partial`, `failed`, and `canceled` remain distinct domain outcomes.

Room revision claims are atomic at the database boundary. This applies to SQLite and PostgreSQL and does not depend on one Python process owning an in-memory lock.

Pending speaker steps expose `claim_count`. A generating step owns a database-clock lease renewed by heartbeat. A crashed worker can be taken over only after expiry; owner plus claim epoch fence stale commits. Every step permits at most three claims (initial plus two takeovers). Exhaustion persists a terminal `failed`/`partial` run with `tavern_run_claims_exhausted` and a `lease_recovery` Harness trace; HTTP `200` still requires the client to inspect `run.status`.

### `POST /tavern/rooms/{room_id}/runs/{run_id}/resume`

Resumes a pending run after a process or worker interruption. Completed steps and messages are reused, never regenerated. An active lease returns structured `409` with `code=tavern_run_in_progress`, its run ID, and `recovery_action=wait_and_resume`. An expired lease is claimed with a new fencing epoch; claim-budget exhaustion returns the durable terminal recovery envelope.

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


## Diagnostic events

`POST /diagnostics/events` accepts at most 100 closed `diagnostic-event-v1`
objects from source `browser` in `{ "events": [...] }` (batch limit 1.6 MiB).
It returns queue acceptance/drop counts, **not durable persistence or business
commit evidence**. Clients retry offline batches with the same event IDs;
the local diagnostic database deduplicates persisted IDs. Invalid content is
rejected with a fixed error code without echoing inputs.

`GET /diagnostics/events?after=0&limit=100` returns ordered `{sequence,event}`
items, `next_cursor`, `has_more`, and writer/read health. Optional filters: `request_id`,
`action_id`, `page_view_id`, `flow_id`, `source`, `page_path`, `severity`,
`operation_id`, `workflow`, `stage`, `resource_id`, `resource_type`, `since`, `until`. Diagnostic requests do not
recursively collect events. Source `browser` correlation fields are untrusted
hints; source `server` request IDs are allocated anew for each HTTP request.
A transport `request_finished` (including HTTP 200) does not prove domain commit.

Server events use an isolated append SQLite database under
`storage_root/diagnostics/events.sqlite3`. Current limits are 1,000 queued events
and event retention of 10,000 rows, seven days from database ingestion, or
64 MiB of UTF-8 event payload, whichever limit is reached first. Aggregate disk
retention (including indexes/WAL/spool), other diagnostic tables and audit export
remain subsequent steps in `docs/plans/unified-debug.md`.

Persona generate/save/reload accepts diagnostic correlation through the common
`X-Debug-Client-Instance-Id`, `X-Debug-Page-View-Id`, `X-Debug-Flow-Id`, and
`X-Debug-Action-Id` headers. The editor captures an action before transport and
passes it explicitly through save and its refresh; no global async action state
is used. These fields never enter model proposals or business request payloads.
Server-only `harness_reference` events point to admitted operations and canonical
terminal traces. `resource_reference` events identify saved Persona records with
the actual revision. Both are diagnostic references, not substitutes for receipt
or resource read-back. Browser ingestion rejects these names and reference fields.

Event classification uses the shared `event-classification-v1.json` fixture.
`category`, `severity`, `outcome`, and bounded `error_code` are derived from the
closed event name and HTTP status, and conflicting uploads are rejected. HTTP
errors have a failed transport outcome; successful transport still makes no
claim about domain commit. `harness_reference.harness` can identify an individual
canonical attempt with `attempt_id`, `attempt_index`, `phase`, and
`attempt_status`. Its event duration is that attempt's duration, never an added
parent-plus-child total. Canonical trace/error/content remain in Harness storage.


`GET /diagnostics/harness-index?after=&limit=100&operation_id=...` returns bounded
`diagnostic-harness-index-v1` projections and index coverage. `after` is the last
trace ID; the optional operation filter selects one admitted operation. The
separate index database stores a durable sweep cursor and one row per trace,
revisits earlier keys to catch late commits, and records missing/invalid sources
as explicit gaps. It copies only reviewed identity, registered component
versions, status and attempt metrics, not the complete trace or protected input.
`coverage.canonical_read_back_required` is always true; this eventually consistent
index is not a receipt. Trace contexts currently lack provider/model/usage/cost
bindings; these values remain null with `usage_gap`, never inferred from defaults.

`GET /diagnostics/operation-links?operation_id=...&after=&limit=100` returns
server-recorded request/client/page-view/flow/action links. Here `after` is the
last request ID. Links are written atomically with server reference events and
retained separately from the bounded event list. Missing links are reported as
`no_correlation_recorded_or_retained`; historical requests are never fabricated
from a recovered Harness trace. Index and link retention budgets remain part of
the diagnostic audit stage.


Server `provider_*` events describe the shared LiteLLM transport and carry a
reviewed `provider_metric` whitelist. A parent call includes retries/backoff;
child attempt durations must not be summed with it. Parent usage is null with
`aggregate_not_additive`; each returned attempt can record provider-reported
input/output/total token integers. Absent, negative, non-integer and unbounded
values remain null with a gap, not zero or an estimate. Responses and chat usage
keys are normalized without copying response content. Provider cost evidence and
endpoint configuration remain explicitly unavailable. `span_id` and
`parent_span_id` are diagnostic identities; the separate Harness reference uses
the actual prepared execution and never a provider tool-call ID. Browser ingestion
rejects provider metrics and event names. Existing TokenUsageService bookkeeping
is unchanged; this observer does not create another usage receipt.


Server `tool_started`, `tool_finished`, `tool_failed`, and `tool_unknown` events
wrap the existing Planning and Study tool execution boundaries. Their
`tool_metric` contains only resolved Tool Manifest workflow/stage/name,
input/result contract versions, call ceilings, timeout and bounded provider
call correlation. Unknown names produce an explicit manifest gap and are not
persisted. Arguments, result bodies, error detail and private grading material
are excluded. A successful tool result has `effect_commit_claim: "none"`;
prepared or external effects still require their canonical receipts. Provider
calls made inside a tool link their parent span to that tool, so audit consumers
must not add inclusive tool and provider durations together. Browser ingestion
rejects server tool names and metric fields.


Browser `action_started`, `action_finished`, `action_failed` and
`action_cancelled` events use the closed `action_name` vocabulary: Persona/Scene
JSON import **read**, JSON export **handoff**, Settings persistence, and Vault
create/unlock/lock/load/save/clear. Import-read completion is not domain validation
or application; browser export handoff is not proof the user retained the download.
Desktop export cancellation is separate from failure. Action observers exclude
filenames, contents, settings snapshots, secret values and exception text.
Settings persistence passes captured correlation explicitly into Vault and HTTP
calls, including after navigation. Nested local spans share an action and keep
parentage; inclusive durations are not additive. A failed diagnostic ID allocation
drops telemetry and leaves the local business action running.


Desktop startup and sidecar lifecycle events first enter a bounded native spool
at `storage_root/diagnostics/desktop-spool` (256 event/pending files). Native
payloads follow the shared `desktop-spool-v1.json` fixture: fixed event names,
instance/event identity, time/duration, exit code and loss counters only. They
contain no paths, process arguments, credentials or exception messages. Browser
ingestion cannot submit these source names or `desktop_metric` fields.

The backend consumes up to 100 files per second, validates the 16 KiB/schema
limit, and acknowledges by deleting only after synchronous diagnostic commit or
an identical persisted event. Offline and failed-write files retain their IDs;
conflicting duplicate payloads remain unacknowledged. Malformed payloads are
rejected. Event queries expose `desktop_spool: {rejected, failures}` health
(or null when unavailable). These counters are process-local; spool eviction
counters do not yet certify crash-safe or multi-process loss accounting.
Sidecar exit observations prove process lifecycle only, never business outcomes.


Browser page lifetimes emit `page_entered`/`page_left` with a unique page-view
identity and captured action. `page_path` is a closed vocabulary of the nine
current frontend routes; unknown paths become null before browser persistence
and unknown uploaded values are rejected. No query strings or dynamic URL
content are collected. Requests with captured contexts keep their originating
page after navigation. Cleanup is idempotent and cannot clear a newer view;
StrictMode replay produces separate balanced lifetimes. Page-left duration is
observed mounted lifetime, not foreground attention or domain execution time.
A browser crash may omit page-left; absence does not establish completion.


Browser `decode_failed` events identify response JSON syntax, domain decoder or
versioned stream contract rejection separately from HTTP/body transport outcomes.
The event retains the Response's captured action/page and server request ID,
including scalar/null payloads and completions after navigation. Diagnostic
storage receives no payload, decoder path, exception text or grading content.
Existing decoder errors are rethrown unchanged. The duration measures the
observed decode boundary (stream duration includes waiting for bytes), not an
additional additive stage. A successful transport can coexist with a failed
decode; neither event establishes domain commit. Tavern query-only terminal
replay remains bounded to the original explicit server directive; decoder
rejection after replay refers to that replay's distinct request ID.


Diagnostic time filters use source timestamps with explicit timezones: `since`
is inclusive and `until` exclusive; equivalent UTC offsets compare as instants.
Unknown/invalid stored timestamps do not match time filters. Cursor paging is
ascending ingest sequence with a bounded lookahead for `has_more`; it is not a
frozen audit snapshot and later events can appear after an empty page. Corrupt
or unavailable event reads return HTTP 503 `diagnostic_query_unavailable`, never
an apparently successful empty result. `health.read_failures` is separate from
writer failure counts. Stored events and operation links are revalidated before
return; invalid content and exception text are not echoed.

Operation/workflow/stage event filters match direct Harness references or the
same server request via durable operation links. New links retain canonical
workflow/stage labels; older links without these labels remain queryable by
operation ID but cannot certify complete historical workflow/stage coverage.
Resource filters currently select directly referenced Persona events, while
page-path filters select events carrying the reviewed browser page label.
These filters are diagnostic projections, not authorization or commit proof.

Harness index queries additionally accept `workflow` and `stage` and return
`has_more`. Query uses a read-only connection: absent/unavailable index storage
reports `coverage.freshness=unavailable` and never creates a blank index as a
side effect. The worker remains responsible for index creation/rebuild.


The browser query adapter (`apps/web/lib/diagnostic-query.ts`) validates event,
index and operation-link DTOs against the checked-in Pydantic schema whitelist
in `packages/shared/fixtures/diagnostics/query-schemas-v1.json`; the backend
query test checks schema drift. The adapter additionally checks classification,
attempt completeness, ascending unique identities and exact cursor continuity.
It rejects unknown nested properties rather than displaying them. Event/link
queries request 100 rows; Harness index queries request 25. Responses are bounded
to 2 MiB and five seconds, including with a caller cancellation signal. These
queries bypass collection and expose fixed failure codes without server or
network exception content. They are a validated read boundary, not a claim that
the global timeline UI or multi-page audit snapshot is complete.


Event queries include `retention` (`diagnostic-event-retention-v1`) from the same
SQLite read snapshot as their rows. It reports retained count/payload bytes,
cumulative removed count/highest removed sequence, unknown legacy ingestion
count and a conservative `cursor_gap` when removals exist above the requested
cursor. Counters persist and commit atomically with deletion, including direct
SQL deletions. This covers retained event history, not writer queue losses or
all installation history. The browser displays removal and legacy-time gaps.

Source timestamp is never used for expiration. Legacy rows without ingestion
time receive the migration time and remain marked as historically unknown;
restarting a partially completed schema migration preserves them. Retention runs
on startup, each write and at most 60 seconds after an idle cleanup interval.
The 64 MiB limit measures event payload bytes only: SQLite page allocation, WAL,
indexes, operation links and desktop spool are excluded. Accordingly
`disk_size_limit_certified` is false until aggregate retention is implemented
and measured. Canonical business/Harness evidence is untouched.


Diagnostic writer/index/spool thread-start failures are best effort and do not
abort the business lifespan. Writer start is idempotent; a stopped or failed
writer rejects new queue admissions, counts discarded queued events, and
balances queue completion bookkeeping. A failed event transaction is rolled
back and counted before the next event can proceed. Query-only native spool
persistence retains its separate synchronous acknowledgement boundary.
These failure/drop counters remain process-local and are not yet durable
writer-epoch coverage. A timed-out join does not claim a fully flushed writer;
`writer_alive` continues to report its observed thread state.
