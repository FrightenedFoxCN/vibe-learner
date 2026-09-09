"""Isolated database fixture shared by persistence contract tests.

Set VIBE_TEST_POSTGRES_URL to opt into a disposable PostgreSQL test database.
Each test gets a fresh schema; the supplied database is never dropped.
"""
from pathlib import Path
from tempfile import TemporaryDirectory
import os
from uuid import uuid4

from sqlalchemy.schema import CreateSchema, DropSchema

from app.persistence.database import Database


def isolated_database(test_case) -> Database:
    url = os.environ.get("VIBE_TEST_POSTGRES_URL")
    if not url:
        directory = TemporaryDirectory()
        test_case.addCleanup(directory.cleanup)
        database = Database(f"sqlite:///{Path(directory.name) / 'test.db'}")
        test_case.addCleanup(database.dispose)
    else:
        if not url.startswith("postgresql"):
            raise ValueError("VIBE_TEST_POSTGRES_URL must use PostgreSQL")
        database = Database(url)
        test_case.addCleanup(database.dispose)
        schema = f"architecture_test_{uuid4().hex}"
        with database.engine.begin() as connection:
            connection.execute(CreateSchema(schema))
        def drop_schema():
            with database.engine.begin() as connection:
                connection.execute(DropSchema(schema, cascade=True))
        test_case.addCleanup(drop_schema)
        database.engine = database.engine.execution_options(schema_translate_map={None: schema})
        database._session_factory.configure(bind=database.engine)
    database.create_schema()
    return database
