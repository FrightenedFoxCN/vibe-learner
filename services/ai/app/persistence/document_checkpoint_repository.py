"""Bounded row checkpoints fenced by the admitted Document process operation."""

from __future__ import annotations

import json
from dataclasses import asdict

from fastapi import HTTPException
from sqlalchemy import select, update, delete

from app.models.document_checkpoint import (
    CHECKPOINT_MAX_BYTES,
    CHECKPOINT_MAX_PAGES,
    DocumentCheckpointSnapshotV1,
    ExtractedPageCheckpointV1,
    DocumentCheckpointResponseV1,
)
from app.models.harness import canonical_harness_digest
from app.models.harness_operation import HarnessDomainOperationKind
from app.persistence.harness_operation_repository import (
    HarnessOperationBindingRepository,
    HarnessOperationDomainNotFound,
    HarnessOperationLegacyUnbound,
)
from app.persistence.models import (
    DocumentCheckpointRow,
    DocumentCheckpointPageRow,
    DocumentCheckpointResumeRow,
    DocumentProcessOperationRow,
)


def byte_size(payload):
    return len(
        json.dumps(
            payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode()
    )


class DocumentCheckpointRepository:
    def __init__(self, database):
        self.database = database
        self.bindings = HarnessOperationBindingRepository(database)

    def _authorize(self, session, operation_id):
        try:
            self.bindings.require_domain_in_session(
                session,
                domain_operation_kind=HarnessDomainOperationKind.DOCUMENT_PROCESS,
                domain_operation_id=operation_id,
            )
        except (HarnessOperationDomainNotFound, HarnessOperationLegacyUnbound) as exc:
            raise HTTPException(404, "document_checkpoint_not_found") from exc
        row = session.get(DocumentProcessOperationRow, operation_id)
        if row is None:
            raise HTTPException(404, "document_checkpoint_not_found")
        return row

    def _write(self, session, operation_id):
        operation = self._authorize(session, operation_id)
        result = session.execute(
            update(DocumentProcessOperationRow)
            .where(
                DocumentProcessOperationRow.operation_id == operation_id,
                DocumentProcessOperationRow.status == "running",
            )
            .values(updated_at=DocumentProcessOperationRow.updated_at)
        )
        if result.rowcount != 1:
            raise HTTPException(409, "document_checkpoint_operation_fenced")
        return operation

    def initialize(
        self, operation_id, *, upload_digest, configuration_digest, force_ocr
    ):
        with self.database.session() as session:
            operation = self._write(session, operation_id)
            row = session.get(DocumentCheckpointRow, operation_id)
            if row is None:
                session.add(
                    DocumentCheckpointRow(
                        operation_id=operation_id,
                        document_id=operation.document_id,
                        upload_digest=upload_digest,
                        configuration_digest=configuration_digest,
                        force_ocr=force_ocr,
                        page_count=0,
                        byte_count=0,
                        storage_limited=False,
                        report=None,
                        output=None,
                        stage_digest="",
                        committed_document=None,
                    )
                )
            elif (row.upload_digest, row.configuration_digest, row.force_ocr) != (
                upload_digest,
                configuration_digest,
                force_ocr,
            ):
                raise HTTPException(409, "document_checkpoint_input_changed")

    def snapshot(self, operation_id) -> DocumentCheckpointSnapshotV1:
        with self.database.session() as session:
            self._authorize(session, operation_id)
            row = session.get(DocumentCheckpointRow, operation_id)
            if row is None:
                raise HTTPException(404, "document_checkpoint_not_found")
            pages = session.scalars(
                select(DocumentCheckpointPageRow)
                .where(DocumentCheckpointPageRow.operation_id == operation_id)
                .order_by(DocumentCheckpointPageRow.page_number)
            ).all()
            if any(
                canonical_harness_digest(page.payload) != page.payload_digest
                for page in pages
            ):
                raise HTTPException(409, "document_checkpoint_digest_mismatch")
            if canonical_harness_digest(
                {"report": row.report, "output": row.output}
            ) != row.stage_digest and (
                row.report is not None or row.output is not None
            ):
                raise HTTPException(409, "document_checkpoint_digest_mismatch")
            return DocumentCheckpointSnapshotV1.model_validate(
                {
                    "operation_id": operation_id,
                    "document_id": row.document_id,
                    "upload_digest": row.upload_digest,
                    "configuration_digest": row.configuration_digest,
                    "force_ocr": row.force_ocr,
                    "page_count": row.page_count,
                    "pages": [page.payload for page in pages],
                    "report": row.report
                    if row.report is not None
                    else row.output.get("debug_report")
                    if row.output
                    else None,
                    "output": row.output,
                    "storage_limited": row.storage_limited,
                }
            )

    def set_page_count(self, operation_id, count):
        with self.database.session() as session:
            self._write(session, operation_id)
            row = session.get(DocumentCheckpointRow, operation_id)
            if row.page_count not in {0, count}:
                raise HTTPException(409, "document_checkpoint_page_count_changed")
            row.page_count = count

    def save_page(self, operation_id, parsed):
        payload = {
            **asdict(parsed),
            "line_entries": [
                {"text": text, "font_size": float(font)}
                for text, font in parsed.line_entries
            ],
            "warnings": [
                warning.model_dump(mode="json") for warning in parsed.warnings
            ],
        }
        if parsed.page_number > CHECKPOINT_MAX_PAGES:
            return
        page = ExtractedPageCheckpointV1.model_validate(payload)
        payload = page.model_dump(mode="json")
        with self.database.session() as session:
            self._write(session, operation_id)
            row = session.get(DocumentCheckpointRow, operation_id)
            existing = session.get(
                DocumentCheckpointPageRow, (operation_id, parsed.page_number)
            )
            if existing is not None:
                if existing.payload_digest != canonical_harness_digest(payload):
                    raise HTTPException(409, "document_checkpoint_page_changed")
                return
            size = byte_size(payload)
            if row.storage_limited or row.byte_count + size > CHECKPOINT_MAX_BYTES:
                row.storage_limited = True
                return
            previous = (
                session.scalar(
                    select(DocumentCheckpointPageRow.page_number)
                    .where(DocumentCheckpointPageRow.operation_id == operation_id)
                    .order_by(DocumentCheckpointPageRow.page_number.desc())
                    .limit(1)
                )
                or 0
            )
            if parsed.page_number != previous + 1:
                raise ValueError("document_checkpoint_page_gap")
            session.add(
                DocumentCheckpointPageRow(
                    operation_id=operation_id,
                    page_number=parsed.page_number,
                    payload=payload,
                    payload_digest=canonical_harness_digest(payload),
                )
            )
            row.byte_count += size

    def save_stage(self, operation_id, report, output=None):
        report_payload = report.model_dump(mode="json") if output is None else None
        output_payload = output.model_dump(mode="json") if output is not None else None
        with self.database.session() as session:
            self._write(session, operation_id)
            row = session.get(DocumentCheckpointRow, operation_id)
            size = byte_size(report_payload) + byte_size(output_payload)
            page_bytes = sum(
                byte_size(payload)
                for payload in session.scalars(
                    select(DocumentCheckpointPageRow.payload).where(
                        DocumentCheckpointPageRow.operation_id == operation_id
                    )
                )
            )
            reusable_report = not (
                row.force_ocr
                and report.ocr_status
                in {"failed", "partial", "unavailable", "required"}
            )
            if (
                page_bytes + size > CHECKPOINT_MAX_BYTES
                and size <= CHECKPOINT_MAX_BYTES
                and reusable_report
            ):
                session.execute(
                    delete(DocumentCheckpointPageRow).where(
                        DocumentCheckpointPageRow.operation_id == operation_id
                    )
                )
                page_bytes = 0
            if (
                page_bytes + size > CHECKPOINT_MAX_BYTES
                or report.page_count > CHECKPOINT_MAX_PAGES
            ):
                row.storage_limited = True
                return
            row.page_count = report.page_count
            row.storage_limited = False
            row.report = report_payload
            row.output = output_payload
            row.stage_digest = canonical_harness_digest(
                {"report": report_payload, "output": output_payload}
            )
            row.byte_count = page_bytes + size

    def resume_child(self, source_id):
        with self.database.session() as session:
            self._authorize(session, source_id)
            row = session.get(DocumentCheckpointResumeRow, source_id)
            return row.child_operation_id if row else None

    def committed_read_back(self, operation_id):
        from app.models.domain import DocumentRecord
        from app.models.document_process_operation import (
            document_process_projection_digest,
        )

        with self.database.session() as session:
            operation = self._authorize(session, operation_id)
            row = session.get(DocumentCheckpointRow, operation_id)
            if (
                operation.status != "committed"
                or row is None
                or row.committed_document is None
            ):
                raise HTTPException(409, "document_checkpoint_child_not_committed")
            if (
                document_process_projection_digest(row.committed_document)
                != operation.document_digest
            ):
                raise HTTPException(409, "document_checkpoint_commit_digest_mismatch")
            return DocumentRecord.model_validate(row.committed_document)

    def public_view(self, operation_id):
        snapshot = self.snapshot(operation_id)
        with self.database.session() as session:
            operation = self._authorize(session, operation_id)
            child = session.get(DocumentCheckpointResumeRow, operation_id)
            status = operation.status
        pages = snapshot.pages[-64:]
        page_previews = [
            {
                "page_number": p.page_number,
                "text_preview": "\n".join(line.text for line in p.line_entries)[:400],
                "extraction_source": p.extraction_source,
            }
            for p in pages
        ]
        if snapshot.report is not None:
            page_previews = [
                {
                    "page_number": p.page_number,
                    "text_preview": p.text_preview,
                    "extraction_source": p.extraction_source,
                }
                for p in snapshot.report.pages[-64:]
            ]
        result = {
            "contract_version": "document-checkpoint-response-v1",
            "operation_id": operation_id,
            "document_id": snapshot.document_id,
            "operation_status": status,
            "page_count": snapshot.page_count,
            "completed_page_count": snapshot.report.page_count
            if snapshot.report
            else len(snapshot.pages),
            "stage": "study_units"
            if snapshot.output
            else "parsed"
            if snapshot.report
            else "pages",
            "force_ocr": snapshot.force_ocr,
            "storage_limited": snapshot.storage_limited,
            "child_operation_id": child.child_operation_id if child else None,
            "pages": page_previews,
            "study_units": [
                unit.model_dump(mode="json") for unit in snapshot.output.study_units
            ]
            if snapshot.output
            else [],
            "result": self.committed_read_back(operation_id).model_dump(mode="json")
            if status == "committed"
            else None,
            "projection_state": "committed"
            if status == "committed"
            else "checkpoint_only",
        }
        return DocumentCheckpointResponseV1.model_validate(result).model_dump(
            mode="json"
        )


class ParserCheckpoint:
    def __init__(
        self, repository, operation_id, source: DocumentCheckpointSnapshotV1 | None
    ):
        self.repository = repository
        self.operation_id = operation_id
        self.pages = {p.page_number: p for p in source.pages} if source else {}

    def set_page_count(self, count):
        self.repository.set_page_count(self.operation_id, count)

    def load_page(self, number):
        from app.models.domain import ParseWarning
        from app.services.document_parser import ParsedPage
        from app.services.ocr_engine import OcrPageResult

        page = self.pages.get(number)
        if page is None or (
            page.ocr_result is not None and page.ocr_result.status != "completed"
        ):
            return None
        parsed = ParsedPage(
            page_number=page.page_number,
            line_entries=[(line.text, line.font_size) for line in page.line_entries],
            dominant_font_size=page.dominant_font_size,
            extraction_source=page.extraction_source,
            warnings=[
                ParseWarning.model_validate(w.model_dump(mode="json"))
                for w in page.warnings
            ],
            used_ocr=page.used_ocr,
            ocr_result=OcrPageResult(**page.ocr_result.model_dump(mode="python"))
            if page.ocr_result
            else None,
        )
        self.repository.save_page(self.operation_id, parsed)
        return parsed

    def save_page(self, page):
        self.repository.save_page(self.operation_id, page)
