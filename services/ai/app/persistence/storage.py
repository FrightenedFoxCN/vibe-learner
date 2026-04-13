from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DirectoryStats:
    path: str
    exists: bool
    file_count: int
    total_bytes: int


class StorageManager:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.upload_root = root / "uploads"
        self.cache_root = root / "cache"
        self.chat_attachment_root = root / "chat_attachments"
        self.runtime_temp_root = root / "_tmp"
        for path in (
            self.root,
            self.upload_root,
            self.cache_root,
            self.chat_attachment_root,
            self.runtime_temp_root,
        ):
            path.mkdir(parents=True, exist_ok=True)

    def ensure_runtime_temp_root(self) -> Path:
        self.runtime_temp_root.mkdir(parents=True, exist_ok=True)
        return self.runtime_temp_root

    def session_attachment_dir(self, session_id: str) -> Path:
        path = self.chat_attachment_root / session_id
        path.mkdir(parents=True, exist_ok=True)
        return path

    def describe_dir(self, path: Path) -> DirectoryStats:
        if not path.exists():
            return DirectoryStats(
                path=str(path),
                exists=False,
                file_count=0,
                total_bytes=0,
            )
        file_count = 0
        total_bytes = 0
        for child in path.rglob("*"):
            if child.is_file():
                file_count += 1
                total_bytes += child.stat().st_size
        return DirectoryStats(
            path=str(path),
            exists=True,
            file_count=file_count,
            total_bytes=total_bytes,
        )

    def clear_dir(self, path: Path) -> int:
        if not path.exists():
            return 0
        removed = 0
        for child in list(path.iterdir()):
            if child.is_dir():
                shutil.rmtree(child)
                removed += 1
            else:
                child.unlink()
                removed += 1
        path.mkdir(parents=True, exist_ok=True)
        return removed

    def delete_tree(self, path: Path) -> int:
        if not path.exists():
            return 0
        if path.is_file():
            path.unlink()
            return 1
        removed = sum(1 for _ in path.rglob("*"))
        shutil.rmtree(path)
        return removed
