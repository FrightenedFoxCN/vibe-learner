# Documentation Index

## Current Docs

- `architecture.md`: current monorepo boundaries, runtime flow, and storage model
- `api-reference.md`: HTTP and streaming API reference, including debug endpoints
- `parsing-and-planning-data-flow.md`: end-to-end backend data chain for textbook parsing, study-unit cleanup, planning context, and plan trace persistence
- `plan-text-contract.md`: canonical meaning of learning-plan learner-facing text fields
- `frontend-learning-workspace.md`: frontend responsibility split for the Learning Workspace page

## Reading Order

1. Read `architecture.md` for the high-level system split.
2. Read `parsing-and-planning-data-flow.md` before changing PDF parsing, study-unit cleanup, planning context, or tool-enabled plan generation.
3. Read `frontend-learning-workspace.md` before changing `apps/web/components/learning-workspace.tsx` or its controller/state helpers.
4. Read `plan-text-contract.md` before changing learning-plan text fields or UI copy mapping.
5. Read `api-reference.md` before touching frontend/backend contracts.
6. Read `../AGENTS.md` for repo entry points, commands, and local workflow notes.
7. Read `../TODO.md` for the active implementation backlog.

## Scope

These docs describe the repository as it exists now, not the aspirational long-term platform. When implementation changes, update the docs in the same change if the API, runtime flow, or data layout moved.
