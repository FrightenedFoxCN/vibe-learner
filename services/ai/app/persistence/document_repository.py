from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.domain import DocumentDebugRecord, DocumentRecord
from app.persistence.database import Database
from app.persistence.models import DocumentDebugRow, DocumentRow


class DocumentNotFound(RuntimeError):
    pass


class DocumentRevisionConflict(RuntimeError):
    def __init__(self, document_id: str, expected: int, actual: int | None) -> None:
        super().__init__(f"document_revision_conflict:{document_id}:{expected}:{actual}")


class DocumentProcessingConflict(RuntimeError):
    pass


class StudyUnitNotFound(RuntimeError):
    pass


class DocumentLegacyImportConflict(RuntimeError):
    pass


class DocumentRepository:
    """Single-record writes; Document revision also fences its Debug projection."""

    def __init__(self, database: Database) -> None:
        self.database = database

    def insert(self, document: DocumentRecord) -> None:
        with self.database.session() as session:
            session.add(DocumentRow(**_document_values(document)))
            session.flush()

    def get(self, document_id: str) -> DocumentRecord | None:
        with self.database.session() as session:
            row = session.get(DocumentRow, document_id)
            return document_from_row(row) if row is not None else None

    def list(self) -> list[DocumentRecord]:
        with self.database.session() as session:
            rows = session.scalars(
                select(DocumentRow).order_by(DocumentRow.created_at, DocumentRow.id)
            ).all()
            return [document_from_row(row) for row in rows]

    def get_with_debug(self, document_id: str) -> tuple[DocumentRecord, DocumentDebugRecord | None] | None:
        with self.database.session() as session:
            pair = session.execute(
                select(DocumentRow, DocumentDebugRow)
                .outerjoin(DocumentDebugRow, DocumentDebugRow.document_id == DocumentRow.id)
                .where(DocumentRow.id == document_id)
            ).one_or_none()
            if pair is None:
                return None
            document_row, debug_row = pair
            return (
                document_from_row(document_row),
                DocumentDebugRecord.model_validate(debug_row.payload) if debug_row is not None else None,
            )

    def import_legacy(self, documents: list[DocumentRecord]) -> None:
        unique: dict[str, DocumentRecord] = {}
        for document in documents:
            if not document.id:
                raise ValueError("document_legacy_import_id_required")
            if document.id in unique and unique[document.id] != document:
                raise DocumentLegacyImportConflict(document.id)
            unique[document.id] = document
        for _ in range(3):
            try:
                with self.database.session() as session:
                    for document in unique.values():
                        row = session.get(DocumentRow, document.id)
                        if row is None:
                            session.add(DocumentRow(**_document_values(document)))
                        elif document_from_row(row) != document:
                            raise DocumentLegacyImportConflict(document.id)
                    session.flush()
                return
            except IntegrityError:
                # A competing import may insert an ID after our read. Recheck
                # the whole batch so a divergent row can never be overwritten.
                continue
        raise RuntimeError("document_legacy_import_race")

    def rename_study_unit(
        self,
        *,
        document_id: str,
        study_unit_id: str,
        title: str,
        expected_revision: int,
    ) -> DocumentRecord:
        with self.database.session() as session:
            row = session.get(DocumentRow, document_id)
            if row is None:
                raise DocumentNotFound(document_id)
            document = document_from_row(row)
            if document.revision != expected_revision:
                raise DocumentRevisionConflict(document_id, expected_revision, document.revision)
            if document.status == "processing":
                raise DocumentProcessingConflict(document_id)
            unit = next((unit for unit in document.study_units if unit.id == study_unit_id), None)
            if unit is None:
                raise StudyUnitNotFound(study_unit_id)
            unit.title = title
            for section in document.sections:
                if section.id == study_unit_id:
                    section.title = title
            document.revision += 1
            document.updated_at = datetime.now(timezone.utc).isoformat()
            replace_document_in_session(session, document, expected_revision=expected_revision)
            debug_row = session.get(DocumentDebugRow, document_id)
            if debug_row is not None:
                debug = DocumentDebugRecord.model_validate(debug_row.payload or {})
                for debug_unit in debug.study_units:
                    if debug_unit.id == study_unit_id:
                        debug_unit.title = title
                debug_row.payload = debug.model_dump(mode="json")
            session.flush()
            return document


def document_from_row(row: DocumentRow) -> DocumentRecord:
    document = DocumentRecord.model_validate(row.payload or {})
    if document.revision != row.revision:
        raise ValueError(f"document_revision_projection_mismatch:{row.id}")
    return document


def replace_document_in_session(
    session: Session,
    document: DocumentRecord,
    *,
    expected_revision: int,
) -> None:
    """Fence the write in SQL, including when called inside a workflow commit."""
    if document.revision != expected_revision + 1:
        raise ValueError("document_revision_must_advance_once")
    result = session.execute(
        update(DocumentRow)
        .where(DocumentRow.id == document.id, DocumentRow.revision == expected_revision)
        .values(**_document_values(document))
        .execution_options(synchronize_session="fetch")
    )
    if result.rowcount != 1:
        actual = session.scalar(select(DocumentRow.revision).where(DocumentRow.id == document.id))
        raise DocumentRevisionConflict(document.id, expected_revision, actual)


def fence_document_in_session(session: Session, document: DocumentRecord) -> None:
    """Hold an unchanged Document through a Planning transaction without a new revision."""
    result = session.execute(
        update(DocumentRow)
        .where(DocumentRow.id == document.id, DocumentRow.revision == document.revision)
        .values(revision=document.revision)
        .execution_options(synchronize_session=False)
    )
    if result.rowcount != 1:
        actual = session.scalar(select(DocumentRow.revision).where(DocumentRow.id == document.id))
        raise DocumentRevisionConflict(document.id, document.revision, actual)


def _document_values(document: DocumentRecord) -> dict[str, Any]:
    return {
        "id": document.id,
        "revision": document.revision,
        "title": document.title,
        "original_filename": document.original_filename,
        "stored_path": document.stored_path,
        "status": document.status,
        "ocr_status": document.ocr_status,
        "created_at": document.created_at,
        "updated_at": document.updated_at,
        "payload": document.model_dump(mode="json"),
    }
