from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable
from uuid import uuid4

from fastapi import HTTPException

from app.models.domain import (
    DocumentDebugRecord,
    DocumentRecord,
    DocumentSection,
    LearningGoalInput,
    LearningPlanRecord,
    PersonaProfile,
    StudyScheduleRecord,
    StudyUnitRecord,
)
from app.services.local_store import LocalJsonStore
from app.services.model_provider import ModelProvider
from app.services.study_arrangement import StudyArrangementService


class LearningPlanService:
    def __init__(
        self,
        store: LocalJsonStore,
        arrangement_service: StudyArrangementService,
        model_provider: ModelProvider,
    ) -> None:
        self.store = store
        self.arrangement_service = arrangement_service
        self.model_provider = model_provider

    def create_plan(
        self,
        *,
        goal: LearningGoalInput,
        document: DocumentRecord,
        persona_name: str,
        persona: PersonaProfile,
        debug_report: DocumentDebugRecord | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
    ) -> LearningPlanRecord:
        if debug_report is not None and not document.study_units:
            study_units = self.arrangement_service.build_study_units(
                document=document,
                debug_report=debug_report,
            )
            document.study_units = study_units
            document.study_unit_count = len(study_units)
            document.sections = [
                DocumentSection(
                    id=unit.id,
                    document_id=unit.document_id,
                    title=unit.title,
                    page_start=unit.page_start,
                    page_end=unit.page_end,
                    level=1,
                )
                for unit in study_units
                if unit.include_in_plan
            ]
        _emit_progress(
            progress_callback,
            "study_units_ready",
            {
                "document_id": document.id,
                "study_unit_count": len(document.study_units),
                "plannable_count": len([unit for unit in document.study_units if unit.include_in_plan]),
            },
        )
        plan = self.arrangement_service.build_plan(
            goal=goal,
            document=document,
            persona_name=persona_name,
            persona=persona,
        )
        _emit_progress(
            progress_callback,
            "heuristic_plan_built",
            {
                "document_id": document.id,
                "today_task_count": len(plan.today_tasks),
                "schedule_count": len(plan.schedule),
                "study_chapter_count": len(plan.study_chapters),
            },
        )
        model_plan = self.model_provider.generate_learning_plan(
            persona=persona,
            document_title=document.title,
            goal=goal,
            study_units=plan.study_units,
            document_path=document.stored_path,
            debug_report=debug_report,
            progress_callback=progress_callback,
        )
        if model_plan.revised_study_units:
            plan.study_units = model_plan.revised_study_units
            document.study_units = model_plan.revised_study_units
            document.study_unit_count = len(model_plan.revised_study_units)
            document.sections = _project_sections_from_study_units(model_plan.revised_study_units)
            if debug_report is not None:
                debug_report.study_units = model_plan.revised_study_units
                self.store.save_item("document_debug", document.id, debug_report)
            self._persist_document(document)
        valid_unit_ids = {unit.id for unit in plan.study_units}
        filtered_schedule = [
            StudyScheduleRecord(
                id=f"schedule-{index + 1}",
                unit_id=item.unit_id,
                title=item.title,
                focus=item.focus,
                activity_type=item.activity_type,
                status="planned",
            )
            for index, item in enumerate(model_plan.schedule)
            if item.unit_id in valid_unit_ids
        ]
        if model_plan.course_title:
            plan.course_title = model_plan.course_title
        if model_plan.overview:
            plan.overview = model_plan.overview
        if model_plan.study_chapters:
            plan.study_chapters = model_plan.study_chapters
        if model_plan.today_tasks:
            plan.today_tasks = model_plan.today_tasks
        if goal.scene_profile is not None:
            plan.scene_profile = goal.scene_profile
        if filtered_schedule:
            plan.schedule = filtered_schedule
        _emit_progress(
            progress_callback,
            "model_plan_applied",
            {
                "document_id": document.id,
                "schedule_count": len(plan.schedule),
                "today_task_count": len(plan.today_tasks),
                "study_chapter_count": len(plan.study_chapters),
            },
        )
        plan.id = f"plan-{uuid4().hex[:10]}"
        plan.created_at = _now()
        if model_plan.debug_trace is not None:
            model_plan.debug_trace.plan_id = plan.id
            self.store.save_item("planning_trace", document.id, model_plan.debug_trace)
        plans = self._load_plans()
        plans.append(plan)
        self._save_plans(plans)
        _emit_progress(
            progress_callback,
            "learning_plan_completed",
            {
                "document_id": document.id,
                "plan_id": plan.id,
                "schedule_count": len(plan.schedule),
            },
        )
        return plan

    def require_plan(self, plan_id: str) -> LearningPlanRecord:
        plans = self._load_plans()
        for plan in plans:
            if plan.id == plan_id:
                return plan
        raise HTTPException(status_code=404, detail="plan_not_found")

    def update_plan(
        self,
        *,
        plan_id: str,
        course_title: str | None = None,
        study_chapters: list[str] | None = None,
    ) -> LearningPlanRecord:
        normalized_title = course_title.strip() if course_title is not None else None
        normalized_chapters = (
            [item.strip() for item in study_chapters if item.strip()]
            if study_chapters is not None
            else None
        )
        if normalized_title is None and normalized_chapters is None:
            raise HTTPException(status_code=422, detail="plan_update_empty")
        if normalized_title is not None and not normalized_title:
            raise HTTPException(status_code=422, detail="course_title_required")
        if normalized_chapters is not None and not normalized_chapters:
            raise HTTPException(status_code=422, detail="study_chapters_required")

        plans = self._load_plans()
        updated_plan: LearningPlanRecord | None = None
        next_plans: list[LearningPlanRecord] = []
        for plan in plans:
            if plan.id != plan_id:
                next_plans.append(plan)
                continue
            updates: dict[str, object] = {}
            if normalized_title is not None:
                updates["course_title"] = normalized_title
            if normalized_chapters is not None:
                updates["study_chapters"] = normalized_chapters
            updated_plan = plan.model_copy(update=updates)
            next_plans.append(updated_plan)

        if updated_plan is None:
            raise HTTPException(status_code=404, detail="plan_not_found")

        self._save_plans(next_plans)
        return updated_plan

    def delete_plan(self, plan_id: str) -> None:
        plans = self._load_plans()
        next_plans = [plan for plan in plans if plan.id != plan_id]
        if len(next_plans) == len(plans):
            raise HTTPException(status_code=404, detail="plan_not_found")
        self._save_plans(next_plans)

    def update_study_unit_title(
        self,
        *,
        document_id: str,
        study_unit_id: str,
        title: str,
    ) -> list[LearningPlanRecord]:
        normalized_title = title.strip()
        if not normalized_title:
            raise HTTPException(status_code=422, detail="study_unit_title_required")

        plans = self._load_plans()
        updated_plans: list[LearningPlanRecord] = []
        next_plans: list[LearningPlanRecord] = []

        for plan in plans:
            if plan.document_id != document_id:
                next_plans.append(plan)
                continue

            did_update = False
            for unit in plan.study_units:
                if unit.id != study_unit_id:
                    continue
                unit.title = normalized_title
                did_update = True
                break

            next_plans.append(plan)
            if did_update:
                updated_plans.append(plan)

        if updated_plans:
            self._save_plans(next_plans)
        return updated_plans

    def list_plans(self) -> list[LearningPlanRecord]:
        return self._load_plans()

    def _load_plans(self) -> list[LearningPlanRecord]:
        return self.store.load_list("plans", LearningPlanRecord)

    def _save_plans(self, plans: list[LearningPlanRecord]) -> None:
        self.store.save_list("plans", plans)

    def _persist_document(self, document: DocumentRecord) -> None:
        documents = self.store.load_list("documents", DocumentRecord)
        updated = [item if item.id != document.id else document for item in documents]
        if not any(item.id == document.id for item in documents):
            updated.append(document)
        self.store.save_list("documents", updated)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _emit_progress(
    callback: Callable[[str, dict[str, object]], None] | None,
    stage: str,
    payload: dict[str, object],
) -> None:
    if callback is None:
        return
    callback(stage, payload)


def _project_sections_from_study_units(study_units: list[StudyUnitRecord]) -> list[DocumentSection]:
    return [
        DocumentSection(
            id=str(unit.id),
            document_id=str(unit.document_id),
            title=str(unit.title),
            page_start=int(unit.page_start),
            page_end=int(unit.page_end),
            level=1,
        )
        for unit in study_units
        if bool(unit.include_in_plan)
    ]
