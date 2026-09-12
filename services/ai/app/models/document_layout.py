from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


DocumentLayoutLabel = Literal["Picture", "Formula"]


class DocumentLayoutContractModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True, allow_inf_nan=False)


class DocumentLayoutBoxV1(DocumentLayoutContractModel):
    x: float = Field(ge=0.0, le=1.0)
    y: float = Field(ge=0.0, le=1.0)
    width: float = Field(gt=0.0, le=1.0)
    height: float = Field(gt=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_extent(self) -> "DocumentLayoutBoxV1":
        if self.x + self.width > 1.000001 or self.y + self.height > 1.000001:
            raise ValueError("document_layout_box_out_of_bounds")
        return self


class DocumentLayoutCandidateV1(DocumentLayoutContractModel):
    candidate_id: Annotated[str, Field(pattern=r"^layout-[0-9]{3}$")]
    label: DocumentLayoutLabel
    confidence: float = Field(ge=0.0, le=1.0)
    box: DocumentLayoutBoxV1
    depth: Literal[0, 1]
    parent_candidate_id: Annotated[str, Field(pattern=r"^layout-[0-9]{3}$")] | None = None

    @model_validator(mode="after")
    def validate_parent(self) -> "DocumentLayoutCandidateV1":
        if self.depth == 0 and self.parent_candidate_id is not None:
            raise ValueError("document_layout_root_has_parent")
        if self.depth == 1 and self.parent_candidate_id is None:
            raise ValueError("document_layout_child_missing_parent")
        return self


class DocumentLayoutDetectionV1(DocumentLayoutContractModel):
    schema_name: Literal["DocumentLayoutDetection"] = "DocumentLayoutDetection"
    schema_version: Literal["document-layout-detection-v1"] = "document-layout-detection-v1"
    status: Literal["completed", "disabled", "unavailable", "failed"]
    engine: Literal["doclayout-yolo", "disabled"]
    model_id: str = ""
    model_revision: str = ""
    source_sha256: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    width: int = Field(ge=1, le=20_000)
    height: int = Field(ge=1, le=20_000)
    labels: tuple[DocumentLayoutLabel, ...]
    recursive_picture: bool
    candidates: tuple[DocumentLayoutCandidateV1, ...] = ()
    warning: Annotated[str, Field(max_length=500)] = ""

