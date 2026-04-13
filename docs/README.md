# Documentation Index

## Current Docs

- `user_manual.md`: end-user product manual with page-by-page and block-by-block usage instructions
- `architecture.md`: current monorepo boundaries, runtime flow, and storage model
- `api-reference.md`: HTTP and streaming API reference, including debug endpoints
- `desktop-roadmap.md`: active desktop implementation roadmap for Tauri packaging, OnnxTR OCR, and master-password vault storage
- `desktop-packaging.md`: concrete desktop preview packaging commands, artifact paths, sidecar bundling, and CI workflow notes
- `desktop-distribution-plan.md`: deferred plan for future cross-platform desktop packaging and app-shell architecture
- `parsing-and-planning-data-flow.md`: end-to-end backend data chain for textbook parsing, study-unit cleanup, planning context, and plan trace persistence
- `study-chapter-and-schedule.md`: canonical terminology and runtime data chain for study units, chapter labels, schedule items, and session scope
- `plan-text-contract.md`: canonical meaning of learning-plan learner-facing text fields
- `learning-plan-prompt-contract.md`: exact learning-plan prompt sections, user payload shape, schema injection, and model transport string
- `frontend-learning-workspace.md`: frontend responsibility split for `/plan` and `/study` workspace pages
- `persona-spectrum.md`: Persona Spectrum page data chain and API contract
- `scene-setup.md`: layered scene editor guide for `/scene-setup`

## Reading Order

1. Read `user_manual.md` to understand the current page-level product behavior and operation flow.
2. Read `architecture.md` for the high-level system split.
3. Read `study-chapter-and-schedule.md` before discussing study-unit, chapter-label, schedule, or session-scope changes.
4. Read `parsing-and-planning-data-flow.md` before changing PDF parsing, study-unit cleanup, planning context, or tool-enabled plan generation.
5. Read `frontend-learning-workspace.md` before changing `apps/web/components/learning-workspace.tsx` or its controller/state helpers.
6. Read `plan-text-contract.md` before changing learning-plan text fields or UI copy mapping.
7. Read `learning-plan-prompt-contract.md` before changing plan prompt assembly, schema injection, or model payload serialization.
8. Read `api-reference.md` before touching frontend/backend contracts.
9. Read `desktop-roadmap.md` before changing desktop packaging, OCR replacement, or secure secret storage.
10. Read `desktop-distribution-plan.md` for the original architecture exploration context.
11. Read `../AGENTS.md` for repo entry points, commands, and local workflow notes.
12. Read `../TODO.md` for the active implementation backlog.

## Scope

These docs describe the repository as it exists now, not the aspirational long-term platform. When implementation changes, update the docs in the same change if the API, runtime flow, or data layout moved.

## Recent Sync Notes (2026-04-10)

- Study chat now uses per-section session routing and historical session re-entry in the frontend controller.
- Study transcript is rendered in reverse chronological order (latest first).
- Chat failures now surface as explicit UI errors with manual retry action instead of silent fallback assistant text.
- Study chat model now supports page-range text/image reading tools and has dedicated chat tool config variables.
- OpenAI-compatible provider truncation mitigation is documented via `OPENAI_CHAT_MAX_TOKENS` tuning.
- Scene Setup and Scene Library contracts are documented in `scene-setup.md` and summarized in `api-reference.md`.
- Scene-related 422 triage now centers on empty `scene_name` / `scene_summary` and missing required `scene_layers[].scope_label`.
- `/plan` and `/study` now preserve page-local draft state across route changes, with serializable state restored from `sessionStorage` after same-tab refresh.
- OpenAI-compatible model calls now retry transient transport failures inside `OpenAIModelProvider`, while keeping final public error categories stable and exposing retry count in plan stream errors.
- Successful model recoveries are now carried as debug-only data (`model_recoveries` / plan trace recoveries) for plan, chat, persona, and scene generation flows; ordinary page UI still only surfaces unrecovered failures.
