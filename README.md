# Gal Learner

Monorepo scaffold for an LLM-driven learning assistant with:

- `apps/web`: Next.js learning workspace with persona-aware character shell
- `services/ai`: FastAPI service for pedagogy orchestration and character event generation
- `packages/shared`: shared TypeScript contracts for learning, persona, and performance events

## Workspace

```bash
npm install
cd services/ai
uv sync
```

## Run

```bash
npm run dev:web
cd services/ai && uv run uvicorn app.main:app --reload
```

## Test

```bash
npm run test:ai
```
