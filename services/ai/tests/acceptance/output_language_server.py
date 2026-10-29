"""Disposable real mock backend for the output-language browser acceptance."""

from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

from app.app_factory import create_app
from app.core.settings import Settings


if __name__ == "__main__":
    with TemporaryDirectory(prefix="vibe-output-language-") as folder:
        root = Path(folder)
        settings = Settings(
            database_url=f"sqlite:///{root / 'runtime.db'}",
            storage_root=str(root / "data"),
            allowed_origins=("http://127.0.0.1:3433",),
            auto_migrate_local_data=False,
            plan_provider="mock",
            ocr_engine="disabled",
        )
        uvicorn.run(create_app(settings=settings), host="127.0.0.1", port=18443)
