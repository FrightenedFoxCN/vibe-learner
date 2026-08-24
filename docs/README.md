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
- `tavern-architecture.md`: Tavern schema, transaction invariants, harness ownership, and performance boundaries
- `harness-engineering.md`: repository-wide validate/repair/commit lifecycle, shared trace schema, adoption matrix, and release metrics
- `harness-schema-ownership.md`: cross-workflow input/proposal/committed/API ownership registry and v1/v2/v3 evidence compatibility
- `independent-product-audit-2026-08-12.md`: evidence-backed independent UX/reliability audit, reproductions, priorities, and acceptance gates
- `performance-budgets-v1.md`: versioned fixture, query/payload, server P95, and React render gates for focused performance work
- `handoff-2026-08-13.md`: current stop point, verified commits, unresolved risks, Git state, and ordered instructions for the next agent

## Reading Order

1. Read `user_manual.md` to understand the current page-level product behavior and operation flow.
2. Read `architecture.md` for the high-level system split.
3. Read `study-chapter-and-schedule.md` before discussing study-unit, chapter-label, schedule, or session-scope changes.
4. Read `parsing-and-planning-data-flow.md` before changing PDF parsing, study-unit cleanup, planning context, or tool-enabled plan generation.
5. Read `frontend-learning-workspace.md` before changing `apps/web/components/learning-workspace.tsx` or its controller/state helpers.
6. Read `plan-text-contract.md` before changing learning-plan text fields or UI copy mapping.
7. Read `learning-plan-prompt-contract.md` before changing plan prompt assembly, schema injection, or model payload serialization.
8. Read `api-reference.md` before touching frontend/backend contracts.
9. Read `harness-engineering.md` before adding or changing reliability, recovery, trace, or evaluation boundaries in any workflow.
10. Read `harness-schema-ownership.md` before changing model-output, persisted-record, effect, or API schema ownership.
11. Read `tavern-architecture.md` before changing Tavern persistence or orchestration.
12. Read `independent-product-audit-2026-08-12.md` before closing UX, reliability, recovery, or cross-workflow adoption items.
13. Read `performance-budgets-v1.md` before changing a registered performance-critical query or UI list.
14. Read `desktop-roadmap.md` before changing desktop packaging, OCR replacement, or secure secret storage.
15. Read `desktop-distribution-plan.md` for the original architecture exploration context.
16. Read `../AGENTS.md` for repo entry points, commands, and local workflow notes.
17. Read `../TODO.md` for the active implementation backlog.

## Scope

These docs describe the repository as it exists now, not the aspirational long-term platform. When implementation changes, update the docs in the same change if the API, runtime flow, or data layout moved.

## Current implementation notes (2026-08-13)

- Debug is a global overlay; the old standalone `/debug` route no longer exists.
- Structured persistence defaults to local SQLite and can use PostgreSQL through `DATABASE_URL`; uploads, attachments, cache, and compatibility debug files remain local.
- `/tavern` is active in both frontend and backend. It supports durable 1–6 persona rooms, direct and facilitated turns, append-only transcript paging, partial failure, scoped child retry, resume, and cancel fencing.
- The Tavern browser boundary strictly decodes the current legacy-v1 wire and fences stale room/operation results. This does not complete `HRN-WEB-001` for Document, Plan, Persona, Scene, or Study responses.
- Harness Engineering is repository-wide. V2/v3 contracts and the v3 context builder are schema foundations; no production workflow currently calls `build_harness_context`, and Tavern production evidence remains legacy v1 until `HRN-TAV-V3-001` is complete.
- Snapshot digests are integrity references only. Protected replay needs the authorized artifact resolver, resource evidence policies, retention, and read-back verification tracked in `TODO.md`.
- Study Chat now has Session CAS, durable request admission/read-back, strict browser operation recovery, a mixed transactional database-effect batch, operation-owned attachment staging, and explicit provider uncertainty. Full v3 protected replay/eval and independent closure gates remain open.
- Interactive questions now use private server-owned grading, a narrow idempotent Attempt journal, and persisted Session read-back; the two schema tickets remain open only for required independent revalidation.
- Document processing uses a durable operation journal and commits Document/Debug projections atomically with digest read-back and startup recovery. Planning still retains a multi-aggregate boundary that requires staged or transactional migration.
