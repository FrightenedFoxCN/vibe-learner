"""Resolve Planning intent without promoting model guesses to user instructions."""
from __future__ import annotations

from collections.abc import Iterable

from app.models.domain import (
    PlanningIntentV1,
    PlanningPageRangeV1,
    PlanningResolvedIntegerV1,
    PlanningResolvedIntentV1,
    PlanningResolvedLanguageV1,
    PlanningResolvedOutlineTargetsV1,
    PlanningResolvedPageRangesV1,
    StudyUnitRecord,
)


LEARN_MINUTES_PER_PAGE = 3
REVIEW_MINUTES_PER_PAGE = 1


def _scheduled_page_count(item: object) -> int:
    pages = {
        page
        for chapter in getattr(item, "schedule_chapters", [])
        for content_slice in chapter.content_slices
        for page in range(content_slice.page_start, content_slice.page_end + 1)
    }
    return len(pages)


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
    inferred_durations: set[int] = set()
    explicit_targets = explicit_outline_targets(intent)
    covered_pages: set[int] = set()
    for index, item in enumerate(schedule):
        duration = getattr(item, "duration_minutes", None)
        if not isinstance(duration, int):
            raise RuntimeError(
                f"plan_proposal_invariant_failed:schedule.{index}.duration_minutes:required"
            )
        inferred_durations.add(duration)
        if expected_minutes is not None and duration != expected_minutes:
            raise RuntimeError(
                f"plan_proposal_invariant_failed:schedule.{index}.duration_minutes:"
                "explicit_minutes_mismatch"
            )
        activity_type = getattr(item, "activity_type", None)
        minutes_per_page = (
            REVIEW_MINUTES_PER_PAGE
            if activity_type == "review"
            else LEARN_MINUTES_PER_PAGE
        )
        scheduled_pages = _scheduled_page_count(item)
        page_capacity = max(1, duration // minutes_per_page)
        coverage_mode = getattr(item, "coverage_mode", None)
        if scheduled_pages > page_capacity and coverage_mode is not None:
            if coverage_mode not in {"selective", "overview"}:
                raise RuntimeError(
                    f"plan_proposal_invariant_failed:schedule.{index}.coverage_mode:"
                    "overload_requires_selective_or_overview"
                )
            rationale = getattr(item, "workload_rationale", "")
            if not isinstance(rationale, str) or len(rationale.strip()) < 40:
                raise RuntimeError(
                    f"plan_proposal_invariant_failed:schedule.{index}.workload_rationale:"
                    "overload_requires_sufficient_rationale"
                )
        for chapter_index, chapter in enumerate(getattr(item, "schedule_chapters", [])):
            chapter_sources = set(chapter.source_section_ids)
            if explicit_targets and not chapter_sources.issubset(explicit_targets):
                raise RuntimeError(
                    f"plan_proposal_invariant_failed:schedule.{index}.schedule_chapters."
                    f"{chapter_index}.source_section_ids:outside_explicit_scope"
                )
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
                slice_sources = set(content_slice.source_section_ids)
                if explicit_targets and not slice_sources.issubset(explicit_targets):
                    raise RuntimeError(
                        f"plan_proposal_invariant_failed:schedule.{index}.schedule_chapters."
                        f"{chapter_index}.content_slices.{slice_index}.source_section_ids:"
                        "outside_explicit_scope"
                    )
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
    if expected_minutes is None and len(inferred_durations) != 1:
        raise RuntimeError(
            "plan_proposal_invariant_failed:schedule:inferred_minutes_not_uniform"
        )


def resolve_planning_intent(
    *, schedule: list[object], intent: PlanningIntentV1, output_language: str
) -> PlanningResolvedIntentV1:
    page_spans = sorted({
        (content_slice.page_start, content_slice.page_end)
        for item in schedule
        for chapter in getattr(item, "schedule_chapters", [])
        for content_slice in chapter.content_slices
    })
    merged_spans: list[tuple[int, int]] = []
    for start, end in page_spans:
        if merged_spans and start <= merged_spans[-1][1] + 1:
            merged_spans[-1] = (merged_spans[-1][0], max(merged_spans[-1][1], end))
        else:
            merged_spans.append((start, end))
    if not merged_spans:
        raise RuntimeError("planning_resolved_intent_missing:pdf_page_ranges")
    durations = {getattr(item, "duration_minutes", None) for item in schedule}
    if len(durations) != 1 or None in durations:
        raise RuntimeError("planning_resolved_intent_missing:minutes_per_session")
    source_ids = sorted({
        source_id
        for item in schedule
        for chapter in getattr(item, "schedule_chapters", [])
        for source_id in chapter.source_section_ids
    })
    explicit_pages = intent.pdf_page_ranges.value or []
    explicit_outline = intent.outline_targets.value or []
    return PlanningResolvedIntentV1(
        pdf_page_ranges=PlanningResolvedPageRangesV1(
            source=(
                "user_explicit"
                if intent.pdf_page_ranges.status == "user_explicit"
                else "model_inferred"
            ),
            value=(
                list(explicit_pages)
                if intent.pdf_page_ranges.status == "user_explicit"
                else [
                    PlanningPageRangeV1(page_start=start, page_end=end)
                    for start, end in merged_spans
                ]
            ),
        ),
        outline_targets=PlanningResolvedOutlineTargetsV1(
            source=(
                "user_explicit"
                if intent.outline_targets.status == "user_explicit"
                else "model_inferred"
            ),
            value=(
                list(explicit_outline)
                if intent.outline_targets.status == "user_explicit"
                else source_ids
            ),
        ),
        session_count=PlanningResolvedIntegerV1(
            source=(
                "user_explicit"
                if intent.session_count.status == "user_explicit"
                else "model_inferred"
            ),
            value=len(schedule),
        ),
        minutes_per_session=PlanningResolvedIntegerV1(
            source=(
                "user_explicit"
                if intent.minutes_per_session.status == "user_explicit"
                else "model_inferred"
            ),
            value=next(iter(durations)),
        ),
        output_language=PlanningResolvedLanguageV1(
            source=(
                "user_explicit"
                if intent.output_language.status == "user_explicit"
                else "model_inferred"
            ),
            value=output_language,
        ),
    )
