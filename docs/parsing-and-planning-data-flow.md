# Parsing And Planning Data Flow

This document traces the current backend data chain for textbook parsing and learning-plan generation in `services/ai`.

## Purpose

Use this when changing:

- PDF parsing or OCR fallback
- study-unit cleanup
- planning context assembly
- OpenAI tool-enabled plan generation
- local debug or trace persistence

This doc describes the actual runtime path from HTTP entrypoint to local JSON artifacts.

## 1. Document Parsing Chain

### Upload shell creation

HTTP entry:

- `POST /documents`

Code path:

- `services/ai/app/api/routes.py`
- `DocumentService.create_document()` in `services/ai/app/services/documents.py`

Writes:

- uploaded PDF to `services/ai/data/uploads/{document_id}.pdf`
- document shell row into `services/ai/data/documents.json`

Initial record shape:

- `DocumentRecord.status = "uploaded"`
- `ocr_status = "pending"`
- empty `sections`
- empty `study_units`
- `debug_ready = False`

### Parse execution

HTTP entry:

- `POST /documents/{document_id}/process`
- `POST /documents/{document_id}/process/stream`

Code path:

1. `routes.process_document()` or `routes.process_document_stream()`
2. `DocumentService.process_document()`
3. `DocumentParser.parse()`
4. `StudyArrangementService.build_study_units()`

### Parser internals

`DocumentParser.parse()` in `services/ai/app/services/document_parser.py` builds one `DocumentDebugRecord`.

Main steps:

1. Read PDF with PyMuPDF.
2. Try TOC-based section detection with `_build_sections_from_toc()`.
3. Parse every page through `_parse_page()`.
4. Fall back to OCR when `force_ocr=True` or extracted text is below `TEXT_DENSITY_THRESHOLD`.
5. Detect recurring headers and footers, then strip them.
6. Extract heading candidates from page text and OCR text.
7. Build `sections` from TOC or heuristic heading seeds.
8. Build `chunks` by section-aware page segmentation.
9. Return `DocumentDebugRecord` with:
   `pages`, `sections`, `chunks`, `warnings`, `ocr_applied`, `extraction_method`.

Important parser outputs:

- `pages`: per-page previews, char counts, heading candidates, extraction source
- `sections`: raw parser-detected textbook structure
- `chunks`: chunked textbook content later used by planning tools
- `warnings`: OCR and parse-quality signals

### Study-unit cleanup

After parsing, `DocumentService.process_document()` calls `StudyArrangementService.build_study_units()`.

Transformation:

- input: `DocumentDebugRecord.sections` and `DocumentDebugRecord.pages`
- output: cleaned `StudyUnitRecord[]`

Key cleanup behavior:

- prefers level-1 sections as anchors
- recovers titles from page preview or heading candidates when section titles are weak
- classifies units into `chapter`, `front_matter`, or `back_matter`
- sets `include_in_plan`
- merges adjacent units when needed
- guarantees at least one plannable unit

### Parse persistence

`DocumentService.process_document()` persists three backend-facing artifacts:

1. `services/ai/data/documents.json`
   Updates the `DocumentRecord` with:
   `status`, `ocr_status`, `sections`, `study_units`, `study_unit_count`, `page_count`, `chunk_count`, `preview_excerpt`, `debug_ready`.
2. `services/ai/data/document_debug/{document_id}.json`
   Stores the full `DocumentDebugRecord`, including cleaned `study_units`.
3. `services/ai/data/document_process_stream/{document_id}.json`
   Stores stream/progress events through `StreamReportRecorder`.

Important field transition:

- raw parser `sections` stay in `DocumentDebugRecord.sections`
- cleaned planning `study_units` are written to both `DocumentRecord.study_units` and `DocumentDebugRecord.study_units`
- `DocumentRecord.sections` is reduced to plannable top-level unit coverage for UI/session usage

## 2. Planning Context Chain

HTTP entry:

- `GET /documents/{document_id}/planning-context`

Code path:

1. `routes.get_document_planning_context()`
2. `DocumentService.require_document()`
3. `DocumentService.require_debug_report()`
4. `build_learning_plan_context()` in `services/ai/app/services/plan_prompt.py`
5. `get_learning_plan_tool_specs()` in `services/ai/app/services/model_provider.py`

Returned payload:

- `course_outline`
- `study_units`
- `detail_map`
- `available_tools`

### How planning context is assembled

`build_learning_plan_context()` derives debug-facing planning views from the parsed document.

`course_outline`:

- built from raw `debug_report.sections`
- preserves level-1 and level-2 structure
- kept for `/debug` inspection and planner-input comparison

`study_units`:

- built from cleaned `StudyUnitRecord[]`
- adds `subsection_titles`, `related_section_ids`, and `detail_tool_target_id`
- used as the model-visible plannable unit list

`detail_map`:

- keyed by `study_unit_id`
- joins each cleaned unit to:
  `related_sections`, `subsection_titles`, `chunk_count`, `chunk_excerpts`
- acts as the backing store for planner tool calls

This is the bridge from parser artifacts to plan-model grounding.

## 3. Learning Plan Generation Chain

HTTP entry:

- `POST /learning-plans`
- `POST /learning-plans/stream`

Code path:

1. `routes.create_learning_plan()` or `routes.create_learning_plan_stream()`
2. `persona_engine.require_persona()`
3. `document_service.require_document()`
4. optional `document_service.require_debug_report()`
5. `LearningPlanService.create_plan()`
6. `StudyArrangementService.build_plan()`
7. `ModelProvider.generate_learning_plan()`

### Provider selection

`services/ai/app/core/bootstrap.py` builds the provider from `services/ai/.env`.

Relevant env keys:

- `VIBE_LEARNER_PLAN_PROVIDER`
- `OPENAI_API_KEY`
- `OPENAI_BASE_URL`
- `OPENAI_PLAN_MODEL`
- `OPENAI_TIMEOUT_SECONDS`

Behavior:

- `mock` uses `MockModelProvider`
- `openai` uses `OpenAIModelProvider`
- missing API key while `openai` is requested falls back to `MockModelProvider`

Transport stability notes for `OpenAIModelProvider`:

- all LiteLLM-backed completion, responses, and embedding calls now share one transient-retry wrapper
- retries only cover timeout/network failures and transient upstream HTTP statuses (`408`, `409`, `425`, `500`, `502`, `503`, `504`)
- rate-limit and invalid-payload classes still surface as-is so upstream failure reasons remain visible

Plan generation also records successful semantic recoveries inside planner trace data:

- transport retries resolved inside a round
- `content_filter` recovery retries
- empty-response recovery retries

These successful recoveries are intended for debug inspection and trace review, not for the main plan UI.

### Heuristic first pass

`LearningPlanService.create_plan()` always builds a heuristic base plan first through `StudyArrangementService.build_plan()`.

This produces a `LearningPlanRecord` shell with:

- `course_title`
- `objective`
- `overview`
- `study_chapters` (ordered study chapters used for downstream navigation)
- `today_tasks`
- `study_units`
- `schedule`

This heuristic result is then refined by the selected model provider.

### Model planning pass

`OpenAIModelProvider.generate_learning_plan()` does the following:

1. rebuilds planning context with `build_learning_plan_context()`
2. builds planner messages with `build_learning_plan_messages()`, using cleaned `study_units` as the model-visible structural input
3. runs `OpenAIPlanRunner`
4. optionally exposes tool definitions when `detail_map` is available
5. loops through up to 4 rounds of model responses
6. executes tool calls locally
7. extracts final strict JSON payload

Planner tools:

- `get_study_unit_detail`
- `revise_study_units`
- `read_page_range_content`
- `read_page_range_images` (when multimodal is enabled)

Tool backing data:

- `get_study_unit_detail` reads from `detail_map`
- `read_page_range_content` reads from `debug_report.chunks`

Model output is parsed into:

- `course_title`
- `overview`
- `study_chapters` (ordered study chapters used for downstream navigation)
- `today_tasks`
- `schedule`

### Plan reconciliation

`LearningPlanService.create_plan()` merges model output back into the heuristic plan.

Important reconciliation rules:

- schedule rows are filtered to known `study_unit.id` values only
- heuristic values remain as fallback when model fields are empty
- persisted `study_units` come from the backend cleanup step, not from model invention

This is the main guardrail that prevents schedule rows from referencing unknown units.

## 4. Plan Persistence And Traces

When plan generation succeeds, the backend writes:

1. `services/ai/data/plans.json`
   Stores the final `LearningPlanRecord`.
2. `services/ai/data/learning_plan_stream/{document_id}.json`
   Stores progress and error/completion events.
3. `services/ai/data/planning_trace/{document_id}.json`
   Stores `PlanGenerationTraceRecord` only when the model provider produced a trace.

Trace contents:

- one record per model round
- assistant content
- extracted reasoning text when available upstream
- elapsed time
- tool call arguments and results

The `/documents/{document_id}/planning-trace` endpoint now returns a wrapper payload with `has_trace`, `summary`, and `trace`.

## 5. Stored Artifact Map

Current local storage categories involved in this chain:

- `services/ai/data/uploads/`
  raw uploaded PDFs
- `services/ai/data/documents.json`
  document shells and post-parse summaries
- `services/ai/data/document_debug/`
  parser/debug payloads with pages, sections, chunks, warnings, and study units
- `services/ai/data/document_process_stream/`
  parse progress stream records
- `services/ai/data/plans.json`
  persisted learning plans
- `services/ai/data/learning_plan_stream/`
  plan-generation progress stream records
- `services/ai/data/planning_trace/`
  per-document model trace for tool-enabled planning

Some files are created lazily. If a document has never been planned with trace capture, `planning_trace/{document_id}.json` may not exist yet.

## 6. Main Handoff Objects

The chain is easiest to reason about by watching these object boundaries:

1. `UploadFile`
2. `DocumentRecord`
3. `DocumentDebugRecord`
4. `StudyUnitRecord[]`
5. planning context payload:
   `course_outline`, `study_units`, `detail_map`
6. heuristic `LearningPlanRecord`
7. model `PlanModelReply`
8. final persisted `LearningPlanRecord`

## 7. Best Intervention Points

When changing parser quality:

- edit `services/ai/app/services/document_parser.py`
- inspect `document_debug/{document_id}.json`
- inspect `/documents/{id}/process-events`

When changing study-unit cleanup:

- edit `services/ai/app/services/study_arrangement.py`
- inspect `DocumentDebugRecord.study_units`
- inspect `/documents/{id}/planning-context`

When changing planning prompt or tool grounding:

- edit `services/ai/app/services/plan_prompt.py`
- edit `services/ai/app/services/model_provider.py`
- inspect `/documents/{id}/planning-context`
- inspect `/documents/{id}/planning-trace`
- inspect `/documents/{id}/plan-events`
