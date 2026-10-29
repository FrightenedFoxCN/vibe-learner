"""Read byte-bounded inputs before admission and inspect PDF page metadata only."""

from __future__ import annotations

from pathlib import Path
from typing import BinaryIO

import fitz

from app.models.document_input_limits import (
    DOCUMENT_UPLOAD_MAX_BYTES,
    DOCUMENT_MAX_PHYSICAL_PAGES,
    UPLOAD_READ_CHUNK_BYTES,
    DocumentInputLimitError,
)


def read_bounded_upload(handle: BinaryIO) -> bytes:
    parts = []
    size = 0
    while True:
        part = handle.read(
            min(UPLOAD_READ_CHUNK_BYTES, DOCUMENT_UPLOAD_MAX_BYTES + 1 - size)
        )
        if not part:
            break
        size += len(part)
        if size > DOCUMENT_UPLOAD_MAX_BYTES:
            raise DocumentInputLimitError(
                "document_upload_too_large",
                limit=DOCUMENT_UPLOAD_MAX_BYTES,
                actual=size,
            )
        parts.append(part)
    return b"".join(parts)


def validate_pdf_page_count(count: int) -> None:
    if count > DOCUMENT_MAX_PHYSICAL_PAGES:
        raise DocumentInputLimitError(
            "document_page_limit_exceeded",
            limit=DOCUMENT_MAX_PHYSICAL_PAGES,
            actual=count,
        )


def validate_upload_pdf_metadata(contents: bytes) -> None:
    # An invalid/opaque upload retains the existing process-stage failure path.
    # Any PDF MuPDF can open is page-bounded here, even with a repaired header.
    try:
        pdf = fitz.open(stream=contents, filetype="pdf")
    except (fitz.FileDataError, ValueError, RuntimeError):
        return
    with pdf:
        validate_pdf_page_count(pdf.page_count)


def read_bounded_document(path: str) -> bytes:
    with Path(path).open("rb") as handle:
        contents = read_bounded_upload(handle)
    validate_upload_pdf_metadata(contents)
    return contents
