# Frontend Workspace Boundary

This document defines the current frontend boundary for the split workspace pages in `apps/web`.

## Goal

The frontend is intentionally split so rendering, async workflows, state transitions, pure state rules, and UI copy do not collapse back into one page component.

When changing this area, preserve the separation below unless there is a clear architectural reason to move it.

## Page Split

- `/` = navigation home
- `/plan` = `Plan Workspace` (upload, process, generate, history)
- `/study` = `Chapter Dialogue Workspace` (chat + PDF + chapter switching)
- `/persona-spectrum` = `Persona Layer Workspace` (persona slots, style tuning, import/export)
- `/scene-setup` = `Scene Setup Workspace` (world-to-classroom layered scene editing)

`/plan` and `/study` share one runtime state source through `LearningWorkspaceProvider`.

## Boundary Map

### Page Composition

File:

- `apps/web/components/learning-workspace.tsx` (`/plan`)
- `apps/web/components/study-dialog-page.tsx` (`/study`)

Responsibilities:

- compose page-level UI from smaller blocks
- bind controller state and actions into component props
- contain page-local layout and presentation styles only

Must not own:

- API calls
- workflow orchestration
- multi-step state transition logic
- repeated UI copy constants

### Workflow Controller

File:

- `apps/web/hooks/use-learning-workspace-controller.ts`

Responsibilities:

- orchestrate async workflows:
  - initial snapshot load
  - focus-triggered snapshot refresh
  - document upload and processing
  - learning plan generation
  - study session creation
  - study chat send/reply
  - study session chapter switching
- translate backend results into reducer actions
- expose page-ready derived state and actions

Must not own:

- JSX rendering
- inline style definitions
- complex pure state transition rules that can be expressed without side effects

### Reducer State Layer

File:

- `apps/web/lib/learning-workspace-reducer.ts`

Responsibilities:

- define the canonical `LearningWorkspaceState`
- define reducer actions
- apply state transitions in one place
- keep notice, busy, session, response, selection, and snapshot application behavior consistent

Must not own:

- network requests
- browser event wiring
- view rendering

### Pure State Utilities

File:

- `apps/web/lib/learning-workspace-state.ts`

Responsibilities:

- resolve snapshot application results
- upsert document records
- build default study-session creation input

These functions should stay deterministic and side-effect free.

### Plan View Data

File:

- `apps/web/lib/plan-panel-data.ts`

Responsibilities:

- sort plan history
- resolve selected plan ids
- map records into `Plan Overview Panel` selection items
- preserve display-specific plan metadata such as `courseTitle` for the merged history selector

This layer exists so plan selection and display mapping do not leak into the page component.

### Copy And Telemetry

Files:

- `apps/web/lib/learning-workspace-copy.ts`
- `apps/web/lib/learning-workspace-telemetry.ts`

Responsibilities:

- centralize repeated notice/copy strings
- centralize workflow log formatting

Do not scatter workflow notice strings or telemetry prefixes back into the page/component layer.

## Component Inputs

The `/plan` page currently renders these blocks:

- `PersonaSelector`
- `DocumentSetup`
- `PlanOverview`

The `/study` page currently renders these blocks:

- `PersonaSelector`
- `StudyConsole`
- `CharacterShell`
- embedded PDF pane

Current `/study` interaction details:

- theme selector routes to a concrete section id before sending chat
- quick action allows jumping PDF preview to the current theme start page
- transcript displays latest turns first (reverse chronological)
- on chat failure, UI shows explicit error text and a manual retry button

Each block should receive already-prepared data via props.

Examples:

- `PlanOverview` receives `items`, `selectedPlanId`, `plan`, `documentTitle`, and actions such as `onSelectPlan`
- `StudyConsole` receives the active section list, current response, and handlers for asking/switching/opening textbook pages

Chapter switching rules:

- The chapter source is the active plan directory (`plan.schedule.unitId` mapped to document study units).
- If schedule-derived units are empty, fallback is document sections.
- Switching chapter re-enters or creates a section-scoped session for the active plan, then clears stale response.

For `Plan Overview`, keep these display rules stable:

- `courseTitle` is the main heading
- `objective` is supporting goal text, not the heading
- `weeklyFocus` and `todayTasks` are sequential content and should render as vertical reading flow, not same-row card grids
- `schedule` remains part of the plan payload but is not currently rendered in `Plan Overview`

## Design Rule

When adding new behavior to the `Learning Workspace`, place it by answering this question first:

- Is it rendering? Put it in the component.
- Is it async orchestration? Put it in the controller hook.
- Is it a state transition? Put it in the reducer.
- Is it pure derivation or normalization? Put it in `lib` utility state helpers.
- Is it repeated wording or workflow logging? Put it in copy/telemetry helpers.

If a change would require updating multiple layers, keep each layer limited to its own responsibility instead of shortcutting everything into the hook or page component.
