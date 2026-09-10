# Frontend Workspace Boundary

This document defines the current frontend boundary for the split workspace pages in `apps/web`.

## Goal

The frontend is intentionally split so rendering, async workflows, state transitions, pure state rules, and UI copy do not collapse back into one page component.

When changing this area, preserve the separation below unless there is a clear architectural reason to move it.

## Page Split

- `/` = navigation home
- `/plan` = `Plan Workspace` (upload, process, generate, history)
- `/study` = `Study Dialog` (chat + PDF + chapter switching)
- `/persona-spectrum` = `Persona Spectrum` (persona slots, style tuning, import/export)
- `/scene-setup` = `Scene Setup` (world-to-classroom layered scene editing)

`/plan` and `/study` share one runtime state source through `LearningWorkspaceProvider`.

The learning provider lives in the `(learning)` route group. Settings, Model Usage,
Persona, Scene and Tavern do not initialize learning data. The global
`DebugProvider` receives a narrow read-only learning projection and clears it
when the learning owner leaves.

A lightweight root `LearningPageCacheProvider` preserves page-local drafts:

- in-memory files and text survive navigation out of Plan/Study;
- `sessionStorage` preserves serializable state across same-tab refresh;
- `File` objects remain memory-only and cannot be restored after hard refresh.

Leaving the learning route invalidates response tickets and stops local stream
reading. Known stream operations receive cancellation requests; ambiguous Study
Chat writes retain their original identity and recover by query on return.

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

The controller composes module owners and projects reducer state for pages. API
writes, recovery, timers and draft lifecycles have explicit independently tested
boundaries:

| Owner | Responsibility |
| --- | --- |
| `WorkspaceSnapshotLoader` | Initial/focus/manual learning snapshots and stale query suppression |
| `useWorkspaceLibraries` | Persona/Scene refresh identity, selection and event subscriptions |
| `usePlanGeneration` | Upload, parse/plan streams, cancellation and initial Session |
| `usePlanMutations` | Plan/Study Unit writes, per-resource admission and feedback |
| `useStudySessionNavigation` | Session history, creation and serialized chapter switching |
| `useStudyMessages` | Learner/hidden messages, automatic request identity and admission failures |
| `useStudyChatRecovery` | Query-only restore/read-back, explicit retry eligibility and view tickets |
| `useStudyCommitActions` | Answer/confirmation committed projections and callback eligibility |
| `useStudyContinuation` | Prelude, scheduled follow-up, pause and deferred answer callbacks |
| `learning-workspace-model` | Pure directory, theme, Scene and configuration projections |

Each asynchronous owner accepts a narrow API/storage/clock port where needed.
A pending operation blocks new automatic generation during restore. Timers read
the current Session revision when firing; failed timers wait for an authoritative
Session refresh instead of re-polling on busy-state changes. Learner completion
consumes only deferred callbacks captured before its request, preserving answers
queued while it was in flight.

Persona Spectrum and Scene Setup similarly use route composition, domain-owned
library/draft/generation/rewrite/persistence hooks, and separate presentation
components. See [frontend test boundaries](frontend-test-boundaries.md) for the
independent module and production-browser commands.

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

The reducer-backed state is still the source of truth for documents, plans, sessions, and replies.

Study Chat POST, operation query, and rejected-admission refresh results also pass through `StudyAsyncViewFence`. Its ticket binds operation identity, current Plan/Session subject, a monotonic view revision, and the current Session/Study Unit field target. Switching Plan, Session, or Study Unit invalidates older tickets; a late result may be logged or its pending identity cleared, but it cannot overwrite the new view. Persona and Scene async generation/file reads use the same subject/draft-revision/field-target fencing primitive in their own pages.

Page-cache state is only for page-local UI continuity such as:

- `/plan` upload mode, objective draft, and selected-but-not-yet-submitted PDF file
- `/study` chapter/subsection selection, preview window position, and unsent chat draft

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
- transcript validates contiguous sequence and displays turns oldest-to-newest, scrolling to the latest committed Turn
- ambiguous chat outcomes show an explicit query action for the original operation and lock new sends; only explicit `not_committed + safe_to_retry` permits resend, while known pre-admission rejection requires a Session refresh first
- unsent composer text, question draft state, and preview/chapter position recover after route changes and same-tab refresh
- successful model-side recoveries are debug-only: they surface in `StudyDebugPanels`, persona/scene page debug snapshots, and plan trace/debug panels, but not in the main user-facing page blocks

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
- `todayTasks`, `schedule`, and nested `scheduleChapters` are sequential content and should render as vertical reading flow, not same-row card grids
- `schedule` is rendered in `Plan Overview`; nested chapters expand under their parent schedule item and retain their page anchors

## Design Rule

When adding new behavior to the `Learning Workspace`, place it by answering this question first:

- Is it rendering? Put it in the component.
- Is it async orchestration? Put it in the controller hook.
- Is it a state transition? Put it in the reducer.
- Is it pure derivation or normalization? Put it in `lib` utility state helpers.
- Is it repeated wording or workflow logging? Put it in copy/telemetry helpers.

If a change would require updating multiple layers, keep each layer limited to its own responsibility instead of shortcutting everything into the hook or page component.
