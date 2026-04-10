# AI Service

FastAPI service for:

- persona loading
- pedagogy orchestration
- character performance event mapping
- document parsing, OCR fallback, and study-unit cleanup
- learning-plan generation and plan trace persistence
- debug endpoints used by the web `/debug` page

Detailed HTTP contract docs live in `../../docs/api-reference.md`.

Run with:

```bash
uv sync
uv run uvicorn app.main:app --reload
```

Plan generation and chapter chat support real LLM calls when configured.

```bash
cp .env.example .env
```

Example:

```bash
GAL_LEARNER_PLAN_PROVIDER=openai
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_PLAN_MODEL=gpt-4.1-mini
OPENAI_CHAT_MODEL=gpt-4.1-mini
OPENAI_CHAT_TEMPERATURE=0.35
OPENAI_CHAT_MAX_TOKENS=800
OPENAI_CHAT_HISTORY_MESSAGES=8
OPENAI_CHAT_TOOL_MAX_ROUNDS=4
OPENAI_CHAT_TOOLS_ENABLED=true
OPENAI_CHAT_MODEL_MULTIMODAL=false
OPENAI_TIMEOUT_SECONDS=30
```

Without those vars, the service falls back to the mock planner.
