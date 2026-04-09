from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

from app.models.domain import DocumentRecord, DocumentSection
from app.services.local_store import LocalJsonStore


class DocumentService:
    def __init__(self, store: LocalJsonStore) -> None:
        self.store = store

    def create_document(self, file: UploadFile) -> DocumentRecord:
        document_id = f"doc-{uuid4().hex[:10]}"
        suffix = Path(file.filename or "document.pdf").suffix or ".pdf"
        stored_name = f"{document_id}{suffix}"
        stored_path = self.store.upload_root / stored_name
        contents = file.file.read()
        stored_path.write_bytes(contents)

        document = DocumentRecord(
            id=document_id,
            title=Path(file.filename or stored_name).stem,
            original_filename=file.filename or stored_name,
            stored_path=str(stored_path),
            status="uploaded",
            ocr_status="pending",
            created_at=_now(),
            updated_at=_now(),
            sections=[],
        )
        documents = self._load_documents()
        documents.append(document)
        self._save_documents(documents)
        return document

    def process_document(self, document_id: str) -> DocumentRecord:
        documents = self._load_documents()
        document = self.require_document(document_id, documents)
        sections = _build_sections(document)
        document.status = "processed"
        document.ocr_status = "completed"
        document.updated_at = _now()
        document.sections = sections
        self._save_documents(documents)
        return document

    def list_documents(self) -> list[DocumentRecord]:
        return self._load_documents()

    def require_document(
        self, document_id: str, documents: list[DocumentRecord] | None = None
    ) -> DocumentRecord:
        if documents is None:
            documents = self._load_documents()
        for document in documents:
            if document.id == document_id:
                return document
        raise HTTPException(status_code=404, detail="document_not_found")

    def _load_documents(self) -> list[DocumentRecord]:
        return self.store.load_list("documents", DocumentRecord)

    def _save_documents(self, documents: list[DocumentRecord]) -> None:
        self.store.save_list("documents", documents)


def _build_sections(document: DocumentRecord) -> list[DocumentSection]:
    base = document.title.replace("-", " ").replace("_", " ").strip() or "教材"
    return [
        DocumentSection(
            id=f"{document.id}:intro",
            document_id=document.id,
            title=f"{base} 导论",
            page_start=1,
            page_end=6,
            level=1,
        ),
        DocumentSection(
            id=f"{document.id}:core",
            document_id=document.id,
            title=f"{base} 核心概念",
            page_start=7,
            page_end=18,
            level=1,
        ),
        DocumentSection(
            id=f"{document.id}:practice",
            document_id=document.id,
            title=f"{base} 例题与练习",
            page_start=19,
            page_end=28,
            level=1,
        ),
    ]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
