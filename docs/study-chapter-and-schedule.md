# Study Chapter And Schedule

This document defines the current runtime meaning of `学习章节` and `学习排期` after the schedule-chapter refactor.

Use it before discussing backend models, frontend routing, or persisted plan data.

## 1. Canonical Terms

### Raw Section

- Chinese: `原始章节`
- Type: `DocumentDebugRecord.sections[]`
- Meaning: parser-detected textbook structure
- Main use: debug, grounding, citations, planning tools

### Study Unit

- Chinese: `学习单元`
- Type: `StudyUnitRecord` / `StudyUnit`
- Meaning: cleaned plannable content segment derived from raw sections
- Stable identity: `study_unit.id`
- Main use: planning backbone, session scope, progress aggregation

This is the only canonical session entry and session scope.

### Schedule Item

- Chinese: `学习排期项`
- Type: `StudyScheduleRecord`
- Meaning: executable plan row bound to one `study_unit.id`
- Stable identity: `schedule.id`
- Main use: execution, status tracking, first-level plan navigation

### Schedule Chapter

- Chinese: `学习章节`
- Type: `ScheduleChapterRecord`
- Location: `LearningPlanRecord.schedule[].schedule_chapters[]`
- Meaning: learner-facing chapter or subchapter item nested under one schedule item
- Stable identity: `schedule_chapter.id`
- Main use: second-level plan navigation, page anchoring, local preview context

This is no longer a top-level plan field.

### Study Unit Progress

- Chinese: `学习单元进度`
- Type: `StudyUnitProgressRecord`
- Location: `LearningPlanRecord.study_unit_progress[]`
- Meaning: derived progress view aggregated by `study_unit.id`
- Main use: progress summaries, not authored structure

### Session Scope

- Chinese: `会话作用域`
- Type: `StudySessionRecord.study_unit_id`
- Meaning: the active learning scope for chat/session routing
- Runtime rule: always points to the parent study unit, never to a schedule chapter

## 2. Naming Rules

Use these names consistently:

- `原始章节` = parser output `Section`
- `学习单元` = cleaned plannable unit `Study Unit`
- `学习排期项` = executable row `Schedule Item`
- `学习章节` = nested `Schedule Chapter`
- `学习单元进度` = derived `Study Unit Progress`
- `会话作用域` = `StudySession.study_unit_id`

Avoid these ambiguous phrasings:

- saying `section` when you mean `study unit`
- saying `章节列表` when you mean top-level plan navigation
- saying `章节进度` when the data is keyed by `study_unit.id`

## 3. Learning Chapter Data Chain

The current chapter chain is:

1. `DocumentParser.parse()` builds raw `DocumentDebugRecord.sections`.
2. `StudyArrangementService.build_study_units()` converts raw sections into cleaned `StudyUnitRecord[]`.
3. `StudyArrangementService.build_plan()` creates `schedule[]`.
4. Each schedule item builds `schedule_chapters[]` from the parent study unit's source sections and page coverage.
5. Frontend `/plan` renders `schedule[]` as the first level and `schedule_chapters[]` as the second level.
6. Frontend `/study` lets the learner choose:
   - one parent schedule item
   - one nested schedule chapter
7. Only the parent schedule item's `unit_id` is written into `StudySession.study_unit_id`.

### Resulting ownership

- Structural source of truth: `study_units`
- Execution source of truth: `schedule`
- Learner-facing subchapter directory: `schedule[].schedule_chapters`
- Live chat routing id: `study_session.study_unit_id`

## 4. Learning Schedule Data Chain

The current schedule chain is:

1. `StudyArrangementService.build_plan()` selects plannable `study_units`.
2. `_build_schedule()` creates heuristic `schedule[]`.
3. Each `schedule` item receives nested `schedule_chapters[]`.
4. `ModelProvider.generate_learning_plan()` may replace the heuristic schedule, but must still emit nested `schedule_chapters[]`.
5. `LearningPlanService.create_plan()` filters schedule rows to known `study_unit.id` values and validates nested schedule chapters against the parent unit scope.
6. `study_unit_progress` and `progress_summary` are derived from persisted `schedule[]`.
7. Frontend progress actions update `schedule[].status`, then backend recomputes derived summaries.

### Resulting ownership

- Structural binding key: `schedule.unit_id -> study_unit.id`
- Execution state source of truth: `schedule[].status`
- Nested navigation structure: `schedule[].schedule_chapters[]`
- Progress summaries: derived, not authored

## 5. Relationship Matrix

| Term | Main field | Has stable ID | Has page range | Main use |
| --- | --- | --- | --- | --- |
| Raw Section | `DocumentDebugRecord.sections[]` | yes | yes | debug / grounding |
| Study Unit | `study_units[]` | yes | yes | planning backbone / session scope |
| Schedule Item | `schedule[]` | yes | indirect via `unit_id` | execution / progress |
| Schedule Chapter | `schedule[].schedule_chapters[]` | yes | yes | learner-facing nested navigation |
| Session Scope | `StudySession.study_unit_id` | yes | indirect via study unit | chat routing |

## 6. Current Runtime Caveats

### `DocumentRecord.sections` is still a projected list

After processing, `DocumentRecord.sections` is projected from plannable study units, not the raw textbook tree.

Use:

- `DocumentDebugRecord.sections` for raw parser structure
- `DocumentRecord.study_units` for cleaned planning structure

### Schedule chapters are subordinate, not a new scope layer

`schedule_chapters[]` can be finer-grained than the parent study unit and can contain discontinuous `content_slices[]`, but they do not create a new session scope.

They are for:

- page anchoring
- learner-facing labels
- preview/navigation context

They are not for:

- session identity
- plan progress keys
- memory retrieval scope

### Raw `section_id` still exists in citations and debug artifacts

The refactor does not rename parser- or citation-level `section_id`.

Use raw `section_id` only when the ID refers to:

- parser sections
- extracted chunks
- grounded citations

Use `study_unit_id` for session, memory, and progress data.

## 7. Practical Discussion Rules

Phrase future changes like this:

- `把学习单元切得更细`
- `让排期项绑定学习单元`
- `让学习章节成为排期项下的可选子项`
- `会话作用域始终落在学习单元`
- `章节进度改成学习单元进度`

Avoid saying:

- `把章节和 section 对齐`
- `section 切换`
- `编辑顶层学习章节数组`

## 8. Bottom Line

The current system has one canonical content backbone:

- `Study Unit`

One canonical execution backbone:

- `Schedule Item`

And one nested learner-facing directory layer:

- `Schedule Chapter`

Session routing and progress aggregation both belong to the study-unit layer, not the chapter-label layer.
