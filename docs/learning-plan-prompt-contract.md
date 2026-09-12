# Learning Plan Prompt Contract

This document describes the current prompt assembly contract for learning-plan generation in `services/ai`.

## Source Files

- Prompt assembly: `services/ai/app/services/plan_prompt.py`
- Prompt template: `services/ai/app/prompts/learning_plan_prompt.txt`
- Planner proposal and tool contracts: `services/ai/app/models/planning.py`
- Planner runner/transport: `services/ai/app/services/model_provider.py`

## Prompt Sections

`learning_plan_prompt.txt` is parsed as an INI-like prompt file with named sections.

Current required sections:

- `[system]`: top-level planner rules and JSON-only output requirement
- `[user_instructions]`: additional planning constraints injected into the user payload

## Injected JSON Schema String

`services/ai/app/services/plan_prompt.py` defines a string constant named `PLAN_JSON_SCHEMA`.

Current schema string:

```text
{"schema_name": "learning-plan-proposal", "schema_version": "learning-plan-proposal-v1", "course_title": string, "overview": string, "today_tasks": string[], "schedule": [{"unit_id": string, "title": string, "focus": string, "activity_type": "learn" | "review", "schedule_chapters": [{"title": string, "anchor_page_start": integer, "anchor_page_end": integer, "source_section_ids": string[], "content_slices": [{"page_start": integer, "page_end": integer, "source_section_ids": string[]}]}]}]}.
```

There is no top-level `study_chapters` field anymore.

## User Payload Structure

`build_learning_plan_messages()` serializes one user payload with these top-level keys:

- `plan_creation_mode`
- `document_available`
- `persona`
- `document_title`
- `learning_goal`
- `planning_feedback`
- `current_plan`
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

The planner must return a single JSON object that strictly decodes as `LearningPlanProposalV1` (`extra="forbid"`, strict primitive types). The runner permits at most one bounded schema-repair attempt before failure.

Required semantic rules:

- `course_title` is the learner-facing plan header.
- `overview` is a short summary paragraph.
- `today_tasks` is the current actionable task list.
- `schedule[].unit_id` must point to an existing `study_unit.id`.
- `schedule[].schedule_chapters[]` is required for every schedule item.
- `schedule[].schedule_chapters[]` must stay inside the parent study unit's page range and content scope.
- `schedule[].schedule_chapters[].title` should name concrete chapter or subchapter content, not abstract themes.
- `schedule[].schedule_chapters[].content_slices[]` may be discontinuous, but must remain within the parent study unit.
- model output never owns plan, schedule, or chapter IDs, revision, status, timestamps, or persisted progress; the application assigns and validates committed identities after decode.

## Source-minimal-v3 production default

`source-minimal-v3` is the user-authorized production-default text strategy for learner-facing Learning Plan fields, specifically `focus`, `today_tasks`, and learning activities. It requires the smallest useful rewrite that remains faithful to the source:

- preserve complete source spans when dropping a noun-phrase prefix or other qualifier would change the referent;
- preserve source-time epistemic and workflow status such as planned, proposed, scheduled, recorded, reported, observed, listed, or acknowledged instead of strengthening it into an established fact;
- keep study-time estimates separate from the real-world duration of an event described by the source;
- do not invent unsupported operations, submissions, approvals, or workflow mechanisms.

This wording policy does not transfer application-owned identity, revisions, timestamps, progress, or effects into the model proposal. Existing strict decode, invariant validation, tool authorization, and commit boundaries remain authoritative.

The reviewed Planning behavior is registered as `LearningPlanPrompt@planning-prompt-v3`; the corresponding Study Chat behavior is registered as `StudyChatPrompt@study-chat-prompt-v2`. Planning v3 adds one bounded representative excerpt per Study Unit, source-structure fidelity rules, honest page-read truncation metadata, and a one-round tool finalization policy. Historical v1/v2 traces and archived experiment evidence remain unchanged.

The same strategy is separately adopted for Study Chat, including the rule that a tool effect may be described as completed only after successful execution. This document does not otherwise define the Study Chat contract. The adoption does not change Tavern, Persona/Scene generation, Harness schemas, or multimodal defaults.

The supporting evidence consists of development synthetic cases reviewed manually for semantic fidelity. It is not a keyword-based pass check and has not independently certified learning outcomes, production traffic quality, or generalization to the excluded workflows.

## Tool-Loop Expectations

The planner may call:

- `get_study_unit_detail`
- `ask_planning_question`
- `estimate_plan_completion`
- `revise_study_units`
- `read_page_range_content`
- `read_page_range_images`

All six tools decode strict `planning-tool-arguments-v1` arguments and return a strict `planning-tool-result-v1` success or typed error projection. Malformed JSON, extra fields, wrong primitive types, invalid ranges, or unavailable tool context fail without executing the tool. The effective tool set is filtered by runtime configuration and context (for example, page images require multimodal support).

Prompt wording and runner behavior both bias toward continued tool use when:

- study units are still coarse
- subsection hints are sparse or noisy
- the model has not yet gathered enough evidence to emit useful `schedule_chapters`

## Runtime evidence and budget boundaries

`get_study_unit_detail` permits at most three calls per model round and four per operation, executed serially. Detail excerpts follow the revised Study Unit page range; page-text character limits include separators, and image page ranges are bounded before allocation. Complete the tool-result batch before attaching images, and retain tool evidence during strict proposal repair.

A single unit is not coarse solely because its count is one. The existing wide-source criterion requires at most two units and an at-least-80-page span; sparse detail signals remain independent. `estimate_plan_completion` is labeled “学习单元结构估分” and assesses source structure metadata, not the generated plan's activities, goal coverage or factual quality.

Repair and commit validation share chapter invariants. The repair prompt distinguishes application timestamps from learning durations. See [model runtime quality](model-runtime-quality.md) for adopted scope, commit references and verification limits.

## Change Rules

When changing learning-plan prompting:

1. Update `services/ai/app/services/plan_prompt.py` if the transport payload or schema changes.
2. Update `services/ai/app/prompts/learning_plan_prompt.txt` if prompt wording changes.
3. Update `services/ai/app/models/planning.py` and the shared frontend decoder contracts when proposal or tool argument/result schemas change.
4. Update `services/ai/app/services/model_provider.py` if output decode/repair or committed schedule projection changes.
5. Update `docs/plan-text-contract.md` if learner-facing field meaning changes.
6. Update tests that assert exact planner JSON field names.
