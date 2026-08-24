from __future__ import annotations

import base64
import hashlib
import io
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import fitz
from fastapi import HTTPException, UploadFile

from app.models.domain import LearnerAttachmentRecord, PdfRectRecord
from app.models.harness_effect import HARNESS_EFFECT_ADAPTER_POLICIES
from app.services.local_store import LocalJsonStore

_MAX_ATTACHMENT_COUNT = 4
_MAX_ATTACHMENT_FILE_BYTES = 12 * 1024 * 1024
_MAX_ATTACHMENT_TOTAL_BYTES = 24 * 1024 * 1024
_MAX_TEXT_EXCERPT_CHARS = 4000
_SAFE_PATH_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")
_TEXTUAL_MIME_TYPES = {
    "application/json",
    "application/ld+json",
    "application/xml",
    "application/javascript",
    "application/x-javascript",
    "application/yaml",
    "application/x-yaml",
    "text/csv",
    "text/markdown",
}
STUDY_ATTACHMENT_STAGE_ADAPTER = HARNESS_EFFECT_ADAPTER_POLICIES[
    "study_attachment_stage"
]


@dataclass
class PreparedStudyChatAttachments:
    records: list[LearnerAttachmentRecord]
    attachment_context: str
    multimodal_parts: list[dict[str, Any]]
    operation_id: str = ""
    staged_effect_ids: list[str] = field(default_factory=list)

    @property
    def effect_adapter(self):
        return STUDY_ATTACHMENT_STAGE_ADAPTER


@dataclass
class StudyChatAttachmentInput:
    filename: str
    mime_type: str
    raw_bytes: bytes


def read_study_chat_attachment_inputs(
    files: list[UploadFile],
) -> list[StudyChatAttachmentInput]:
    normalized_files = [file for file in files if file.filename]
    if len(normalized_files) > _MAX_ATTACHMENT_COUNT:
        raise HTTPException(status_code=422, detail="chat_attachment_count_exceeded")
    result: list[StudyChatAttachmentInput] = []
    total_bytes = 0
    for file in normalized_files:
        raw_bytes = file.file.read(_MAX_ATTACHMENT_FILE_BYTES + 1)
        file.file.seek(0)
        if len(raw_bytes) > _MAX_ATTACHMENT_FILE_BYTES:
            raise HTTPException(status_code=413, detail="chat_attachment_file_too_large")
        total_bytes += len(raw_bytes)
        if total_bytes > _MAX_ATTACHMENT_TOTAL_BYTES:
            raise HTTPException(status_code=413, detail="chat_attachment_total_too_large")
        if not raw_bytes:
            continue
        filename = (file.filename or "attachment").strip() or "attachment"
        mime_type = (file.content_type or _guess_mime_type(filename)).strip() or "application/octet-stream"
        result.append(
            StudyChatAttachmentInput(
                filename=filename,
                mime_type=mime_type,
                raw_bytes=raw_bytes,
            )
        )
    return result


def study_chat_attachment_manifest(
    inputs: list[StudyChatAttachmentInput],
) -> list[dict[str, object]]:
    return [
        {
            "sha256": hashlib.sha256(item.raw_bytes).hexdigest(),
            "size_bytes": len(item.raw_bytes),
            "mime_type": item.mime_type,
            "normalized_name": _sanitize_filename(item.filename),
        }
        for item in inputs
    ]


def validate_study_chat_attachment_inputs(
    inputs: list[StudyChatAttachmentInput],
    *,
    allow_image_input: bool,
) -> None:
    """Validate bounded attachment content without publishing business files."""
    if len(inputs) > _MAX_ATTACHMENT_COUNT:
        raise HTTPException(status_code=422, detail="chat_attachment_count_exceeded")
    total_bytes = sum(len(item.raw_bytes) for item in inputs)
    if any(len(item.raw_bytes) > _MAX_ATTACHMENT_FILE_BYTES for item in inputs):
        raise HTTPException(status_code=413, detail="chat_attachment_file_too_large")
    if total_bytes > _MAX_ATTACHMENT_TOTAL_BYTES:
        raise HTTPException(status_code=413, detail="chat_attachment_total_too_large")
    for item in inputs:
        filename = item.filename
        mime_type = item.mime_type
        if mime_type.startswith("image/"):
            if not allow_image_input:
                raise HTTPException(status_code=400, detail="chat_image_upload_requires_multimodal")
            continue
        if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
            excerpt, _ = _extract_pdf_excerpt(item.raw_bytes)
            if not excerpt.strip():
                raise HTTPException(status_code=400, detail="chat_pdf_attachment_empty")
            continue
        if _is_textual_file(mime_type, filename):
            if not _extract_text_excerpt(item.raw_bytes).strip():
                raise HTTPException(status_code=400, detail="chat_text_attachment_empty")
            continue
        raise HTTPException(status_code=400, detail="chat_attachment_unsupported_media_type")


def prepare_study_chat_attachments(
    *,
    store: LocalJsonStore,
    session_id: str,
    files: list[UploadFile],
    allow_image_input: bool,
    inputs: list[StudyChatAttachmentInput] | None = None,
    operation_id: str = "",
    inputs_validated: bool = False,
) -> PreparedStudyChatAttachments:
    attachment_inputs = inputs if inputs is not None else read_study_chat_attachment_inputs(files)
    if not inputs_validated:
        validate_study_chat_attachment_inputs(
            attachment_inputs,
            allow_image_input=allow_image_input,
        )
    if operation_id:
        _validate_path_component(operation_id, "study_chat_operation_id_invalid")
    _validate_path_component(session_id, "study_chat_session_id_invalid")

    records: list[LearnerAttachmentRecord] = []
    context_blocks: list[str] = []
    multimodal_parts: list[dict[str, Any]] = []

    try:
        for attachment_index, attachment_input in enumerate(attachment_inputs):
            raw_bytes = attachment_input.raw_bytes
            filename = attachment_input.filename
            mime_type = attachment_input.mime_type
            size_bytes = len(raw_bytes)

            if mime_type.startswith("image/"):
                attachment_id = _attachment_id(operation_id, attachment_index)
                if not allow_image_input:
                    raise HTTPException(status_code=400, detail="chat_image_upload_requires_multimodal")
                image_url = _build_data_url(mime_type, raw_bytes)
                stored_path = _store_session_attachment_file(
                    store=store,
                    session_id=session_id,
                    attachment_id=attachment_id,
                    filename=filename,
                    raw_bytes=raw_bytes,
                    operation_id=operation_id,
                )
                records.append(
                    LearnerAttachmentRecord(
                        attachment_id=attachment_id,
                        name=filename,
                        mime_type=mime_type,
                        kind="image",
                        size_bytes=size_bytes,
                        image_url=image_url,
                        stored_path=str(stored_path),
                        page_count=1,
                        previewable=True,
                    )
                )
                multimodal_parts.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": image_url},
                    }
                )
                context_blocks.append(f"- 图片附件：{filename}（{mime_type}，{size_bytes} bytes）")
                continue

            if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
                attachment_id = _attachment_id(operation_id, attachment_index)
                excerpt, page_count = _extract_pdf_excerpt(raw_bytes)
                if not excerpt.strip():
                    raise HTTPException(status_code=400, detail="chat_pdf_attachment_empty")
                stored_path = _store_session_attachment_pdf(
                    store=store,
                    session_id=session_id,
                    attachment_id=attachment_id,
                    filename=filename,
                    raw_bytes=raw_bytes,
                    operation_id=operation_id,
                )
                records.append(
                    LearnerAttachmentRecord(
                        attachment_id=attachment_id,
                        name=filename,
                        mime_type="application/pdf",
                        kind="pdf",
                        size_bytes=size_bytes,
                        text_excerpt=excerpt,
                        stored_path=str(stored_path),
                        page_count=page_count,
                        previewable=True,
                    )
                )
                context_blocks.append(_render_text_attachment_block(filename, "PDF 摘录", excerpt))
                continue

            if _is_textual_file(mime_type, filename):
                excerpt = _extract_text_excerpt(raw_bytes)
                if not excerpt.strip():
                    raise HTTPException(status_code=400, detail="chat_text_attachment_empty")
                records.append(
                    LearnerAttachmentRecord(
                        attachment_id=_attachment_id(operation_id, attachment_index),
                        name=filename,
                        mime_type=mime_type,
                        kind="text",
                        size_bytes=size_bytes,
                        text_excerpt=excerpt,
                    )
                )
                context_blocks.append(_render_text_attachment_block(filename, "文本摘录", excerpt))
                continue

            raise HTTPException(status_code=400, detail="chat_attachment_unsupported_media_type")
    except Exception:
        cleanup_prepared_study_chat_attachments(
            store=store,
            session_id=session_id,
            records=records,
        )
        raise

    attachment_context = ""
    if context_blocks:
        attachment_context = "学习者本轮附带了这些材料，请先结合它们理解问题：\n" + "\n\n".join(context_blocks)
    return PreparedStudyChatAttachments(
        records=records,
        attachment_context=attachment_context,
        multimodal_parts=multimodal_parts,
        operation_id=operation_id,
        staged_effect_ids=[
            _attachment_stage_effect_id(operation_id, index)
            for index, record in enumerate(records)
            if operation_id and record.stored_path
        ],
    )


def cleanup_prepared_study_chat_attachments(
    *,
    store: LocalJsonStore,
    session_id: str,
    records: list[LearnerAttachmentRecord],
) -> int:
    """Remove only files created for this Session/attachment identity set."""
    session_root = _session_attachment_root(store.chat_attachment_root, session_id)
    removed = 0
    for record in records:
        if not record.stored_path:
            continue
        path = Path(record.stored_path).resolve()
        try:
            path.relative_to(session_root)
        except ValueError as exc:
            raise ValueError("study_chat_attachment_cleanup_scope_mismatch") from exc
        if not path.name.startswith(f"{record.attachment_id}-"):
            raise ValueError("study_chat_attachment_cleanup_identity_mismatch")
        if path.is_file():
            path.unlink()
            removed += 1
    return removed


def cleanup_staged_study_chat_operation_attachments(
    *,
    store: LocalJsonStore,
    session_id: str,
    operation_id: str,
) -> int:
    """Recover an operation-owned staging directory without broad deletion."""
    operation_root = _operation_attachment_root(
        store.chat_attachment_root,
        session_id,
        operation_id,
    )
    if not operation_root.exists():
        return 0
    removed = 0
    for child in list(operation_root.iterdir()):
        if not child.is_file():
            raise ValueError("study_chat_attachment_staging_shape_invalid")
        child.unlink()
        removed += 1
    operation_root.rmdir()
    return removed


def validate_committed_study_chat_attachment_read_back(
    *,
    chat_attachment_root: Path,
    session_id: str,
    operation_id: str,
    manifests,
    records: list[LearnerAttachmentRecord],
) -> None:
    """Bind a committed Turn projection to its admitted manifest and staged bytes."""
    if len(records) != len(manifests):
        raise ValueError("study_chat_attachment_read_back_count_mismatch")
    operation_root = _operation_attachment_root(
        chat_attachment_root,
        session_id,
        operation_id,
    )
    for index, (manifest, record) in enumerate(zip(manifests, records, strict=True)):
        expected_id = _attachment_id(operation_id, index)
        if (
            record.attachment_id != expected_id
            or _sanitize_filename(record.name) != manifest.normalized_name
            or record.size_bytes != manifest.size_bytes
        ):
            raise ValueError("study_chat_attachment_read_back_projection_mismatch")
        expected_kind = _attachment_kind(
            manifest.mime_type,
            manifest.normalized_name,
        )
        expected_mime_type = (
            "application/pdf" if expected_kind == "pdf" else manifest.mime_type
        )
        if record.kind != expected_kind or record.mime_type != expected_mime_type:
            raise ValueError("study_chat_attachment_read_back_kind_mismatch")
        if expected_kind == "text":
            if record.stored_path or not record.text_excerpt:
                raise ValueError("study_chat_attachment_text_read_back_mismatch")
            continue
        expected_path = (
            operation_root / f"{expected_id}-{manifest.normalized_name}"
        ).resolve()
        if Path(record.stored_path).resolve() != expected_path:
            raise ValueError("study_chat_attachment_path_read_back_mismatch")
        if not expected_path.is_file():
            raise ValueError("study_chat_attachment_file_read_back_missing")
        digest = hashlib.sha256(expected_path.read_bytes()).hexdigest()
        if digest != manifest.sha256:
            raise ValueError("study_chat_attachment_file_digest_mismatch")


def _render_text_attachment_block(filename: str, label: str, excerpt: str) -> str:
    return f"- {label}：{filename}\n```text\n{excerpt}\n```"


def _guess_mime_type(filename: str) -> str:
    lowered = filename.lower()
    if lowered.endswith(".md") or lowered.endswith(".markdown"):
        return "text/markdown"
    if lowered.endswith(".json"):
        return "application/json"
    if lowered.endswith(".csv"):
        return "text/csv"
    if lowered.endswith(".txt") or lowered.endswith(".log"):
        return "text/plain"
    if lowered.endswith(".pdf"):
        return "application/pdf"
    return "application/octet-stream"


def _is_textual_file(mime_type: str, filename: str) -> bool:
    return (
        mime_type.startswith("text/")
        or mime_type in _TEXTUAL_MIME_TYPES
        or filename.lower().endswith((".txt", ".md", ".markdown", ".json", ".csv", ".log", ".yaml", ".yml", ".xml"))
    )


def _extract_text_excerpt(raw_bytes: bytes) -> str:
    text = raw_bytes.decode("utf-8", errors="ignore").replace("\r\n", "\n").replace("\r", "\n")
    compact = text.strip()
    if len(compact) <= _MAX_TEXT_EXCERPT_CHARS:
        return compact
    return compact[: _MAX_TEXT_EXCERPT_CHARS - 1].rstrip() + "…"


def _extract_pdf_excerpt(raw_bytes: bytes) -> tuple[str, int]:
    excerpts: list[str] = []
    with fitz.open(stream=io.BytesIO(raw_bytes), filetype="pdf") as document:
        page_count = document.page_count
        for page in document[: min(document.page_count, 3)]:
            text = page.get_text("text").strip()
            if text:
                excerpts.append(text)
            if sum(len(item) for item in excerpts) >= _MAX_TEXT_EXCERPT_CHARS:
                break
    compact = "\n\n".join(excerpts).strip()
    if len(compact) <= _MAX_TEXT_EXCERPT_CHARS:
        return compact, page_count
    return compact[: _MAX_TEXT_EXCERPT_CHARS - 1].rstrip() + "…", page_count


def extract_pdf_page_range_text(
    *,
    pdf_path: str,
    page_start: int,
    page_end: int,
    max_chars: int = 4000,
) -> dict[str, object]:
    parts: list[str] = []
    total_chars = 0
    clamped_start = max(1, page_start)
    clamped_end = max(clamped_start, page_end)
    with fitz.open(pdf_path) as document:
        for page_number in range(clamped_start, min(clamped_end, document.page_count) + 1):
            text = document.load_page(page_number - 1).get_text("text").strip()
            if not text:
                continue
            page_block = f"[Page {page_number}]\n{text}"
            if parts and total_chars + len(page_block) > max_chars:
                remaining = max_chars - total_chars
                if remaining > 120:
                    parts.append(page_block[:remaining].rstrip())
                break
            parts.append(page_block)
            total_chars += len(page_block)
            if total_chars >= max_chars:
                break
    return {
        "page_start": clamped_start,
        "page_end": clamped_end,
        "content": "\n\n".join(parts).strip(),
    }


def search_pdf_text_rects(
    *,
    pdf_path: str,
    page_number: int,
    quote_text: str,
    max_matches: int = 8,
) -> list[PdfRectRecord]:
    normalized_quote = quote_text.strip()
    if not normalized_quote:
        return []
    with fitz.open(pdf_path) as document:
        page_index = page_number - 1
        if page_index < 0 or page_index >= document.page_count:
            return []
        page = document.load_page(page_index)
        page_rect = page.rect
        matches = page.search_for(normalized_quote)
        if not matches and len(normalized_quote) > 10:
            compact_quote = re.sub(r"\s+", " ", normalized_quote).strip()
            matches = page.search_for(compact_quote)
        return [
            _normalize_pdf_rect(match, page_rect)
            for match in matches[: max(1, min(max_matches, 12))]
        ]


def render_pdf_page_png_bytes(
    *,
    pdf_path: str,
    page_number: int,
    dpi: int = 144,
) -> bytes:
    with fitz.open(pdf_path) as document:
        page_index = page_number - 1
        if page_index < 0 or page_index >= document.page_count:
            raise HTTPException(status_code=404, detail="pdf_page_not_found")
        page = document.load_page(page_index)
        pixmap = page.get_pixmap(dpi=max(72, min(dpi, 216)), alpha=False)
        return pixmap.tobytes("png")


def _build_data_url(mime_type: str, raw_bytes: bytes) -> str:
    return f"data:{mime_type};base64,{base64.b64encode(raw_bytes).decode('ascii')}"


def _store_session_attachment_pdf(
    *,
    store: LocalJsonStore,
    session_id: str,
    attachment_id: str,
    filename: str,
    raw_bytes: bytes,
    operation_id: str,
) -> Path:
    return _store_session_attachment_file(
        store=store,
        session_id=session_id,
        attachment_id=attachment_id,
        filename=filename,
        raw_bytes=raw_bytes,
        operation_id=operation_id,
    )


def _store_session_attachment_file(
    *,
    store: LocalJsonStore,
    session_id: str,
    attachment_id: str,
    filename: str,
    raw_bytes: bytes,
    operation_id: str,
) -> Path:
    attachment_root = (
        _operation_attachment_root(
            store.chat_attachment_root,
            session_id,
            operation_id,
        )
        if operation_id
        else _session_attachment_root(store.chat_attachment_root, session_id)
    )
    attachment_root.mkdir(parents=True, exist_ok=True)
    safe_name = _sanitize_filename(filename)
    path = attachment_root / f"{attachment_id}-{safe_name}"
    path.write_bytes(raw_bytes)
    return path


def _attachment_id(operation_id: str, index: int) -> str:
    if not operation_id:
        return f"attach-{uuid4().hex[:10]}"
    digest = hashlib.sha256(f"{operation_id}:{index}".encode("utf-8")).hexdigest()[:20]
    return f"attach-{digest}"


def _attachment_stage_effect_id(operation_id: str, index: int) -> str:
    digest = hashlib.sha256(
        f"{operation_id}:attachment-stage:{index}".encode("utf-8")
    ).hexdigest()[:20]
    return f"study-file-effect-{digest}"


def _attachment_kind(mime_type: str, filename: str) -> str:
    if mime_type.startswith("image/"):
        return "image"
    if mime_type == "application/pdf" or filename.lower().endswith(".pdf"):
        return "pdf"
    return "text"


def _session_attachment_root(chat_attachment_root: Path, session_id: str) -> Path:
    _validate_path_component(session_id, "study_chat_session_id_invalid")
    root = chat_attachment_root.resolve()
    session_root = (root / session_id).resolve()
    try:
        session_root.relative_to(root)
    except ValueError as exc:
        raise ValueError("study_chat_attachment_session_scope_mismatch") from exc
    return session_root


def _operation_attachment_root(
    chat_attachment_root: Path,
    session_id: str,
    operation_id: str,
) -> Path:
    _validate_path_component(operation_id, "study_chat_operation_id_invalid")
    session_root = _session_attachment_root(chat_attachment_root, session_id)
    operation_root = (session_root / operation_id).resolve()
    try:
        operation_root.relative_to(session_root)
    except ValueError as exc:
        raise ValueError("study_chat_attachment_operation_scope_mismatch") from exc
    return operation_root


def _validate_path_component(value: str, error_code: str) -> None:
    if not _SAFE_PATH_COMPONENT.fullmatch(value):
        raise ValueError(error_code)


def _sanitize_filename(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", filename.strip()) or "attachment.bin"


def _normalize_pdf_rect(rect: fitz.Rect, page_rect: fitz.Rect) -> PdfRectRecord:
    page_width = max(page_rect.width, 1.0)
    page_height = max(page_rect.height, 1.0)
    return PdfRectRecord(
        x=max(0.0, min(1.0, rect.x0 / page_width)),
        y=max(0.0, min(1.0, rect.y0 / page_height)),
        width=max(0.0, min(1.0, rect.width / page_width)),
        height=max(0.0, min(1.0, rect.height / page_height)),
    )
