from __future__ import annotations

import base64
import json
from dataclasses import dataclass

import fitz

from app.models.domain import (
    DocumentDebugRecord,
    DocumentSection,
    LearningGoalInput,
    LearningPlanRecord,
    PersonaProfile,
    PlanningQuestionRecord,
    StudyUnitRecord,
)
from app.services.persona_runtime import render_persona_runtime_instruction
from app.services.prompt_loader import load_prompt_template

PLAN_JSON_SCHEMA = (
    "{"
    '"course_title": string, '
    '"overview": string, '
    '"study_chapters": string[], '
    '"today_tasks": string[], '
    '"schedule": ['
    "{"
    '"unit_id": string, '
    '"title": string, '
    '"focus": string, '
    '"activity_type": "learn" | "review"'
    "}"
    "]"
    "}."
)
@dataclass(frozen=True)
class LearningPlanPromptTemplate:
    system_prompt: str
    user_instructions: list[str]


def build_learning_plan_messages(
    *,
    persona: PersonaProfile,
    document_title: str,
    goal: LearningGoalInput,
    study_units: list[StudyUnitRecord],
    debug_report: DocumentDebugRecord | None = None,
    planning_questions: list[PlanningQuestionRecord] | None = None,
    existing_plan: LearningPlanRecord | None = None,
) -> list[dict[str, str]]:
    planning_context = build_learning_plan_context(
        study_units=study_units,
        debug_report=debug_report,
    )
    segmentation_hints = _build_segmentation_hints(
        study_units=study_units,
        detail_map=planning_context["detail_map"],
    )
    prompt_template = load_learning_plan_prompt_template()
    runtime_instruction = render_persona_runtime_instruction(persona)
    user_prompt = {
        "plan_creation_mode": "goal_only" if not goal.document_id.strip() else "document",
        "document_available": debug_report is not None,
        "persona": {
            "id": persona.id,
            "name": persona.name,
            "source": persona.source,
            "summary": persona.summary,
            "relationship": persona.relationship,
            "learner_address": persona.learner_address,
            "system_prompt": runtime_instruction,
            "additional_instruction": persona.system_prompt,
            "runtime_instruction": runtime_instruction,
            "slots": [
                {"kind": slot.kind, "label": slot.label, "content": slot.content}
                for slot in persona.slots
            ],
            "available_emotions": persona.available_emotions,
            "available_actions": persona.available_actions,
            "default_speech_style": persona.default_speech_style,
        },
        "document_title": document_title,
        "learning_goal": {
            "objective": goal.objective,
            "scene_profile_summary": goal.scene_profile_summary,
            "scene_profile": (
                {
                    "scene_id": goal.scene_profile.scene_id,
                    "title": goal.scene_profile.title,
                    "summary": goal.scene_profile.summary,
                    "tags": goal.scene_profile.tags,
                    "selected_path": goal.scene_profile.selected_path,
                    "focus_object_names": goal.scene_profile.focus_object_names,
                    "scene_tree": [node.model_dump(mode="json") for node in goal.scene_profile.scene_tree],
                }
                if goal.scene_profile is not None
                else None
            ),
        },
        "planning_feedback": {
            "answered_questions": [
                _serialize_planning_question(item)
                for item in (planning_questions or [])
                if item.status == "answered" and item.answer.strip()
            ],
            "pending_questions": [
                _serialize_planning_question(item)
                for item in (planning_questions or [])
                if item.status != "answered"
            ],
        },
        "current_plan": _serialize_current_plan(existing_plan),
        "course_outline": planning_context["course_outline"],
        "segmentation_hints": segmentation_hints,
        "study_units": planning_context["study_units"],
        "instructions": prompt_template.user_instructions,
    }
    return [
        {"role": "system", "content": prompt_template.system_prompt},
        {
            "role": "user",
            "content": json.dumps(user_prompt, ensure_ascii=False, indent=2),
        },
    ]

def load_learning_plan_prompt_template() -> LearningPlanPromptTemplate:
    prompt = load_prompt_template("learning_plan_prompt.txt")
    system_prompt = prompt.require("system")
    if not system_prompt:
        raise RuntimeError("learning_plan_prompt_missing_system_section")
    user_instructions = [
        line.strip()
        for line in prompt.optional("user_instructions", "").splitlines()
        if line.strip()
    ]
    return LearningPlanPromptTemplate(
        system_prompt=system_prompt.replace("{{PLAN_JSON_SCHEMA}}", PLAN_JSON_SCHEMA),
        user_instructions=user_instructions,
    )


def build_learning_plan_context(
    *,
    study_units: list[StudyUnitRecord],
    debug_report: DocumentDebugRecord | None = None,
) -> dict[str, object]:
    course_outline = _build_course_outline(debug_report.sections if debug_report else [])
    study_unit_payload = []
    detail_map = build_study_unit_detail_map(
        study_units=study_units,
        debug_report=debug_report,
    )
    for unit in study_units:
        detail = detail_map[unit.id]
        study_unit_payload.append(
            {
                "unit_id": unit.id,
                "title": unit.title,
                "page_start": unit.page_start,
                "page_end": unit.page_end,
                "summary": unit.summary,
                "unit_kind": unit.unit_kind,
                "include_in_plan": unit.include_in_plan,
                "subsection_titles": detail["subsection_titles"],
                "related_section_ids": detail["related_section_ids"],
                "detail_tool_target_id": unit.id,
            }
        )
    return {
        "course_outline": course_outline,
        "study_units": study_unit_payload,
        "detail_map": detail_map,
    }


def _serialize_planning_question(question: PlanningQuestionRecord) -> dict[str, object]:
    return {
        "id": question.id,
        "question": question.question,
        "reason": question.reason,
        "assumptions": list(question.assumptions),
        "answer": question.answer,
        "status": question.status,
    }


def _serialize_current_plan(plan: LearningPlanRecord | None) -> dict[str, object] | None:
    if plan is None:
        return None
    return {
        "course_title": plan.course_title,
        "overview": plan.overview,
        "study_chapters": list(plan.study_chapters),
        "today_tasks": list(plan.today_tasks),
        "schedule": [
            {
                "id": item.id,
                "unit_id": item.unit_id,
                "title": item.title,
                "focus": item.focus,
                "activity_type": item.activity_type,
                "status": item.status,
            }
            for item in plan.schedule
        ],
        "chapter_progress": [
            {
                "unit_id": item.unit_id,
                "title": item.title,
                "objective_fragment": item.objective_fragment,
                "completion_percent": item.completion_percent,
                "status": item.status,
                "schedule_ids": list(item.schedule_ids),
            }
            for item in plan.chapter_progress
        ],
    }


def read_page_range_content(
    *,
    debug_report: DocumentDebugRecord | None,
    page_start: int,
    page_end: int,
    max_chars: int = 4000,
) -> dict[str, object]:
    if debug_report is None:
        return {
            "page_start": page_start,
            "page_end": page_end,
            "chunk_count": 0,
            "content": "",
        }
    matched_chunks = [
        chunk
        for chunk in debug_report.chunks
        if _ranges_overlap(
            start_a=page_start,
            end_a=page_end,
            start_b=chunk.page_start,
            end_b=chunk.page_end,
        )
    ]
    parts: list[str] = []
    total = 0
    for chunk in matched_chunks:
        text = (chunk.content or chunk.text_preview).strip()
        if not text:
            continue
        if parts and total + len(text) > max_chars:
            remaining = max_chars - total
            if remaining > 120:
                parts.append(text[:remaining])
            break
        parts.append(text)
        total += len(text)
        if total >= max_chars:
            break
    return {
        "page_start": page_start,
        "page_end": page_end,
        "chunk_count": len(matched_chunks),
        "content": "\n\n".join(parts),
    }


def read_page_range_images(
    *,
    document_path: str | None,
    page_start: int,
    page_end: int,
    max_images: int = 3,
) -> dict[str, object]:
    if not document_path:
        return {
            "page_start": page_start,
            "page_end": page_end,
            "image_count": 0,
            "images": [],
        }
    requested_pages = list(range(max(1, page_start), max(page_start, page_end) + 1))[: max(1, min(max_images, 4))]
    images: list[dict[str, object]] = []
    try:
        with fitz.open(document_path) as document:
            for page_number in requested_pages:
                page_index = page_number - 1
                if page_index < 0 or page_index >= len(document):
                    continue
                page = document.load_page(page_index)
                pixmap = page.get_pixmap(dpi=144, alpha=False)
                image_bytes = pixmap.tobytes("png")
                images.append(
                    {
                        "page_number": page_number,
                        "mime_type": "image/png",
                        "image_url": f"data:image/png;base64,{base64.b64encode(image_bytes).decode('ascii')}",
                    }
                )
    except Exception:
        images = []
    return {
        "page_start": page_start,
        "page_end": page_end,
        "image_count": len(images),
        "images": images,
    }


def build_study_unit_detail_map(
    *,
    study_units: list[StudyUnitRecord],
    debug_report: DocumentDebugRecord | None = None,
) -> dict[str, dict[str, object]]:
    sections = debug_report.sections if debug_report else []
    chunks = debug_report.chunks if debug_report else []
    detail_map: dict[str, dict[str, object]] = {}
    for unit in study_units:
        related_sections = _related_sections_for_unit(unit=unit, sections=sections)
        related_section_ids = [section.id for section in related_sections]
        subsection_titles = [
            section.title
            for section in related_sections
            if section.level == 2
        ]
        related_chunks = _related_chunks_for_unit(
            unit=unit,
            chunks=chunks,
            related_section_ids=related_section_ids,
        )
        detail_map[unit.id] = {
            "unit_id": unit.id,
            "title": unit.title,
            "page_start": unit.page_start,
            "page_end": unit.page_end,
            "summary": unit.summary,
            "unit_kind": unit.unit_kind,
            "include_in_plan": unit.include_in_plan,
            "related_section_ids": related_section_ids,
            "subsection_titles": subsection_titles,
            "related_sections": [
                {
                    "section_id": section.id,
                    "title": section.title,
                    "level": section.level,
                    "page_start": section.page_start,
                    "page_end": section.page_end,
                }
                for section in related_sections
            ],
            "chunk_count": len(related_chunks),
            "chunk_excerpts": [
                {
                    "chunk_id": chunk.id,
                    "section_id": chunk.section_id,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "char_count": chunk.char_count,
                    "content": (chunk.content or chunk.text_preview)[:900],
                }
                for chunk in related_chunks[:6]
            ],
        }
    return detail_map


def _build_course_outline(sections: list[DocumentSection]) -> list[dict[str, object]]:
    coarse_sections = sorted(
        [section for section in sections if section.level == 1],
        key=lambda section: (section.page_start, section.page_end, section.id),
    )
    fine_sections = sorted(
        [section for section in sections if section.level == 2],
        key=lambda section: (section.page_start, section.page_end, section.id),
    )
    outline: list[dict[str, object]] = []
    for coarse in coarse_sections:
        outline.append(
            {
                "section_id": coarse.id,
                "title": coarse.title,
                "level": coarse.level,
                "page_start": coarse.page_start,
                "page_end": coarse.page_end,
                "children": [
                    {
                        "section_id": fine.id,
                        "title": fine.title,
                        "level": fine.level,
                        "page_start": fine.page_start,
                        "page_end": fine.page_end,
                    }
                    for fine in fine_sections
                    if coarse.page_start <= fine.page_start <= fine.page_end <= coarse.page_end
                ],
            }
        )
    return outline


def _related_sections_for_unit(
    *, unit: StudyUnitRecord, sections: list[DocumentSection]
) -> list[DocumentSection]:
    if not sections:
        return []
    direct_matches = [
        section
        for section in sections
        if section.id in unit.source_section_ids
    ]
    overlapping = [
        section
        for section in sections
        if _ranges_overlap(
            start_a=unit.page_start,
            end_a=unit.page_end,
            start_b=section.page_start,
            end_b=section.page_end,
        )
    ]
    related = direct_matches or overlapping
    return sorted(
        related,
        key=lambda section: (section.page_start, section.level, section.page_end, section.id),
    )


def _related_chunks_for_unit(
    *,
    unit: StudyUnitRecord,
    chunks: list[object],
    related_section_ids: list[str],
):
    if not chunks:
        return []
    if related_section_ids:
        matched = [chunk for chunk in chunks if chunk.section_id in related_section_ids]
        if matched:
            return matched
    return [
        chunk
        for chunk in chunks
        if _ranges_overlap(
            start_a=unit.page_start,
            end_a=unit.page_end,
            start_b=chunk.page_start,
            end_b=chunk.page_end,
        )
    ]


def _ranges_overlap(*, start_a: int, end_a: int, start_b: int, end_b: int) -> bool:
    return max(start_a, start_b) <= min(end_a, end_b)
def _build_segmentation_hints(
    *,
    study_units: list[StudyUnitRecord],
    detail_map: dict[str, dict[str, object]],
) -> dict[str, object]:
    plannable = [unit for unit in study_units if unit.include_in_plan] or study_units
    if not plannable:
        return {
            "is_coarse_grained": False,
            "plannable_unit_count": 0,
            "max_unit_page_span": 0,
            "units_with_subsections": 0,
            "sparse_subsection_unit_count": 0,
            "total_subsection_count": 0,
            "recommend_min_tool_rounds": 1,
            "recommend_detail_tool_call": False,
            "recommend_revise_study_units": False,
            "recommend_continue_tool_calls": False,
            "reason": "no_plannable_units",
        }
    max_span = max((unit.page_end - unit.page_start + 1) for unit in plannable)
    subsection_counts = [
        len(detail_map.get(unit.id, {}).get("subsection_titles", []) or [])
        for unit in plannable
    ]
    units_with_subsections = sum(1 for count in subsection_counts if count > 0)
    sparse_subsection_unit_count = sum(1 for count in subsection_counts if count <= 1)
    total_subsection_count = sum(subsection_counts)
    coarse = len(plannable) <= 1 or (len(plannable) <= 2 and max_span >= 80)
    sparse = sparse_subsection_unit_count >= max(1, len(plannable) // 2)
    should_continue = coarse or sparse or total_subsection_count < len(plannable) * 2
    recommend_min_tool_rounds = 3 if should_continue else 2
    reason_parts: list[str] = []
    if coarse:
        reason_parts.append("plannable_units_too_coarse")
    if sparse:
        reason_parts.append("subsections_too_sparse")
    if total_subsection_count < len(plannable) * 2:
        reason_parts.append("subsection_coverage_thin")
    if not reason_parts:
        reason_parts.append("structure_looks_usable_but_still_verify_details")
    return {
        "is_coarse_grained": coarse,
        "plannable_unit_count": len(plannable),
        "max_unit_page_span": max_span,
        "units_with_subsections": units_with_subsections,
        "sparse_subsection_unit_count": sparse_subsection_unit_count,
        "total_subsection_count": total_subsection_count,
        "recommend_min_tool_rounds": recommend_min_tool_rounds,
        "recommend_detail_tool_call": should_continue,
        "recommend_revise_study_units": coarse or sparse,
        "recommend_continue_tool_calls": should_continue,
        "reason": ", ".join(reason_parts),
    }
