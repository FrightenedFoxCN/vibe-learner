"""New application process for PG HTTP read-back; every model call is forbidden."""

from __future__ import annotations

import argparse
from pathlib import Path

from sqlalchemy import text
import uvicorn

from app.app_factory import create_app
from app.core.bootstrap import Container
from app.core.settings import Settings
from app.services.model_provider import MockModelProvider
from tests.support.process_database import process_database_url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--fd", type=int, required=True)
    args = parser.parse_args()
    calls = []

    class ReadBackOnly(MockModelProvider):
        def forbidden(self, *args, **kwargs):
            calls.append("unexpected model call")
            raise AssertionError("read-back attempted model execution")

        generate_chat = forbidden
        generate_learning_plan = forbidden
        generate_tavern_actor_reply = forbidden

    def factory(settings):
        container = Container(settings)
        provider = ReadBackOnly()
        container.model_provider = provider
        container.plan_service.model_provider = provider
        container.pedagogy_orchestrator.model_provider = provider
        container.tavern_service.model_provider = provider
        return container

    app = create_app(
        settings=Settings(
            database_url=process_database_url(args.root),
            storage_root=str(args.root),
            auto_migrate_local_data=False,
            plan_provider="mock",
            ocr_engine="disabled",
        ),
        container_factory=factory,
    )

    @app.get("/__acceptance__/identity")
    def identity():
        database = app.state.container.database
        with database.engine.connect() as connection:
            return {
                "dialect": database.engine.dialect.name,
                "schema": connection.execute(
                    text("SELECT current_schema()")
                ).scalar_one(),
                "provider_calls": list(calls),
            }

    uvicorn.run(app, fd=args.fd)
