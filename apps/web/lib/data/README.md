# Data Lib Map

Each domain structure now has one frontend entrypoint under `apps/web/lib/data/`.

- `personas.ts`
  Used by: `app/persona-spectrum/page.tsx`, persona-related UI flows.
  Owns: persona profile CRUD, persona assist APIs, persona asset fetch.
- `persona-cards.ts`
  Used by: `app/persona-spectrum/page.tsx`.
  Owns: persona card CRUD and generation.
- `documents.ts`
  Used by: `hooks/use-learning-workspace-controller.ts`, `hooks/use-document-debug-data.ts`.
  Owns: document CRUD, processing, debug/context/trace reads, process event reads, study-unit title update.
- `learning-plans.ts`
  Used by: `hooks/use-learning-workspace-controller.ts`.
  Owns: learning-plan CRUD, stream creation, progress updates, planning-question answer.
- `study-sessions.ts`
  Used by: `hooks/use-learning-workspace-controller.ts`.
  Owns: study-session CRUD, chat, question attempt, plan confirmation resolution.
- `scenes.ts`
  Used by: `app/scene-setup/page.tsx`, `components/document-setup.tsx`, `hooks/use-learning-workspace-controller.ts`.
  Owns: scene setup state, saved scene library CRUD, reusable scene node CRUD, scene generation.
- `runtime-settings.ts`
  Used by: `components/runtime-settings-provider.tsx`, `components/settings/use-settings-controller.ts`.
  Owns: runtime settings read/update and model probe.
- `model-tools.ts`
  Used by: `app/sensory-tools/page.tsx`, `hooks/use-document-debug-data.ts`.
  Owns: model-tool config read/update.
- `model-usage.ts`
  Used by: `app/model-usage/page.tsx`.
  Owns: model usage stats read.

`apps/web/lib/api.ts` remains as a compatibility aggregator for transport and normalization internals. New page-level imports should prefer `lib/data/*`.

## Page Consumption Map

This map is based on actual page runtime dependencies, not only direct imports.

- `/`
  Uses no backend CRUD directly.
  Only links into other product pages.
- `/plan`
  Renders `LearningWorkspace`, which consumes:
  `documents.ts`, `learning-plans.ts`, `study-sessions.ts`, `personas.ts`, `scenes.ts`
  The page needs persona and scene data because plan generation, plan history labeling, session creation, and scene selection all depend on them.
- `/study`
  Renders `StudyDialogPage`, which consumes `LearningWorkspace` state and therefore also depends on:
  `documents.ts`, `learning-plans.ts`, `study-sessions.ts`, `personas.ts`, `scenes.ts`
  The page also opens document / attachment previews using IDs produced by those records.
- `/persona-spectrum`
  Consumes:
  `personas.ts`, `persona-cards.ts`
- `/scene-setup`
  Consumes:
  `scenes.ts`, `personas.ts`
  Scene text rewrite uses persona assist APIs even though the page is scene-focused.
- `/settings`
  Consumes:
  `runtime-settings.ts`
  The page reads current runtime settings through `RuntimeSettingsProvider` and updates/probes through `use-settings-controller.ts`.
- `/sensory-tools`
  Consumes:
  `model-tools.ts`
- `/model-usage`
  Consumes:
  `model-usage.ts`

## Shared Runtime Consumers

- `hooks/use-learning-workspace-controller.ts`
  This is the main cross-page orchestration hub for `/plan` and `/study`.
  It is the authoritative consumer of:
  `documents.ts`, `learning-plans.ts`, `study-sessions.ts`, `personas.ts`, `scenes.ts`
- `hooks/use-document-debug-data.ts`
  Consumes:
  `documents.ts`, `model-tools.ts`
- `components/runtime-settings-provider.tsx`
  Consumes:
  `runtime-settings.ts`
- `components/debug-overlay.tsx`
  Indirectly depends on `use-document-debug-data.ts` and `RuntimeSettingsProvider`.

## Boundary Rule

When a page needs a data structure, import from that structure's module even if the request is made indirectly by a shared controller.

Examples:

- If `/study` needs persona or scene-backed behavior, that still belongs to `personas.ts` / `scenes.ts`, even when the fetch is currently centralized inside `use-learning-workspace-controller.ts`.
- Do not create page-specific copies such as `plan-api.ts` or `study-api.ts` for records that already have a structure-level home.
