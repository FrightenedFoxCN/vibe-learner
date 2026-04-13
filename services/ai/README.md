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

Database migration:

```bash
alembic upgrade head
```

Legacy JSON data import:

```bash
uv run python -m app.persistence.migrate_local_data
```

Plan generation and chapter chat support real LLM calls when configured.

```bash
cp .env.example .env
```

Example:

```bash
DATABASE_URL=postgresql+psycopg://postgres:postgres@127.0.0.1:5432/vibe_learner
VIBE_LEARNER_PLAN_PROVIDER=litellm
OPENAI_API_KEY=sk-...
OPENAI_BASE_URL=http://127.0.0.1:4000
OPENAI_PLAN_MODEL=gpt-4.1-mini
OPENAI_SETTING_MODEL=gpt-4.1-mini
OPENAI_CHAT_MODEL=gpt-4.1-mini
OPENAI_CHAT_TEMPERATURE=0.35
OPENAI_SETTING_TEMPERATURE=0.4
OPENAI_SETTING_MAX_TOKENS=900
OPENAI_CHAT_MAX_TOKENS=800
OPENAI_CHAT_HISTORY_MESSAGES=8
OPENAI_CHAT_TOOL_MAX_ROUNDS=4
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
OPENAI_CHAT_MODEL_MULTIMODAL=false
OPENAI_TIMEOUT_SECONDS=30
```

Storage notes:

- primary structured data now lives in PostgreSQL through SQLAlchemy ORM
- uploaded PDFs remain on disk under `services/ai/data/uploads/`
- session attachment temp files live under `services/ai/data/chat_attachments/`
- OCR/runtime temp files live under `services/ai/data/_tmp/`
- debug traces and stream reports are now database-backed cache buckets and can be inspected/cleared through `/storage/summary` and `/storage/cleanup`

Without those vars, the service falls back to the mock planner.

The runtime now calls LiteLLM through the Python SDK. You can still point `OPENAI_*_BASE_URL` at LiteLLM Proxy, but you can also use provider-prefixed LiteLLM model names to reach other supported upstreams directly. The runtime settings model probe still expects an OpenAI-compatible `/models` response, so direct upstreams may require manual model names in the UI.

Persona setting assistant uses `OPENAI_SETTING_MODEL` when provider is `litellm`.

Memory retrieval notes:

- `OPENAI_EMBEDDING_MODEL` controls the embedding model used by cross-session memory retrieval.
- If embedding endpoint is unavailable, the backend will gracefully fall back to local hashed-vector retrieval.

## Chat Payload Troubleshooting

When using LiteLLM with some reasoning-heavy upstreams, the provider can return `finish_reason=length` with very short `message.content` while most tokens are consumed as reasoning tokens. In this case, the backend may raise `chat_model_invalid_payload`.

Recommended adjustment (priority 1):

- increase `OPENAI_CHAT_MAX_TOKENS` (for example from `800` to `1600` or `2400`) so the model has enough output budget for valid assistant content

Also verify:

- model capability for strict JSON output
- whether the current upstream can be normalized by LiteLLM into a valid chat-completions payload
- timeout budget (`OPENAI_TIMEOUT_SECONDS`) after increasing output tokens
