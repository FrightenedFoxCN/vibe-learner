from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


DOCUMENT_PROCESS_REQUEST_SCHEMA_VERSION = "document-process-request-v1"
DOCUMENT_PROCESS_FINGERPRINT_CONTRACT_VERSION = "document-process-fingerprint-v1"
DOCUMENT_PROCESS_COMMIT_CONTRACT_VERSION = "document-process-commit-v1"


class DocumentProcessOperationStatus(str, Enum):
    RUNNING = "running"
    COMMITTED = "committed"
    FAILED = "failed"
    INTERRUPTED = "interrupted"


class DocumentProcessProjectionState(str, Enum):
    PENDING = "pending"
    COMMITTED = "committed"
    NOT_COMMITTED = "not_committed"


class DocumentProcessRequestPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str = Field(min_length=1, max_length=64)
    force_ocr: bool = False


class DocumentProcessOperationRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str
    document_id: str
    request_schema_version: str
    fingerprint_contract_version: str
    request_fingerprint: str
    request_payload: DocumentProcessRequestPayload
    status: DocumentProcessOperationStatus
    projection_state: DocumentProcessProjectionState
    base_document_payload: dict[str, Any]
    document_digest: str = ""
    debug_digest: str = ""
    commit_contract_version: str = ""
    error_code: str = ""
    created_at: str
    updated_at: str
    completed_at: str = ""

    @model_validator(mode="after")
    def validate_terminal_evidence(self) -> "DocumentProcessOperationRecord":
        if self.request_schema_version != DOCUMENT_PROCESS_REQUEST_SCHEMA_VERSION:
            raise ValueError("unsupported_document_process_request_schema")
        if self.fingerprint_contract_version != DOCUMENT_PROCESS_FINGERPRINT_CONTRACT_VERSION:
            raise ValueError("unsupported_document_process_fingerprint_contract")
        if self.request_payload.document_id != self.document_id:
            raise ValueError("document_process_request_identity_mismatch")
        expected_fingerprint = document_process_request_fingerprint(self.request_payload)
        if self.request_fingerprint != expected_fingerprint:
            raise ValueError("document_process_request_fingerprint_mismatch")
        if self.status == DocumentProcessOperationStatus.RUNNING:
            if self.projection_state != DocumentProcessProjectionState.PENDING:
                raise ValueError("running_document_process_projection_must_be_pending")
            if self.completed_at or self.error_code:
                raise ValueError("running_document_process_has_terminal_evidence")
        elif self.status == DocumentProcessOperationStatus.COMMITTED:
            if self.projection_state != DocumentProcessProjectionState.COMMITTED:
                raise ValueError("committed_document_process_projection_required")
            if (
                not self.completed_at
                or not self.document_digest
                or not self.debug_digest
                or self.commit_contract_version != DOCUMENT_PROCESS_COMMIT_CONTRACT_VERSION
                or self.error_code
            ):
                raise ValueError("committed_document_process_evidence_incomplete")
        else:
            if self.projection_state != DocumentProcessProjectionState.NOT_COMMITTED:
                raise ValueError("failed_document_process_must_be_not_committed")
            if not self.completed_at or not self.error_code:
                raise ValueError("failed_document_process_evidence_incomplete")
            if self.document_digest or self.debug_digest or self.commit_contract_version:
                raise ValueError("failed_document_process_has_commit_evidence")
        return self


def document_process_request_fingerprint(payload: DocumentProcessRequestPayload) -> str:
    return _digest(payload.model_dump(mode="json"))


def document_process_projection_digest(payload: dict[str, Any]) -> str:
    return _digest(payload)


def _digest(payload: dict[str, Any]) -> str:
    canonical = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
