# Documentation Index

## Current Docs

- `user_manual.md`: end-user product manual with page-by-page and block-by-block usage instructions
- `architecture.md`: current monorepo boundaries, runtime flow, and storage model
- `api-reference.md`: HTTP and streaming API reference, including debug endpoints
- `desktop-roadmap.md`: active desktop implementation roadmap for Tauri packaging, OnnxTR OCR, and master-password vault storage
- `desktop-packaging.md`: concrete desktop preview packaging commands, artifact paths, sidecar bundling, and CI workflow notes
- `desktop-startup-hotspots-v1.md`: packaged macOS cold-start evidence, hotspot analysis, and follow-up boundary
- `parsing-and-planning-data-flow.md`: end-to-end backend data chain for textbook parsing, study-unit cleanup, planning context, and plan trace persistence
- `study-chapter-and-schedule.md`: canonical terminology and runtime data chain for study units, chapter labels, schedule items, and session scope
- `plan-text-contract.md`: canonical meaning of learning-plan learner-facing text fields
- `learning-plan-prompt-contract.md`: exact learning-plan prompt sections, user payload shape, schema injection, and model transport string
- `frontend-learning-workspace.md`: frontend responsibility split for `/plan` and `/study` workspace pages
- `scene-setup.md`: layered scene editor guide for `/scene-setup`
- `tavern-architecture.md`: Tavern schema, transaction invariants, harness ownership, and performance boundaries
- `harness-engineering.md`: repository-wide validate/repair/commit lifecycle, shared trace schema, adoption matrix, and release metrics
- `harness-schema-ownership.md`: cross-workflow input/proposal/committed/API ownership registry and v1/v2/v3 evidence compatibility
- `acceptance-wave45-2026-09-10/recovery-limits/README.md`: process-crash recovery, maximum-input boundaries and HTTP restart evidence
- `harness-stage-evals.md`: ten deterministic stage regression suites, commands, gates, and evidence limits
- `harness-roadmap.md`: canonical unfinished Harness backlog, dependency graph, delivery waves, eval program, and production adoption gates
- `audit-2026-09-06-remediation.md`: implementation fixes and validation record for the 2026-09-06 audit
- `audit-2026-09-08-review.md`: follow-up review and residual failure evidence
- `audit-2026-09-08-remediation.md`: fixes and regression results for the follow-up review
- `performance-budgets-v1.md`: versioned fixture, query/payload, server P95, and React render gates for focused performance work
- `harness-performance-budgets-v1.md`: Wave 5 runtime limits, local performance fixtures and raw samples, serial Planning decision, and pending joint acceptance

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
11. Read `harness-roadmap.md` before claiming or scheduling Harness foundation, eval, migration, or production-adoption work.
12. Read `tavern-architecture.md` before changing Tavern persistence or orchestration.
13. Read `performance-budgets-v1.md` before changing a registered performance-critical query or UI list.
14. Read `desktop-roadmap.md` before changing desktop packaging, OCR replacement, or secure secret storage.
15. Read `../AGENTS.md` for repo entry points, commands, and local workflow notes.
16. Read `../TODO.md` for the active non-Harness implementation backlog and independent closure gates.

## Scope

These docs describe the repository as it exists now, not the aspirational long-term platform. When implementation changes, update the docs in the same change if the API, runtime flow, or data layout moved.

## Current implementation notes (2026-09-03)

- Debug is a global overlay; the old standalone `/debug` route no longer exists.
- Structured persistence defaults to local SQLite and can use PostgreSQL through `DATABASE_URL`; uploads, attachments, cache, and compatibility debug files remain local.
- `/tavern` is active in both frontend and backend. It supports durable 1–6 persona rooms, direct and facilitated turns, append-only transcript paging, partial failure, scoped child retry, resume, and cancel fencing.
- Domain-owned strict decoders now cover Tavern, Document, Planning, Persona/Scene, Study, and versioned Document/Planning streams. Independent live-wire closure, remaining endpoint inventory, Frontend Decoder component registration, and v2/v3 trace forwarding/resource evidence remain open; decoder coverage alone does not complete repository-wide Harness adoption.
- Harness Engineering is repository-wide. Tavern actor generation and Study Chat now call the shared v3 context/runtime boundary with authorized protected snapshots, terminal traces, committed primary-output projections, and deterministic eval suites. Historical v1/v2 evidence remains readable without being upgraded.
- Snapshot digests are integrity references only. Protected replay uses the authorized artifact resolver, resource evidence policies, retention, and read-back verification; production workflow adoption remains tracked in `harness-roadmap.md`.
- Study Chat now has independently revalidated production v3 execution across durable admission/read-back, protected replay, transactional Session/Scene effects, operation-owned attachment staging, the shared durable effect journal, and explicit provider uncertainty. Its commit evidence proves the Session/Turn primary output; independent live-wire samples remain optional frontend coverage.
- Interactive questions now use private server-owned grading, a narrow idempotent Attempt journal, and persisted Session read-back; the two schema tickets remain open only for required independent revalidation.
- Document processing uses a durable operation journal and commits Document/Debug projections atomically with digest read-back and startup recovery. Planning likewise admits stable operations and atomically commits Document/Debug/Planning Trace/Learning Plan projections plus a versioned terminal snapshot; both still require their separate v3 trace/replay/eval adoption work.
