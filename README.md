# Vibe Learner

Monorepo for a local-first, persona-aware learning assistant.

Current surfaces:

- `apps/web`: Next.js learning workspace with persona-aware character shell
- `services/ai`: FastAPI service for pedagogy orchestration and character event generation
- `packages/shared`: shared TypeScript contracts for learning, persona, and performance events

## Documentation

- [Docs Index](docs/README.md)
- [Architecture](docs/architecture.md)
- [API Reference](docs/api-reference.md)
- [Agent Notes](AGENTS.md)
- [Project TODO](TODO.md)

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

The frontend defaults to `http://127.0.0.1:8000` for the AI service unless `NEXT_PUBLIC_AI_BASE_URL` is set.

## Plan LLM

Learning-plan generation can use either a local mock planner or a real OpenAI call.

```bash
cd services/ai
cp .env.example .env
```

Set these env vars in `services/ai/.env` when you want the plan endpoint to call a real model:

```bash
VIBE_LEARNER_PLAN_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_PLAN_MODEL=gpt-4.1-mini
OPENAI_CHAT_MODEL=gpt-4.1-mini
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_TIMEOUT_SECONDS=30
```

If `VIBE_LEARNER_PLAN_PROVIDER` stays `mock`, the service will keep using the built-in deterministic planner.

## Test

```bash
npm run test:ai
npm run build:web
```
