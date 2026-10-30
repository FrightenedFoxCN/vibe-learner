"""Disposable DOC-USER-001 backend; no .env, user data, or remote providers.

From services/ai:
PYTHONPATH=. LITELLM_LOCAL_MODEL_COST_MAP=True UV_CACHE_DIR=/tmp/vibe-learner-uv-cache \
  uv run --frozen python tests/acceptance/manual_acceptance_server.py
"""

from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock

import fitz
import uvicorn
from fastapi import Response

from app.app_factory import create_app
from app.core.bootstrap import Container
from app.core.settings import Settings
from app.services.model_provider import MockModelProvider


class MockOnlyContainer(Container):
    def _build_model_provider(self, settings: Settings):
        if settings.plan_provider != "mock" or settings.has_any_runtime_api_key():
            raise RuntimeError("manual_acceptance_requires_mock_without_secrets")
        return MockModelProvider()


def manual_app(root: Path):
    calls: list[dict[str, str]] = []
    lock = Lock()

    def container_factory(settings):
        container = MockOnlyContainer(settings)
        original = container.pedagogy_orchestrator.generate_chat_reply

        def observed(**kwargs):
            with lock:
                calls.append(
                    {
                        "message": kwargs["message"],
                        "kind": str(kwargs.get("message_kind", "learner")),
                    }
                )
            return original(**kwargs)

        container.pedagogy_orchestrator.generate_chat_reply = observed
        return container

    settings = Settings(
        database_url=f"sqlite:///{root / 'runtime.db'}",
        storage_root=str(root / "data"),
        auto_migrate_local_data=False,
        allowed_origins=("http://127.0.0.1:13417",),
        plan_provider="mock",
        openai_base_url="http://127.0.0.1:1/disabled",
        ocr_engine="disabled",
    )
    app = create_app(settings=settings, container_factory=container_factory)

    @app.get("/__acceptance__/evidence")
    def evidence():
        with lock:
            return {
                "storage_root": settings.storage_root,
                "database_url": settings.database_url,
                "auto_migrate_local_data": settings.auto_migrate_local_data,
                "allowed_origins": settings.allowed_origins,
                "provider_guard": "mock_without_secrets_only",
                "study_calls": list(calls),
            }

    @app.get("/__acceptance__/textbook.pdf")
    def textbook():
        with fitz.open() as document:
            for title, body in [
                (
                    "Chapter 1: Python loops",
                    "A for loop visits every item in a sequence. Use range(3) to visit 0, 1, 2.",
                ),
                (
                    "Chapter 2: Conditions",
                    "A while loop repeats while its condition is true. Update the counter to terminate.",
                ),
                (
                    "Chapter 3: Practice",
                    "Compare for and while. Trace a counter, explain the stopping condition, and test an empty sequence.",
                ),
            ]:
                page = document.new_page()
                page.insert_textbox(
                    fitz.Rect(40, 40, 550, 790),
                    title + "\n\n" + "\n\n".join([body] * 8),
                    fontsize=12,
                )
            return Response(document.tobytes(), media_type="application/pdf")

    return app


if __name__ == "__main__":
    with TemporaryDirectory(prefix="vibe-manual-acceptance-") as folder:
        uvicorn.run(manual_app(Path(folder)), host="127.0.0.1", port=18996)
