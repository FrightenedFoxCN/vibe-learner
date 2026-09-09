"""Application-instance dependencies; importing routes never starts services."""
from fastapi import Request

from app.core.bootstrap import Container


def get_container(request: Request) -> Container:
    container = getattr(request.app.state, "container", None)
    if container is None:
        raise RuntimeError("application_lifespan_not_started")
    return container
