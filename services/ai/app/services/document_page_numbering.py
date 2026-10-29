"""Read exact PDF label metadata without inferring printed numbers from content."""

from __future__ import annotations

import fitz
from fastapi import HTTPException

from app.models.domain import DocumentRecord
from app.models.pdf_page_scope import (
    DocumentPageCoordinateV1,
    DocumentPageNumberingResponseV1,
    PrintedPageLabelV1,
)


def read_document_page_numbering(
    document: DocumentRecord, pages: list[int]
) -> DocumentPageNumberingResponseV1:
    if (
        not pages
        or len(pages) > 64
        or len(set(pages)) != len(pages)
        or any(page < 1 or page > document.page_count for page in pages)
    ):
        raise HTTPException(422, "document_physical_page_out_of_range")
    try:
        with fitz.open(document.stored_path) as pdf:
            if len(pdf) != document.page_count:
                raise HTTPException(409, "document_page_numbering_changed")
            has_labels = bool(pdf.get_page_labels())
            coordinates = []
            for number in pages:
                label = pdf[number - 1].get_label() if has_labels else ""
                coordinates.append(
                    DocumentPageCoordinateV1(
                        physical_pdf_page=number,
                        printed_page=PrintedPageLabelV1(label=label) if label else None,
                    )
                )
    except (OSError, ValueError, RuntimeError) as exc:
        raise HTTPException(409, "document_page_numbering_unavailable") from exc
    return DocumentPageNumberingResponseV1(
        document_id=document.id,
        document_revision=document.revision,
        physical_page_count=document.page_count,
        pages=coordinates,
    )
