"""Resolve Planning intent without promoting model guesses to user instructions."""
from __future__ import annotations

from collections.abc import Iterable

from app.models.domain import PlanningIntentV1, StudyUnitRecord


def explicit_page_ranges(intent: PlanningIntentV1) -> list[tuple[int, int]]:
    if intent.pdf_page_ranges.status != "user_explicit":
        return []
    return [
        (item.page_start, item.page_end)
        for item in (intent.pdf_page_ranges.value or [])
    ]


def explicit_outline_targets(intent: PlanningIntentV1) -> set[str]:
    if intent.outline_targets.status != "user_explicit":
        return set()
    return set(intent.outline_targets.value or [])


def range_is_within_explicit_scope(
    *, page_start: int, page_end: int, intent: PlanningIntentV1
) -> bool:
    ranges = explicit_page_ranges(intent)
    if not ranges:
        return True
    return any(page_start >= start and page_end <= end for start, end in ranges)


def select_study_units_for_intent(
    *, study_units: list[StudyUnitRecord], intent: PlanningIntentV1
) -> list[StudyUnitRecord]:
    page_ranges = explicit_page_ranges(intent)
    outline_targets = explicit_outline_targets(intent)
    selected: list[StudyUnitRecord] = []
    for unit in study_units:
        if page_ranges and not any(
            unit.page_start <= end and unit.page_end >= start
            for start, end in page_ranges
        ):
            continue
        if outline_targets and not outline_targets.intersection(unit.source_section_ids):
            continue
        selected.append(unit)
    return selected


def validate_intent_against_document(
    *, intent: PlanningIntentV1, page_count: int, section_ids: Iterable[str]
) -> None:
    for start, end in explicit_page_ranges(intent):
        if page_count <= 0 or end > page_count:
            raise RuntimeError("planning_intent_invalid:pdf_page_ranges:outside_document")
    targets = explicit_outline_targets(intent)
    unknown = targets.difference(section_ids)
    if unknown:
        raise RuntimeError("planning_intent_invalid:outline_targets:unknown_ref")


def validate_schedule_against_intent(*, schedule: list[object], intent: PlanningIntentV1) -> None:
    if intent.session_count.status == "user_explicit":
        expected = intent.session_count.value
        if len(schedule) != expected:
            raise RuntimeError(
                "plan_proposal_invariant_failed:schedule:explicit_session_count_mismatch"
            )

    expected_minutes = (
        intent.minutes_per_session.value
        if intent.minutes_per_session.status == "user_explicit"
        else None
    )
    covered_pages: set[int] = set()
    for index, item in enumerate(schedule):
        duration = getattr(item, "duration_minutes", None)
        if expected_minutes is not None and duration != expected_minutes:
            raise RuntimeError(
                f"plan_proposal_invariant_failed:schedule.{index}.duration_minutes:"
                "explicit_minutes_mismatch"
            )
        for chapter_index, chapter in enumerate(getattr(item, "schedule_chapters", [])):
            if not range_is_within_explicit_scope(
                page_start=chapter.anchor_page_start,
                page_end=chapter.anchor_page_end,
                intent=intent,
            ):
                raise RuntimeError(
                    f"plan_proposal_invariant_failed:schedule.{index}.schedule_chapters."
                    f"{chapter_index}.anchor_page_start:outside_explicit_scope"
                )
            for slice_index, content_slice in enumerate(chapter.content_slices):
                if not range_is_within_explicit_scope(
                    page_start=content_slice.page_start,
                    page_end=content_slice.page_end,
                    intent=intent,
                ):
                    raise RuntimeError(
                        f"plan_proposal_invariant_failed:schedule.{index}.schedule_chapters."
                        f"{chapter_index}.content_slices.{slice_index}:outside_explicit_scope"
                    )
                covered_pages.update(
                    range(content_slice.page_start, content_slice.page_end + 1)
                )

    requested_pages = {
        page
        for start, end in explicit_page_ranges(intent)
        for page in range(start, end + 1)
    }
    if requested_pages and not requested_pages.issubset(covered_pages):
        raise RuntimeError(
            "plan_proposal_invariant_failed:schedule:explicit_page_scope_incomplete"
        )
