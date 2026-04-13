# Learning Plan Prompt Contract

This document describes the current prompt assembly contract for learning-plan generation in `services/ai`.

## Source Files

- Prompt assembly: `services/ai/app/services/plan_prompt.py`
- Prompt template: `services/ai/app/prompts/learning_plan_prompt.txt`
- Planner output model: `services/ai/app/services/model_provider.py`

## Prompt Sections

`learning_plan_prompt.txt` is parsed as an INI-like prompt file with named sections.

Current required sections:

- `[system]`: top-level planner rules and JSON-only output requirement
- `[user_instructions]`: additional planning constraints injected into the user payload

## Injected JSON Schema String

`services/ai/app/services/plan_prompt.py` defines a string constant named `PLAN_JSON_SCHEMA`.

Current schema string:

```text
{"course_title": string, "overview": string, "today_tasks": string[], "schedule": [{"unit_id": string, "title": string, "focus": string, "activity_type": "learn" | "review", "schedule_chapters": [{"id": string, "title": string, "anchor_page_start": number, "anchor_page_end": number, "source_section_ids": string[], "content_slices": [{"page_start": number, "page_end": number, "source_section_ids": string[]}]}]}]}.
```

There is no top-level `study_chapters` field anymore.

## User Payload Structure

`build_learning_plan_messages()` serializes one user payload with these top-level keys:

- `plan_creation_mode`
- `document_available`
- `persona`
- `document_title`
- `learning_goal`
- `course_outline`
- `segmentation_hints`
- `study_units`
- `instructions`

Important structural inputs:

- `course_outline` is raw parser-oriented chapter structure for grounding.
- `study_units` is the cleaned planning backbone. Each item carries:
  - `unit_id`
  - `title`
  - `page_start`
  - `page_end`
  - `summary`
  - `unit_kind`
  - `include_in_plan`
  - `subsection_titles`
  - `related_section_ids`
  - `detail_tool_target_id`
- `segmentation_hints` tells the model whether the current structure is too coarse and whether more tool use is expected before finalizing.

## Transport Shape

The provider still sends:

- one system message with the prompt template after schema substitution
- one user message containing `json.dumps(user_prompt, ensure_ascii=False, indent=2)`

The user payload is therefore sent as a pretty-printed JSON string, not as native structured tool input.

## Output Contract

The planner must return a single JSON object matching the schema above.

Required semantic rules:

- `course_title` is the learner-facing plan header.
- `overview` is a short summary paragraph.
- `today_tasks` is the current actionable task list.
- `schedule[].unit_id` must point to an existing `study_unit.id`.
- `schedule[].schedule_chapters[]` is required for every schedule item.
- `schedule[].schedule_chapters[]` must stay inside the parent study unit's page range and content scope.
- `schedule[].schedule_chapters[].title` should name concrete chapter or subchapter content, not abstract themes.
- `schedule[].schedule_chapters[].content_slices[]` may be discontinuous, but must remain within the parent study unit.

## Tool-Loop Expectations

The planner may call:

- `get_study_unit_detail`
- `revise_study_units`
- `read_page_range_content`
- `read_page_range_images`

Prompt wording and runner behavior both bias toward continued tool use when:

- study units are still coarse
- subsection hints are sparse or noisy
- the model has not yet gathered enough evidence to emit useful `schedule_chapters`

## Change Rules

When changing learning-plan prompting:

1. Update `services/ai/app/services/plan_prompt.py` if the transport payload or schema changes.
2. Update `services/ai/app/prompts/learning_plan_prompt.txt` if prompt wording changes.
3. Update `services/ai/app/services/model_provider.py` if output parsing or fallback schedule-chapter generation changes.
4. Update `docs/plan-text-contract.md` if learner-facing field meaning changes.
5. Update tests that assert exact planner JSON field names.
