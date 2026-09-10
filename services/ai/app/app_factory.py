from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import Callable

from pathlib import Path

from app.core.diagnostics import DiagnosticStore
from app.api.diagnostic_middleware import DiagnosticMiddleware

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.tavern_routes import router as tavern_router
from app.core.logging import configure_logging
from app.core.settings import Settings
from app.core.bootstrap import Container


def create_app(*, settings: Settings | None = None, container_factory: Callable[[Settings], Container] = Container) -> FastAPI:
    configure_logging()
    settings = settings if settings is not None else Settings.from_env()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        diagnostics = DiagnosticStore(Path(settings.storage_root) / "diagnostics" / "events.sqlite3")
        app.state.diagnostics = diagnostics
        diagnostics.start()
        diagnostics.emit("lifecycle_started")
        container = None
        try:
            container = container_factory(settings)
            container.start()
            app.state.container = container
            yield
        finally:
            app.state.container = None
            if container is not None:
                container.close()
            diagnostics.emit("lifecycle_stopped")
            diagnostics.close()

    app = FastAPI(title="Vibe Learner AI Service", version="0.3.1", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
        expose_headers=["X-Request-ID"],
    )

    app.add_middleware(DiagnosticMiddleware)

    app.include_router(router)
    app.include_router(tavern_router)
    return app
