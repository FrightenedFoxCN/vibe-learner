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
        )
        _emit_progress(
            progress_callback,
            "heuristic_plan_built",
            {
                "document_id": document.id,
                "today_task_count": len(plan.today_tasks),
                "schedule_count": len(plan.schedule),
                "weekly_focus_count": len(plan.weekly_focus),
            },
        )
        model_plan = self.model_provider.generate_learning_plan(
            persona=persona,
            document_title=document.title,
            goal=goal,
            study_units=plan.study_units,
            debug_report=debug_report,
            progress_callback=progress_callback,
        )
        valid_unit_ids = {unit.id for unit in plan.study_units}
        filtered_schedule = [
            StudyScheduleRecord(
                id=f"schedule-{index + 1}",
                unit_id=item.unit_id,
                title=item.title,
                scheduled_date=item.scheduled_date,
                focus=item.focus,
                activity_type=item.activity_type,
                estimated_minutes=item.estimated_minutes,
                status="planned",
            )
            for index, item in enumerate(model_plan.schedule)
            if item.unit_id in valid_unit_ids
        ]
        if model_plan.overview:
            plan.overview = model_plan.overview
        if model_plan.weekly_focus:
            plan.weekly_focus = model_plan.weekly_focus
        if model_plan.today_tasks:
            plan.today_tasks = model_plan.today_tasks
        if filtered_schedule:
            plan.schedule = filtered_schedule
        _emit_progress(
            progress_callback,
            "model_plan_applied",
            {
                "document_id": document.id,
                "schedule_count": len(plan.schedule),
                "today_task_count": len(plan.today_tasks),
                "weekly_focus_count": len(plan.weekly_focus),
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

    def list_plans(self) -> list[LearningPlanRecord]:
        return self._load_plans()

    def _load_plans(self) -> list[LearningPlanRecord]:
        return self.store.load_list("plans", LearningPlanRecord)

    def _save_plans(self, plans: list[LearningPlanRecord]) -> None:
        self.store.save_list("plans", plans)


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
