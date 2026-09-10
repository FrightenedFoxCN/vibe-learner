"""Committed-document inputs and deterministic replies for planning operation tests."""
from app.models.api import LearningPlanCreateRequest
from app.models.domain import (
    DocumentRecord,
    DocumentDebugRecord,
    StudyUnitRecord,
    PlanGenerationTraceRecord,
)
from app.models.planning import (
    PlanContentSliceProposalV1,
    PlanScheduleChapterProposalV1,
)
from app.services.provider_capabilities import PlanModelReply, PlanScheduleItem

def planning_goal(
    document: DocumentRecord,
    client_request_id: str,
    persona_id: str,
) -> LearningPlanCreateRequest:
    return LearningPlanCreateRequest(
        client_request_id=client_request_id,
        expected_document_updated_at=document.updated_at,
        document_id=document.id,
        persona_id=persona_id,
        objective="Master vectors",
    )


def planning_document(*, document_id: str = "doc-plan-operation") -> DocumentRecord:
    unit = StudyUnitRecord(
        id=f"{document_id}:study-unit:1",
        document_id=document_id,
        title="Vectors",
        page_start=1,
        page_end=12,
        unit_kind="chapter",
        include_in_plan=True,
        source_section_ids=["raw-1"],
        summary="Vector foundations.",
        confidence=0.95,
    )
    return DocumentRecord(
        id=document_id,
        title="Linear Algebra",
        original_filename="linear-algebra.pdf",
        stored_path="/tmp/linear-algebra.pdf",
        status="processed",
        ocr_status="completed",
        created_at="2026-08-24T10:00:00+00:00",
        updated_at="2026-08-24T10:00:00+00:00",
        sections=[],
        study_units=[unit],
        study_unit_count=1,
        page_count=12,
        chunk_count=2,
        preview_excerpt="Vectors",
        debug_ready=True,
    )


def planning_debug(document: DocumentRecord) -> DocumentDebugRecord:
    return DocumentDebugRecord(
        document_id=document.id,
        parser_name="test-parser",
        processed_at=document.updated_at,
        page_count=document.page_count,
        total_characters=1000,
        extraction_method="text",
        pages=[],
        sections=[],
        study_units=[item.model_copy(deep=True) for item in document.study_units],
        chunks=[],
        warnings=[],
        dominant_language_hint="en",
    )


def planning_reply(document: DocumentRecord) -> PlanModelReply:
    unit = document.study_units[0]
    return PlanModelReply(
        course_title="Linear Algebra / Vectors",
        overview="A committed plan.",
        today_tasks=["Read vector definitions."],
        schedule=[
            PlanScheduleItem(
                unit_id=unit.id,
                title="Vectors deep read",
                focus="Definitions and examples.",
                activity_type="learn",
                schedule_chapters=[
                    PlanScheduleChapterProposalV1(
                        title="Vectors",
                        anchor_page_start=unit.page_start,
                        anchor_page_end=unit.page_end,
                        source_section_ids=["raw-1"],
                        content_slices=[
                            PlanContentSliceProposalV1(
                                page_start=unit.page_start,
                                page_end=unit.page_end,
                                source_section_ids=["raw-1"],
                            )
                        ],
                    )
                ],
            )
        ],
        debug_trace=PlanGenerationTraceRecord(
            document_id=document.id,
            model="test-model",
            created_at="2026-08-24T10:00:01+00:00",
            rounds=[],
        ),
    )

