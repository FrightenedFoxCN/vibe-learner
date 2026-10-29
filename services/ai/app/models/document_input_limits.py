"""Versioned admission limits; packing targets are not hard text limits."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

DOCUMENT_UPLOAD_MAX_BYTES = 64 * 1024 * 1024
DOCUMENT_MULTIPART_OVERHEAD_BYTES = 1024 * 1024
DOCUMENT_MAX_PHYSICAL_PAGES = 512
DOCUMENT_MAX_TEXT_UNIT_CHARS = 65_536
UPLOAD_READ_CHUNK_BYTES = 64 * 1024

DocumentInputLimitCode = Literal[
    "document_upload_too_large",
    "document_upload_body_too_large",
    "document_page_limit_exceeded",
    "document_text_unit_too_large",
]


class DocumentInputLimitsV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    contract_version: Literal["document-input-limits-v1"] = "document-input-limits-v1"
    upload_max_bytes: int = DOCUMENT_UPLOAD_MAX_BYTES
    multipart_overhead_bytes: int = DOCUMENT_MULTIPART_OVERHEAD_BYTES
    max_physical_pages: int = DOCUMENT_MAX_PHYSICAL_PAGES
    max_text_unit_chars: int = DOCUMENT_MAX_TEXT_UNIT_CHARS
    oversized_unit_policy: Literal["preserve_until_hard_limit"] = (
        "preserve_until_hard_limit"
    )


class DocumentInputLimitError(RuntimeError):
    def __init__(
        self, code: DocumentInputLimitCode, *, limit: int, actual: int | None = None
    ):
        super().__init__(code)
        self.code = code
        self.limit = limit
        self.actual = actual

    def detail(self) -> dict[str, str | int | None]:
        messages = {
            "document_upload_too_large": "PDF 文件超过 64 MiB，请拆分或压缩后重新上传。",
            "document_upload_body_too_large": "上传请求超过容量上限，请只上传一份不超过 64 MiB 的 PDF。",
            "document_page_limit_exceeded": "PDF 超过 512 个物理页，请拆分后重新上传。",
            "document_text_unit_too_large": "单段文本超过 65,536 个字符；请拆分该页内容或重新导出 PDF 后上传。",
        }
        return {
            "contract_version": "document-input-error-v1",
            "code": self.code,
            "message": messages[self.code],
            "limit": self.limit,
            "actual": self.actual,
            "recovery_action": "split_or_reexport_pdf",
        }
