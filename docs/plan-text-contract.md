# Plan Text Contract

This document defines the learner-facing text fields used by learning plans across backend models, shared contracts, prompts, and frontend UI.

## Canonical Field Meanings

### `course_title`

- Source of truth: heuristic planner or model planner
- Ownership: persisted on `LearningPlan`
- Meaning: textbook-grounded plan header
- UI role: main heading of the `Plan Overview Panel`
- Must not be used as: learner goal statement or schedule item text

Examples:

- `高等数学 / 极限与连续`
- `Discrete Mathematics / Chapter 1 Foundations`

### `objective`

- Source of truth: learner input at plan creation time
- Ownership: `LearningGoalInput.objective`, persisted on `LearningPlan`
- Meaning: learner-authored study goal
- UI role: supporting metadata under the plan title
- Must not be used as: generated overview or task text

Examples:

- `在两周内掌握这本教材的第一章并完成一次复习。`
- `Prepare for the linear algebra midterm by finishing Chapters 1-3.`

### `overview`

- Source of truth: heuristic planner or model planner
- Ownership: persisted on `LearningPlan`
- Meaning: short learner-facing summary of the whole plan
- UI role: summary paragraph in the `Plan Overview Panel`
- Writing rule: 1 to 2 sentences
- Must not be used as: heading or task list item

Examples:

- `本轮先完成极限基础的首轮精读，再安排一次短复习来稳固定义和典型例题。`
- `This plan starts with the foundations unit, then adds a short review before practice.`

### `today_tasks[]`

- Source of truth: heuristic planner or model planner
- Ownership: persisted on `LearningPlan`
- Meaning: actionable learner tasks for the current session or day
- UI role: ordered action list
- Writing rule: imperative or task-oriented text
- Must not be used as: chapter directory text

Examples:

- `阅读第 12-18 页，标出 2 条定义与 1 个例题。`
- `用自己的话复述牛顿第一定律，并记录一个不确定点。`

### `schedule[].title`

- Source of truth: heuristic planner or model planner
- Ownership: persisted on `LearningPlan.schedule[]`
- Meaning: learner-facing title of one executable schedule item
- UI role: first-level selectable row in `/plan` and `/study`
- Writing rule: should read like one study block, not like a whole-course title
- Must not be used as: raw section label or progress summary prose

Examples:

- `极限基础 精读`
- `Chapter 1 Foundations Review`

### `schedule[].focus`

- Source of truth: heuristic planner or model planner
- Ownership: persisted on `LearningPlan.schedule[]`
- Meaning: concise execution focus for the schedule item
- UI role: supporting hint below schedule titles
- Writing rule: compact, specific, action-relevant
- Must not be used as: replacement for `today_tasks`

Examples:

- `理解极限定义，并完成首轮例题辨析。`
- `Connect the chart with the surrounding explanation and formulas.`

### `schedule[].schedule_chapters[].title`

- Source of truth: heuristic planner or model planner
- Ownership: persisted inside each schedule item
- Meaning: learner-facing chapter or subchapter label nested under one schedule item
- UI role: second-level selectable row in `/plan` and `/study`
- Writing rule: should point to concrete textbook content, ideally chapter or subchapter granularity
- Must not be used as: standalone session scope id

Examples:

- `1.1 Sets`
- `力学导论：惯性与受力`

### `study_unit_progress[].objective_fragment`

- Source of truth: derived from schedule rows and status
- Ownership: persisted derived field on `LearningPlan`
- Meaning: unit-level progress hint aggregated by `study_unit.id`
- UI role: progress summary, not navigation
- Must not be used as: authored schedule text

## Cross-Layer Mapping

### Backend

- `LearningGoalInput.objective`
- `LearningPlanRecord.course_title`
- `LearningPlanRecord.objective`
- `LearningPlanRecord.overview`
- `LearningPlanRecord.today_tasks`
- `LearningPlanRecord.schedule[].title`
- `LearningPlanRecord.schedule[].focus`
- `LearningPlanRecord.schedule[].schedule_chapters[].title`
- `LearningPlanRecord.study_unit_progress[].objective_fragment`

### Shared TypeScript

- `LearningGoal.objective`
- `LearningPlan.courseTitle`
- `LearningPlan.objective`
- `LearningPlan.overview`
- `LearningPlan.todayTasks`
- `LearningPlan.schedule[].title`
- `LearningPlan.schedule[].focus`
- `LearningPlan.schedule[].scheduleChapters[].title`
- `LearningPlan.studyUnitProgress[].objectiveFragment`

### Frontend Display

- `Plan Overview Panel` title: `courseTitle`
- `Plan Overview Panel` supporting goal text: `objective`
- `Plan Overview Panel` summary text: `overview`
- `Plan Overview Panel` action list: `todayTasks`
- `Plan Overview Panel` first-level plan directory: `schedule[]`
- `Plan Overview Panel` second-level plan directory: `schedule[].scheduleChapters[]`
- `Study Console` session scope selector: parent `schedule[]`
- `Study Console` local sub-navigation: `scheduleChapter[]`

## Naming Rules For Future Changes

- Use `title` only for heading-level or directory-level text.
- Use `overview` only for paragraph summaries.
- Use `focus` for short execution hints.
- Use `task` for actionable learner steps.
- Use `study unit` for session scope and progress aggregation.
- Use `schedule chapter` for nested learner-facing chapter labels under one schedule item.

Do not reintroduce a top-level `study_chapters[]` label array.
