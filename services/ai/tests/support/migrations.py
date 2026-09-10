"""Alembic configuration for an explicitly selected test database."""
from pathlib import Path
from alembic.config import Config
SERVICE_ROOT = Path(__file__).resolve().parents[2]

def alembic_config(database_url: str) -> Config:
    config = Config(str(SERVICE_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(SERVICE_ROOT / "alembic"))
    config.set_main_option("sqlalchemy.url", database_url)
    return config

