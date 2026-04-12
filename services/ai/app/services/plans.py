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
    PlanProgressEventRecord,
    PlanProgressSummaryRecord,
    PlanningQuestionRecord,
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
        document: DocumentRecord | None,
        persona_name: str,
        persona: PersonaProfile,
        debug_report: DocumentDebugRecord | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
    ) -> LearningPlanRecord:
        progress_document_id = document.id if document is not None else ""
        if document is not None and debug_report is not None and not document.study_units:
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
        if document is None:
            synthetic_document_id = f"goal-only:{uuid4().hex[:8]}"
            plan = self.arrangement_service.build_goal_only_plan(
                goal=goal,
                base_document_id=synthetic_document_id,
                persona_name=persona_name,
                persona=persona,
            )
            document_title = self._goal_only_document_title(goal)
            document_path = None
            study_unit_count = len(plan.study_units)
            plannable_count = len([unit for unit in plan.study_units if unit.include_in_plan])
        else:
            plan = self.arrangement_service.build_plan(
                goal=goal,
                document=document,
                persona_name=persona_name,
                persona=persona,
            )
            document_title = document.title
            document_path = document.stored_path
            study_unit_count = len(document.study_units)
            plannable_count = len([unit for unit in document.study_units if unit.include_in_plan])
        _emit_progress(
            progress_callback,
            "study_units_ready",
            {
                "document_id": progress_document_id,
                "study_unit_count": study_unit_count,
                "plannable_count": plannable_count,
                "creation_mode": plan.creation_mode,
            },
        )
        _emit_progress(
            progress_callback,
            "heuristic_plan_built",
            {
                "document_id": progress_document_id,
                "today_task_count": len(plan.today_tasks),
                "schedule_count": len(plan.schedule),
                "study_chapter_count": len(plan.study_chapters),
                "creation_mode": plan.creation_mode,
            },
        )
        model_plan = self.model_provider.generate_learning_plan(
            persona=persona,
            document_title=document_title,
            goal=goal,
            study_units=plan.study_units,
            document_path=document_path,
            debug_report=debug_report,
            progress_callback=progress_callback,
        )
        if model_plan.revised_study_units:
            plan.study_units = model_plan.revised_study_units
            if document is not None:
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
                "document_id": progress_document_id,
                "schedule_count": len(plan.schedule),
                "today_task_count": len(plan.today_tasks),
                "study_chapter_count": len(plan.study_chapters),
                "planning_question_count": len(getattr(model_plan, "planning_questions", []) or []),
            },
        )
        plan.id = f"plan-{uuid4().hex[:10]}"
        plan.created_at = _now()
        plan.planning_questions = list(getattr(model_plan, "planning_questions", []) or [])
        plan.progress_summary = self._build_progress_summary(plan.schedule)
        if model_plan.debug_trace is not None:
            model_plan.debug_trace.plan_id = plan.id
            self.store.save_item(
                "planning_trace",
                document.id if document is not None else plan.id,
                model_plan.debug_trace,
            )
        plans = self._load_plans()
        plans.append(self._refresh_plan_derived_fields(plan))
        self._save_plans(plans)
        _emit_progress(
            progress_callback,
            "learning_plan_completed",
            {
                "document_id": progress_document_id,
                "plan_id": plan.id,
                "schedule_count": len(plan.schedule),
                "creation_mode": plan.creation_mode,
                "pending_question_count": len(
                    [item for item in plan.planning_questions if item.status != "answered"]
                ),
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

        refreshed_plan = self._refresh_plan_derived_fields(updated_plan)
        refreshed_plans = [
            refreshed_plan if plan.id == refreshed_plan.id else plan
            for plan in next_plans
        ]
        self._save_plans(refreshed_plans)
        return refreshed_plan

    def update_progress(
        self,
        *,
        plan_id: str,
        schedule_ids: list[str],
        status: str,
        note: str = "",
        actor: str = "user",
        source: str = "ui",
    ) -> LearningPlanRecord:
        normalized_ids = []
        seen_ids: set[str] = set()
        for schedule_id in schedule_ids:
            text = schedule_id.strip()
            if not text or text in seen_ids:
                continue
            seen_ids.add(text)
            normalized_ids.append(text)
        normalized_status = status.strip()
        normalized_note = note.strip()
        if not normalized_ids:
            raise HTTPException(status_code=422, detail="schedule_ids_required")
        if normalized_status not in {"planned", "in_progress", "completed", "blocked", "skipped"}:
            raise HTTPException(status_code=422, detail="invalid_schedule_status")

        plans = self._load_plans()
        updated_plan: LearningPlanRecord | None = None
        next_plans: list[LearningPlanRecord] = []
        for plan in plans:
            if plan.id != plan_id:
                next_plans.append(plan)
                continue
            updated_ids: list[str] = []
            for item in plan.schedule:
                if item.id not in normalized_ids:
                    continue
                item.status = normalized_status
                updated_ids.append(item.id)
            if not updated_ids:
                raise HTTPException(status_code=404, detail="schedule_items_not_found")
            plan.progress_events.append(
                PlanProgressEventRecord(
                    id=f"progress-event-{uuid4().hex[:10]}",
                    actor=actor,
                    source=source,
                    schedule_ids=updated_ids,
                    status=normalized_status,
                    note=normalized_note,
                    created_at=_now(),
                )
            )
            updated_plan = self._refresh_plan_derived_fields(plan)
            next_plans.append(updated_plan)

        if updated_plan is None:
            raise HTTPException(status_code=404, detail="plan_not_found")

        self._save_plans(next_plans)
        return updated_plan

    def answer_planning_question(
        self,
        *,
        plan_id: str,
        question_id: str,
        answer: str,
    ) -> LearningPlanRecord:
        normalized_answer = answer.strip()
        if not normalized_answer:
            raise HTTPException(status_code=422, detail="planning_question_answer_required")

        plans = self._load_plans()
        updated_plan: LearningPlanRecord | None = None
        next_plans: list[LearningPlanRecord] = []
        for plan in plans:
            if plan.id != plan_id:
                next_plans.append(plan)
                continue
            matched_question = False
            for question in plan.planning_questions:
                if question.id != question_id:
                    continue
                question.answer = normalized_answer
                question.status = "answered"
                question.answered_at = _now()
                matched_question = True
                break
            if not matched_question:
                raise HTTPException(status_code=404, detail="planning_question_not_found")
            updated_plan = self._refresh_plan_derived_fields(plan)
            next_plans.append(updated_plan)

        if updated_plan is None:
            raise HTTPException(status_code=404, detail="plan_not_found")

        self._save_plans(next_plans)
        return updated_plan

    def describe_progress(self, plan_id: str) -> dict[str, object]:
        plan = self.require_plan(plan_id)
        pending_questions = [
            question
            for question in plan.planning_questions
            if question.status != "answered"
        ]
        return {
            "ok": True,
            "tool_name": "read_learning_plan_progress",
            "plan_id": plan.id,
            "course_title": plan.course_title,
            "objective": plan.objective,
            "creation_mode": plan.creation_mode,
            "progress_summary": plan.progress_summary.model_dump(mode="json"),
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
            "pending_planning_questions": [
                question.model_dump(mode="json")
                for question in pending_questions
            ],
            "recent_progress_events": [
                event.model_dump(mode="json")
                for event in plan.progress_events[-6:]
            ],
        }

    def find_latest_plan(
        self,
        *,
        document_id: str,
        persona_id: str,
    ) -> LearningPlanRecord | None:
        matches = [
            plan
            for plan in self._load_plans()
            if plan.document_id == document_id and plan.persona_id == persona_id
        ]
        if not matches:
            return None
        return sorted(matches, key=lambda plan: plan.created_at, reverse=True)[0]

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
                updated_plans.append(self._refresh_plan_derived_fields(plan))

        if updated_plans:
            refreshed_map = {plan.id: plan for plan in updated_plans}
            self._save_plans([refreshed_map.get(plan.id, plan) for plan in next_plans])
        return updated_plans

    def list_plans(self) -> list[LearningPlanRecord]:
        return self._load_plans()

    def _load_plans(self) -> list[LearningPlanRecord]:
        plans = self.store.load_list("plans", LearningPlanRecord)
        normalized: list[LearningPlanRecord] = []
        did_change = False
        for plan in plans:
            refreshed = self._refresh_plan_derived_fields(plan)
            normalized.append(refreshed)
            if refreshed.model_dump(mode="json") != plan.model_dump(mode="json"):
                did_change = True
        if did_change:
            self.store.save_list("plans", normalized)
        return normalized

    def _save_plans(self, plans: list[LearningPlanRecord]) -> None:
        self.store.save_list(
            "plans",
            [self._refresh_plan_derived_fields(plan) for plan in plans],
        )

    def _persist_document(self, document: DocumentRecord) -> None:
        documents = self.store.load_list("documents", DocumentRecord)
        updated = [item if item.id != document.id else document for item in documents]
        if not any(item.id == document.id for item in documents):
            updated.append(document)
        self.store.save_list("documents", updated)

    def _goal_only_document_title(self, goal: LearningGoalInput) -> str:
        objective = " ".join((goal.objective or "").split()).strip(" 。.!！?？;；：:")
        if not objective:
            return "目标导向学习计划"
        if len(objective) <= 24:
            return objective
        return f"{objective[:24].rstrip()}…"

    def _build_progress_summary(
        self,
        schedule: list[StudyScheduleRecord],
    ) -> PlanProgressSummaryRecord:
        total = len(schedule)
        completed = sum(1 for item in schedule if item.status == "completed")
        in_progress = sum(1 for item in schedule if item.status == "in_progress")
        blocked = sum(1 for item in schedule if item.status == "blocked")
        pending = total - completed - in_progress - blocked
        completion_percent = int(round((completed / total) * 100)) if total else 0
        return PlanProgressSummaryRecord(
            total_schedule_count=total,
            completed_schedule_count=completed,
            in_progress_schedule_count=in_progress,
            pending_schedule_count=max(0, pending),
            blocked_schedule_count=blocked,
            completion_percent=completion_percent,
        )

    def _refresh_plan_derived_fields(self, plan: LearningPlanRecord) -> LearningPlanRecord:
        creation_mode = plan.creation_mode or ("goal_only" if not plan.document_id else "document")
        return plan.model_copy(
            update={
                "creation_mode": creation_mode,
                "progress_summary": self._build_progress_summary(plan.schedule),
            }
        )


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
