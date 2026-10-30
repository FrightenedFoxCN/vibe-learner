# AI Service

FastAPI backend for Document/OCR, Planning, Study Chat, Persona/Scene, Tavern and
Harness evidence. The Web frontend uses a global Debug Overlay.

## Development

From this directory:

```bash
uv sync --frozen
uv run uvicorn app.main:app --reload
```

Database migrations and legacy JSON import:

```bash
uv run alembic upgrade head
uv run python -m app.persistence.migrate_local_data
```

Copy `.env.example` to `.env` for startup defaults. `VIBE_LEARNER_PLAN_PROVIDER=mock`
keeps local runs deterministic; `litellm` enables the configured model provider.
Saved runtime settings in the database override environment defaults.
SQLite is the default database; `DATABASE_URL` can select PostgreSQL.

Configuration and budgets: [Harness configuration](../../docs/harness/configuration.md).
Storage ownership: [Architecture](../../docs/architecture.md).
HTTP contracts: [API reference](../../docs/api-reference.md).
Focused test commands: [Backend test boundaries](../../docs/backend-test-boundaries.md).

## Chat payload troubleshooting

A reasoning-heavy model can return `finish_reason=length` with little visible
content and cause `chat_model_invalid_payload`. Check the effective output-token
and timeout budgets, strict JSON support and LiteLLM response compatibility.
Embedding failures fall back to local hashed-vector retrieval.
