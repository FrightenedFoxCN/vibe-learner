# Learning Plan Prompt Contract

This document describes the current prompt assembly contract for learning-plan generation in `services/ai`.

It is the source of truth for:

- the prompt template sections loaded from disk
- the exact JSON schema string injected into the system prompt
- the structured payload assembled for the user message
- the final transport shape sent to the model provider

## Source Files

- Prompt assembly: `services/ai/app/services/plan_prompt.py`
- Prompt template: `services/ai/app/prompts/learning_plan_prompt.txt`
- Prompt section loader: `services/ai/app/services/prompt_loader.py`
- Planner output model: `services/ai/app/services/model_provider.py`

## Prompt Sections

`learning_plan_prompt.txt` is parsed as an INI-like prompt file with named sections.

Current required sections:

- `[system]`: top-level planner rules and JSON-only output requirement
- `[user_instructions]`: additional writing and planning constraints injected into the user payload

The loader ignores all text outside named sections.

## Injected JSON Schema String

`services/ai/app/services/plan_prompt.py` defines a string constant named `PLAN_JSON_SCHEMA`.

Current schema string:

```text
{"course_title": string, "overview": string, "study_chapters": string[], "today_tasks": string[], "schedule": [{"unit_id": string, "title": string, "focus": string, "activity_type": "learn" | "review"}]}.
```

This string is injected into the `[system]` section by replacing `{{PLAN_JSON_SCHEMA}}`.

## User Payload Structure

`build_learning_plan_messages()` assembles a Python object and serializes it as the single user message.

Top-level payload shape:

```json
{
  "persona": {
    "id": "string",
    "name": "string",
    "source": "string",
    "summary": "string",
    "system_prompt": "string",
    "slots": [
      {
        "kind": "string",
        "label": "string",
        "content": "string"
      }
    ],
    "available_emotions": ["string"],
    "available_actions": ["string"],
    "default_speech_style": "string"
  },
  "document_title": "string",
  "learning_goal": {
    "objective": "string",
    "scene_profile_summary": "string",
    "scene_profile": {
      "scene_id": "string",
      "title": "string",
      "summary": "string",
      "tags": ["string"],
      "selected_path": ["string"],
      "focus_object_names": ["string"],
      "scene_tree": [
        {
          "id": "string",
          "title": "string",
          "scope_label": "string",
          "summary": "string",
          "atmosphere": "string",
          "rules": "string",
          "entrance": "string",
          "objects": [],
          "children": []
        }
      ]
    }
  },
  "course_outline": [
    {
      "section_id": "string",
      "title": "string",
      "level": "number",
      "page_start": "number",
      "page_end": "number",
      "children": [
        {
          "section_id": "string",
          "title": "string",
          "level": "number",
          "page_start": "number",
          "page_end": "number"
        }
      ]
    }
  ],
  "segmentation_hints": {
    "is_coarse_grained": "boolean",
    "recommend_revise_study_units": "boolean",
    "recommend_detail_tool_call": "boolean",
    "recommend_continue_tool_calls": "boolean",
    "recommend_min_tool_rounds": "number",
    "reason": "string",
    "plannable_unit_count": "number",
    "max_unit_page_span": "number",
    "units_with_subsections": "number",
    "sparse_subsection_unit_count": "number",
    "total_subsection_count": "number"
  },
  "study_units": [
    {
      "unit_id": "string",
      "title": "string",
      "page_start": "number",
      "page_end": "number",
      "summary": "string",
      "unit_kind": "string",
      "include_in_plan": "boolean",
      "subsection_titles": ["string"],
      "related_section_ids": ["string"],
      "detail_tool_target_id": "string"
    }
  ],
  "instructions": ["string"]
}
```

## Transport String

The model does not receive the user payload as a native JSON object. It receives a chat message array where:

- the system message is plain text from the `[system]` section after schema substitution
- the user message is `json.dumps(user_prompt, ensure_ascii=False, indent=2)`

Current transport shape:

```json
[
  {
    "role": "system",
    "content": "string"
  },
  {
    "role": "user",
    "content": "{\n  \"persona\": { ... },\n  \"document_title\": \"...\",\n  \"learning_goal\": { ... },\n  \"segmentation_hints\": { ... },\n  \"study_units\": [ ... ],\n  \"instructions\": [ ... ]\n}"
  }
]
```

Important details:

- `ensure_ascii=False` keeps Chinese text unescaped
- `indent=2` means the user message is a pretty-printed JSON string, not a minified string
- only one user message is sent for plan generation

## Output Contract

The planner must return a single JSON object matching the schema above.

Required planner-facing semantic rules:

- `course_title` is the plan header, not the learner goal
- `overview` is 1 to 2 summary sentences
- `study_chapters` is the ordered chapter list used for navigation
- `study_chapters` should be as fine-grained as the textbook structure allows, preferably down to subchapter-level anchors when supported by evidence
- `today_tasks` is the ordered actionable task list
- `schedule[].unit_id` must point to an active study unit
- when `segmentation_hints` or tool evidence show coarse or sparse subsection structure, the planner is expected to keep using tools before finalizing

## Tool-Loop Expectations

The plan runner now biases toward repeated tool use instead of early stopping:

- it allows up to 8 model rounds for plan generation
- it can inject up to 3 follow-up nudges asking the model to continue tool refinement
- if no tools were called yet, it will explicitly push for tool use before accepting a final answer
- if study units still look coarse, it may keep nudging until several tool calls have been made

Prompt wording also explicitly encourages:

- repeated `revise_study_units` calls when directory granularity is still insufficient
- multiple `get_study_unit_detail` / page-range evidence calls across representative units
- continued refinement until downstream chapter/subchapter selection can be fine-grained

## Change Rules

When changing learning-plan prompting:

1. Update `services/ai/app/services/plan_prompt.py` if the transport object changes.
2. Update `services/ai/app/prompts/learning_plan_prompt.txt` if prompt wording or schema wording changes.
3. Update `services/ai/app/services/model_provider.py` if output parsing changes.
4. Update `docs/plan-text-contract.md` if learner-facing field meaning changes.
5. Update tests that assert exact planner payload or exact JSON field names.
