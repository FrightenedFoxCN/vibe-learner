from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

from app.persistence.models import Base


class Database:
    def __init__(self, url: str) -> None:
        engine_kwargs: dict[str, object] = {
            "future": True,
            "pool_pre_ping": True,
        }
        if url.startswith("sqlite"):
            engine_kwargs["connect_args"] = {"check_same_thread": False}
        self.url = url
        self.engine: Engine = create_engine(url, **engine_kwargs)
        self._session_factory = sessionmaker(
            bind=self.engine,
            autoflush=False,
            expire_on_commit=False,
            future=True,
        )

    def create_schema(self) -> None:
        Base.metadata.create_all(self.engine)

    def dispose(self) -> None:
        self.engine.dispose()

    @contextmanager
    def session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
