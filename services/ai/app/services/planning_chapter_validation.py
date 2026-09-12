"""Shared proposal geometry/reference checks for provider repair and domain commit."""
from dataclasses import dataclass
from typing import Literal
from app.models.domain import StudyUnitRecord
from app.models.planning import PlanScheduleChapterProposalV1


@dataclass(frozen=True)
class PlanningChapterViolation:
    path: str
    reason: Literal['outside_unit', 'not_ordered', 'unknown_ref', 'outside_chapter']


def find_chapter_violation(*, chapter: PlanScheduleChapterProposalV1,
                           unit: StudyUnitRecord, previous_anchor_start: int) -> PlanningChapterViolation | None:
    if chapter.anchor_page_start < unit.page_start or chapter.anchor_page_end > unit.page_end:
        return PlanningChapterViolation('anchor_page_start', 'outside_unit')
    if chapter.anchor_page_start < previous_anchor_start:
        return PlanningChapterViolation('anchor_page_start', 'not_ordered')
    allowed = set(unit.source_section_ids)
    if not set(chapter.source_section_ids).issubset(allowed):
        return PlanningChapterViolation('source_section_ids', 'unknown_ref')
    previous_slice_start = 0
    for index, item in enumerate(chapter.content_slices):
        path = f'content_slices.{index}'
        if item.page_start < chapter.anchor_page_start or item.page_end > chapter.anchor_page_end:
            return PlanningChapterViolation(path, 'outside_chapter')
        if item.page_start < previous_slice_start:
            return PlanningChapterViolation(path, 'not_ordered')
        if not set(item.source_section_ids).issubset(allowed):
            return PlanningChapterViolation(f'{path}.source_section_ids', 'unknown_ref')
        previous_slice_start = item.page_start
    return None
