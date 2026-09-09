"""Route-level test fixtures. Lifecycle behavior has its own test module."""
from functools import cached_property
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_container
from app.core.bootstrap import Container
from app.core.settings import Settings


class ContainerTestCase(unittest.TestCase):
    @cached_property
    def container(self) -> Container:
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        root = Path(directory.name)
        container = Container(Settings(
            database_url=f"sqlite:///{root / 'api.db'}",
            storage_root=str(root / "data"),
            ocr_engine="disabled",
        ))
        self.addCleanup(container.close)
        return container


def isolated_client(source_app: FastAPI, container) -> TestClient:
    """Copy the route table into a fresh app with one explicit dependency override.

    Route fault tests do not run startup recovery or use a runtime database.
    Production lifespan is tested separately through create_app + TestClient.
    """
    app = FastAPI()
    app.include_router(source_app.router)
    app.dependency_overrides[get_container] = lambda: container
    return TestClient(app)
