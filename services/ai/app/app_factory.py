from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import Callable

import time
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.api.tavern_routes import router as tavern_router
from app.core.logging import configure_logging, get_logger
from app.core.settings import Settings
from app.core.bootstrap import Container


def create_app(*, settings: Settings | None = None, container_factory: Callable[[Settings], Container] = Container) -> FastAPI:
    configure_logging()
    settings = settings if settings is not None else Settings.from_env()
    logger = get_logger("vibe_learner.api")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        container = container_factory(settings)
        try:
            container.start()
            app.state.container = container
            yield
        finally:
            app.state.container = None
            container.close()

    app = FastAPI(title="Vibe Learner AI Service", version="0.3.1", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.allowed_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def log_requests(request: Request, call_next):
        request_id = uuid4().hex[:8]
        started_at = time.perf_counter()
        logger.info(
            "request.start id=%s method=%s path=%s query=%s",
            request_id,
            request.method,
            request.url.path,
            request.url.query,
        )
        try:
            response = await call_next(request)
        except Exception:
            elapsed_ms = int((time.perf_counter() - started_at) * 1000)
            logger.exception(
                "request.error id=%s method=%s path=%s duration_ms=%s",
                request_id,
                request.method,
                request.url.path,
                elapsed_ms,
            )
            raise
        elapsed_ms = int((time.perf_counter() - started_at) * 1000)
        logger.info(
            "request.end id=%s method=%s path=%s status=%s duration_ms=%s",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            elapsed_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(router)
    app.include_router(tavern_router)
    return app
