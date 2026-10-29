"""PDF physical coordinates and optional printed labels have different authority."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.models.domain import PlanningIntentV1


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PrintedPageLabelV1(_Strict):
    label: str = Field(min_length=1, max_length=128)
    source: Literal["pdf_metadata"] = "pdf_metadata"


class DocumentPageCoordinateV1(_Strict):
    physical_pdf_page: int = Field(ge=1)
    printed_page: PrintedPageLabelV1 | None = None


class DocumentPageNumberingResponseV1(_Strict):
    contract_version: Literal["document-page-numbering-v1"] = (
        "document-page-numbering-v1"
    )
    coordinate_system: Literal["pdf_physical_1_based"] = "pdf_physical_1_based"
    document_id: str
    document_revision: int = Field(ge=0)
    physical_page_count: int = Field(ge=1)
    pages: list[DocumentPageCoordinateV1] = Field(min_length=1, max_length=64)


class PhysicalPageScopeViolation(RuntimeError):
    pass


def validate_physical_input(intent: PlanningIntentV1, page_count: int) -> None:
    if intent.pdf_page_ranges.status != "user_explicit":
        return
    ranges = intent.pdf_page_ranges.value or []
    if len(ranges) > 64 or any(span.page_end > page_count for span in ranges):
        raise PhysicalPageScopeViolation(
            "planning_intent_invalid:pdf_page_ranges:outside_document"
        )


def validate_physical_schedule(
    schedule: list[object], intent: PlanningIntentV1
) -> None:
    """Bound anchors/slices and prove interval coverage without allocating page sets."""
    if intent.pdf_page_ranges.status != "user_explicit":
        return
    requested = intent.pdf_page_ranges.value or []
    spans: list[tuple[int, int]] = []
    for i, item in enumerate(schedule):
        for j, chapter in enumerate(getattr(item, "schedule_chapters", [])):
            path = f"schedule.{i}.schedule_chapters.{j}"
            if not any(
                chapter.anchor_page_start >= r.page_start
                and chapter.anchor_page_end <= r.page_end
                for r in requested
            ):
                raise PhysicalPageScopeViolation(
                    f"plan_proposal_invariant_failed:{path}.anchor_page_start:outside_explicit_scope"
                )
            for k, part in enumerate(chapter.content_slices):
                if not any(
                    part.page_start >= r.page_start and part.page_end <= r.page_end
                    for r in requested
                ):
                    raise PhysicalPageScopeViolation(
                        f"plan_proposal_invariant_failed:{path}.content_slices.{k}:outside_explicit_scope"
                    )
                spans.append((part.page_start, part.page_end))
    merged: list[tuple[int, int]] = []
    for start, end in sorted(spans):
        if merged and start <= merged[-1][1] + 1:
            merged[-1] = merged[-1][0], max(end, merged[-1][1])
        else:
            merged.append((start, end))
    if any(
        not any(start <= r.page_start and end >= r.page_end for start, end in merged)
        for r in requested
    ):
        raise PhysicalPageScopeViolation(
            "plan_proposal_invariant_failed:schedule:explicit_page_scope_incomplete"
        )
