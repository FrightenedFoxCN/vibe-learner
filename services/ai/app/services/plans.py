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
    PlanGenerationTraceRecord,
    PlanProgressEventRecord,
    PlanProgressSummaryRecord,
    PlanningQuestionRecord,
    PersonaProfile,
    ScheduleChapterContentSliceRecord,
    ScheduleChapterRecord,
    StudyScheduleRecord,
    StudyUnitProgressRecord,
    StudyUnitRecord,
)
from app.models.planning import PlanScheduleChapterProposalV1
from app.models.planning import (
    LearningPlanOperationRecord,
    LearningPlanOperationRequestV1,
    LearningPlanOperationStatus,
    planning_projection_digest,
)
from app.persistence.learning_plan_operation_repository import (
    LearningPlanAdmissionRace,
    LearningPlanAlreadyActive,
    LearningPlanDocumentNotFound,
    LearningPlanOperationError,
    LearningPlanOperationRepository,
    LearningPlanProjectionIdentityMismatch,
    LearningPlanProjectionPrerequisiteMissing,
    LearningPlanRequestConflict,
    LearningPlanStaleDocument,
    LearningPlanTerminalReplayBlocked,
)
from app.services.local_store import LocalJsonStore
from app.services.model_provider import ModelProvider
from app.services.stream_interrupts import StreamInterruptedError
from app.services.study_arrangement import StudyArrangementService


class LearningPlanService:
    def __init__(
        self,
        store: LocalJsonStore,
        arrangement_service: StudyArrangementService,
        model_provider: ModelProvider,
        operation_repository: LearningPlanOperationRepository | None = None,
    ) -> None:
        self.store = store
        self.arrangement_service = arrangement_service
        self.model_provider = model_provider
        self.operation_repository = operation_repository or LearningPlanOperationRepository(
            store.database
        )

    def create_plan(
        self,
        *,
        goal: LearningGoalInput,
        document: DocumentRecord | None,
        persona_name: str,
        persona: PersonaProfile,
        debug_report: DocumentDebugRecord | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
        interrupt_check: Callable[[], None] | None = None,
        operation_admitted_callback: Callable[[str], None] | None = None,
    ) -> LearningPlanRecord:
        if document is not None and document.debug_ready and debug_report is None:
            debug_report = self.store.load_item(
                "document_debug",
                document.id,
                DocumentDebugRecord,
            )
        client_request_id = str(getattr(goal, "client_request_id", "") or "").strip()
        if not client_request_id:
            client_request_id = f"plan-request-{uuid4().hex}"
        expected_document_updated_at = str(
            getattr(goal, "expected_document_updated_at", "") or ""
        ).strip()
        if document is not None and not expected_document_updated_at:
            expected_document_updated_at = document.updated_at
        request = LearningPlanOperationRequestV1(
            client_request_id=client_request_id,
            document_id=document.id if document is not None else "",
            persona_id=goal.persona_id,
            objective=goal.objective,
            scene_profile_summary=goal.scene_profile_summary,
            scene_profile=goal.scene_profile,
            expected_document_updated_at=expected_document_updated_at,
        )
        try:
            operation, duplicate = self.operation_repository.admit(request=request)
        except LearningPlanDocumentNotFound as exc:
            raise HTTPException(status_code=404, detail="document_not_found") from exc
        except LearningPlanStaleDocument as exc:
            raise HTTPException(status_code=409, detail="learning_plan_stale_document") from exc
        except (
            LearningPlanAlreadyActive,
            LearningPlanAdmissionRace,
        ) as exc:
            raise HTTPException(status_code=409, detail="learning_plan_operation_active") from exc
        except LearningPlanRequestConflict as exc:
            raise HTTPException(status_code=409, detail="learning_plan_request_conflict") from exc
        except LearningPlanTerminalReplayBlocked as exc:
            raise HTTPException(
                status_code=409,
                detail=f"learning_plan_operation_{exc.status}",
            ) from exc
        except LearningPlanProjectionPrerequisiteMissing as exc:
            raise HTTPException(
                status_code=409,
                detail="learning_plan_projection_prerequisite_missing",
            ) from exc

        if duplicate:
            if operation_admitted_callback is not None:
                operation_admitted_callback(operation.operation_id)
            projection = operation.committed_projection
            if projection is None:
                raise RuntimeError("learning_plan_committed_projection_missing")
            return projection.plan.model_copy(deep=True)

        provider_started = False
        candidate_built = False

        def mark_provider_started() -> None:
            nonlocal provider_started
            self.operation_repository.mark_provider_started(
                operation_id=operation.operation_id
            )
            provider_started = True

        try:
            if operation_admitted_callback is not None:
                operation_admitted_callback(operation.operation_id)
            if document is not None and planning_projection_digest(
                document.model_dump(mode="json")
            ) != operation.base_document_digest:
                raise LearningPlanProjectionIdentityMismatch(
                    operation.operation_id,
                    "input_document_snapshot",
                )
            if debug_report is not None and planning_projection_digest(
                debug_report.model_dump(mode="json")
            ) != operation.base_debug_digest:
                raise LearningPlanProjectionIdentityMismatch(
                    operation.operation_id,
                    "input_debug_snapshot",
                )
            plan, projected_document, projected_debug, trace = (
                self._build_plan_candidate(
                    goal=goal,
                    document=document,
                    persona_name=persona_name,
                    persona=persona,
                    debug_report=debug_report,
                    progress_callback=progress_callback,
                    interrupt_check=interrupt_check,
                    provider_start_callback=mark_provider_started,
                )
            )
            candidate_built = True
            self.operation_repository.commit_success(
                operation_id=operation.operation_id,
                plan=plan,
                document=projected_document,
                debug_report=projected_debug,
                trace=trace,
            )
        except StreamInterruptedError:
            self.operation_repository.mark_terminal(
                operation_id=operation.operation_id,
                status=LearningPlanOperationStatus.INTERRUPTED,
                error_code="learning_plan_interrupted",
            )
            raise
        except Exception as exc:
            self.operation_repository.mark_terminal(
                operation_id=operation.operation_id,
                status=_learning_plan_failure_status(
                    exc,
                    provider_started=provider_started,
                    candidate_built=candidate_built,
                ),
                error_code=_learning_plan_error_code(exc),
            )
            raise

        self.store.mirror_learning_plan_projection(
            plan=plan,
            document=projected_document,
            debug_report=projected_debug,
            trace=trace,
        )
        try:
            _emit_progress(
                progress_callback,
                "learning_plan_completed",
                {
                    "document_id": document.id if document is not None else "",
                    "plan_id": plan.id,
                    "schedule_count": len(plan.schedule),
                    "creation_mode": plan.creation_mode,
                    "pending_question_count": len(
                        [
                            item
                            for item in plan.planning_questions
                            if item.status != "answered"
                        ]
                    ),
                },
            )
        except Exception:
            pass
        return plan

    def _build_plan_candidate(
        self,
        *,
        goal: LearningGoalInput,
        document: DocumentRecord | None,
        persona_name: str,
        persona: PersonaProfile,
        debug_report: DocumentDebugRecord | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
        interrupt_check: Callable[[], None] | None = None,
        provider_start_callback: Callable[[], None] | None = None,
    ) -> tuple[
        LearningPlanRecord,
        DocumentRecord | None,
        DocumentDebugRecord | None,
        PlanGenerationTraceRecord | None,
    ]:
        _call_interrupt(interrupt_check)
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
                debug_report=debug_report,
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
                "schedule_chapter_count": sum(len(item.schedule_chapters) for item in plan.schedule),
                "creation_mode": plan.creation_mode,
            },
        )
        if provider_start_callback is not None:
            provider_start_callback()
        model_plan = self.model_provider.generate_learning_plan(
            persona=persona,
            document_title=document_title,
            goal=goal,
            study_units=plan.study_units,
            document_path=document_path,
            debug_report=debug_report,
            progress_callback=progress_callback,
            interrupt_check=interrupt_check,
        )
        _call_interrupt(interrupt_check)
        if model_plan.revised_study_units:
            plan.study_units = model_plan.revised_study_units
            if document is not None:
                document.study_units = model_plan.revised_study_units
                document.study_unit_count = len(model_plan.revised_study_units)
                document.sections = _project_sections_from_study_units(model_plan.revised_study_units)
                document.updated_at = _now()
                if debug_report is not None:
                    debug_report.study_units = model_plan.revised_study_units
        unit_by_id = {unit.id: unit for unit in plan.study_units}
        filtered_schedule: list[StudyScheduleRecord] = []
        seen_unit_ids: set[str] = set()
        for index, item in enumerate(model_plan.schedule):
            if item.unit_id in seen_unit_ids:
                raise RuntimeError(
                    f"plan_proposal_invariant_failed:schedule.{index}.unit_id:duplicate_ref"
                )
            seen_unit_ids.add(item.unit_id)
            unit = unit_by_id.get(item.unit_id)
            if unit is None:
                raise RuntimeError(
                    f"plan_proposal_invariant_failed:schedule.{index}.unit_id:unknown_ref"
                )
            filtered_schedule.append(
                self._build_schedule_record(index=index, item=item, unit=unit)
            )
        if model_plan.course_title:
            plan.course_title = model_plan.course_title
        if model_plan.overview:
            plan.overview = model_plan.overview
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
                "schedule_chapter_count": sum(len(item.schedule_chapters) for item in plan.schedule),
                "planning_question_count": len(getattr(model_plan, "planning_questions", []) or []),
            },
        )
        plan.id = f"plan-{uuid4().hex[:10]}"
        plan.created_at = _now()
        plan.planning_questions = list(getattr(model_plan, "planning_questions", []) or [])
        plan.progress_summary = self._build_progress_summary(plan.schedule)
        if model_plan.debug_trace is not None:
            model_plan.debug_trace.plan_id = plan.id
        plan = self._refresh_plan_derived_fields(plan)
        return plan, document, debug_report, model_plan.debug_trace

    def recover_abandoned_operations(self) -> int:
        recovered = self.operation_repository.recover_abandoned()
        return len(recovered)

    def require_operation(
        self,
        *,
        client_request_id: str,
    ) -> LearningPlanOperationRecord:
        operation = self.operation_repository.get_by_client_request_id(
            client_request_id=client_request_id,
            validate_current=False,
        )
        if operation is None:
            raise HTTPException(
                status_code=404,
                detail="learning_plan_operation_not_found",
            )
        return operation

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
    ) -> LearningPlanRecord:
        normalized_title = course_title.strip() if course_title is not None else None
        if normalized_title is None:
            raise HTTPException(status_code=422, detail="plan_update_empty")
        if normalized_title is not None and not normalized_title:
            raise HTTPException(status_code=422, detail="course_title_required")

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
        return self._revise_answered_plan(updated_plan)

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
            "study_unit_progress": [
                item.model_dump(mode="json")
                for item in plan.study_unit_progress
            ],
            "schedule": [
                {
                    "id": item.id,
                    "unit_id": item.unit_id,
                    "title": item.title,
                    "focus": item.focus,
                    "activity_type": item.activity_type,
                    "status": item.status,
                    "schedule_chapters": [
                        chapter.model_dump(mode="json")
                        for chapter in item.schedule_chapters
                    ],
                }
                for item in plan.schedule
            ],
            "pending_planning_questions": [
                question.model_dump(mode="json")
                for question in pending_questions
            ],
            "answered_planning_questions": [
                question.model_dump(mode="json")
                for question in plan.planning_questions
                if question.status == "answered"
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

    def _revise_answered_plan(self, plan: LearningPlanRecord) -> LearningPlanRecord:
        persona = self._load_persona(plan.persona_id)
        if persona is None:
            return self._refresh_plan_derived_fields(plan)

        document = self._load_document(plan.document_id) if plan.document_id else None
        debug_report = (
            self.store.load_item("document_debug", document.id, DocumentDebugRecord)
            if document is not None
            else None
        )
        goal = LearningGoalInput(
            document_id=plan.document_id,
            persona_id=plan.persona_id,
            objective=plan.objective,
            scene_profile_summary=plan.scene_profile_summary,
            scene_profile=plan.scene_profile,
        )
        document_title = document.title if document is not None else self._goal_only_document_title(goal)

        try:
            model_plan = self.model_provider.generate_learning_plan(
                persona=persona,
                document_title=document_title,
                goal=goal,
                study_units=plan.study_units,
                document_path=document.stored_path if document is not None else None,
                debug_report=debug_report,
                planning_questions=plan.planning_questions,
                existing_plan=plan,
            )
        except RuntimeError:
            return self._refresh_plan_derived_fields(plan)

        revised_plan = self._merge_model_plan(
            plan=plan,
            model_plan=model_plan,
            document=document,
            debug_report=debug_report,
        )
        if model_plan.debug_trace is not None:
            model_plan.debug_trace.plan_id = revised_plan.id
            self.store.save_item(
                "planning_trace",
                document.id if document is not None else revised_plan.id,
                model_plan.debug_trace,
            )
        persisted_plans = [
            revised_plan if item.id == revised_plan.id else item
            for item in self._load_plans()
        ]
        self._save_plans(persisted_plans)
        return revised_plan

    def _merge_model_plan(
        self,
        *,
        plan: LearningPlanRecord,
        model_plan,
        document: DocumentRecord | None,
        debug_report: DocumentDebugRecord | None,
    ) -> LearningPlanRecord:
        next_plan = plan.model_copy(deep=True)
        if model_plan.revised_study_units:
            next_plan.study_units = model_plan.revised_study_units
            if document is not None:
                document.study_units = model_plan.revised_study_units
                document.study_unit_count = len(model_plan.revised_study_units)
                document.sections = _project_sections_from_study_units(model_plan.revised_study_units)
                if debug_report is not None:
                    debug_report.study_units = model_plan.revised_study_units
                    self.store.save_item("document_debug", document.id, debug_report)
                self._persist_document(document)

        valid_unit_ids = {unit.id for unit in next_plan.study_units}
        filtered_schedule = [
            self._build_schedule_record(
                index=index,
                item=item,
                unit=unit,
            )
            for index, item in enumerate(model_plan.schedule)
            if (unit := next((entry for entry in next_plan.study_units if entry.id == item.unit_id), None)) is not None
        ]
        if filtered_schedule:
            next_plan.schedule = self._carry_over_schedule_statuses(
                previous_schedule=next_plan.schedule,
                next_schedule=filtered_schedule,
            )
        if model_plan.course_title:
            next_plan.course_title = model_plan.course_title
        if model_plan.overview:
            next_plan.overview = model_plan.overview
        if model_plan.today_tasks:
            next_plan.today_tasks = model_plan.today_tasks
        if model_plan.planning_questions is not None:
            next_plan.planning_questions = list(model_plan.planning_questions)
        return self._refresh_plan_derived_fields(next_plan)

    def _carry_over_schedule_statuses(
        self,
        *,
        previous_schedule: list[StudyScheduleRecord],
        next_schedule: list[StudyScheduleRecord],
    ) -> list[StudyScheduleRecord]:
        buckets: dict[tuple[str, str], list[StudyScheduleRecord]] = {}
        for item in previous_schedule:
            key = (item.unit_id, item.activity_type)
            buckets.setdefault(key, []).append(item)

        next_bucket_index: dict[tuple[str, str], int] = {}
        result: list[StudyScheduleRecord] = []
        for item in next_schedule:
            key = (item.unit_id, item.activity_type)
            index = next_bucket_index.get(key, 0)
            previous_items = buckets.get(key, [])
            matched = previous_items[index] if index < len(previous_items) else None
            next_bucket_index[key] = index + 1
            result.append(
                item.model_copy(
                    update={
                        "status": matched.status if matched is not None else item.status,
                        "schedule_chapters": item.schedule_chapters,
                    }
                )
            )
        return result

    def _load_document(self, document_id: str) -> DocumentRecord | None:
        for document in self.store.load_list("documents", DocumentRecord):
            if document.id == document_id:
                return document
        return None

    def _load_persona(self, persona_id: str) -> PersonaProfile | None:
        for persona in self.store.load_list("personas", PersonaProfile):
            if persona.id == persona_id:
                return persona
        return None

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

    def _build_study_unit_progress(self, plan: LearningPlanRecord) -> list[StudyUnitProgressRecord]:
        plannable_units = [unit for unit in plan.study_units if unit.include_in_plan] or list(plan.study_units)
        result = []
        for unit in plannable_units:
            related_schedule = [item for item in plan.schedule if item.unit_id == unit.id]
            total = len(related_schedule)
            completed = sum(1 for item in related_schedule if item.status == "completed")
            in_progress = sum(1 for item in related_schedule if item.status == "in_progress")
            blocked = sum(1 for item in related_schedule if item.status == "blocked")
            pending = max(0, total - completed - in_progress - blocked)
            if total and completed == total:
                status = "completed"
            elif in_progress > 0 or completed > 0:
                status = "in_progress"
            elif blocked > 0 and pending == 0:
                status = "blocked"
            else:
                status = "planned"
            objective_fragment = ""
            for item in related_schedule:
                focus = item.focus.strip()
                if focus:
                    objective_fragment = focus
                    break
            if not objective_fragment:
                objective_fragment = unit.summary.strip()
            if not objective_fragment:
                objective_fragment = self._goal_only_document_title(
                    LearningGoalInput(
                        document_id=plan.document_id,
                        persona_id=plan.persona_id,
                        objective=plan.objective,
                    )
                )
            title = (
                unit.title.strip()
                or next(
                    (
                        chapter.title.strip()
                        for item in related_schedule
                        for chapter in item.schedule_chapters
                        if chapter.title.strip()
                    ),
                    "",
                )
                or unit.id
            )
            completion_percent = int(round((completed / total) * 100)) if total else 0
            result.append(
                StudyUnitProgressRecord(
                    unit_id=unit.id,
                    title=title,
                    objective_fragment=objective_fragment,
                    schedule_ids=[item.id for item in related_schedule],
                    total_schedule_count=total,
                    completed_schedule_count=completed,
                    in_progress_schedule_count=in_progress,
                    pending_schedule_count=pending,
                    blocked_schedule_count=blocked,
                    completion_percent=completion_percent,
                    status=status,
                )
            )
        return result

    def _refresh_plan_derived_fields(self, plan: LearningPlanRecord) -> LearningPlanRecord:
        creation_mode = plan.creation_mode or ("goal_only" if not plan.document_id else "document")
        return plan.model_copy(
            update={
                "creation_mode": creation_mode,
                "progress_summary": self._build_progress_summary(plan.schedule),
                "study_unit_progress": self._build_study_unit_progress(plan),
            }
        )

    def _build_schedule_record(
        self,
        *,
        index: int,
        item,
        unit: StudyUnitRecord,
    ) -> StudyScheduleRecord:
        schedule_chapters = self._normalize_schedule_chapters(
            raw_schedule_chapters=getattr(item, "schedule_chapters", None),
            unit=unit,
        )
        return StudyScheduleRecord(
            id=f"schedule-{index + 1}",
            unit_id=item.unit_id,
            title=item.title,
            focus=item.focus,
            activity_type=item.activity_type,
            status="planned",
            schedule_chapters=schedule_chapters,
        )

    def _normalize_schedule_chapters(
        self,
        *,
        raw_schedule_chapters: (
            list[ScheduleChapterRecord]
            | list[PlanScheduleChapterProposalV1]
            | list[dict[str, object]]
            | None
        ),
        unit: StudyUnitRecord,
    ) -> list[ScheduleChapterRecord]:
        chapters = list(raw_schedule_chapters or [])
        normalized: list[ScheduleChapterRecord] = []
        previous_anchor_start = 0
        for index, raw_chapter in enumerate(chapters, start=1):
            raw_payload = (
                raw_chapter.model_dump(mode="python")
                if hasattr(raw_chapter, "model_dump")
                else raw_chapter
            )
            if not isinstance(raw_payload, dict):
                raise RuntimeError(
                    f"plan_proposal_invariant_failed:schedule_chapters.{index - 1}:not_object"
                )
            raw_payload = {key: value for key, value in raw_payload.items() if key != "id"}
            chapter = PlanScheduleChapterProposalV1.model_validate(raw_payload)
            validated_chapter = self._validate_schedule_chapter(
                chapter=chapter,
                unit=unit,
                index=index,
                previous_anchor_start=previous_anchor_start,
            )
            previous_anchor_start = validated_chapter.anchor_page_start
            normalized.append(validated_chapter)
        if normalized:
            return normalized
        normalized_sources = [str(item).strip() for item in unit.source_section_ids if str(item).strip()]
        return [
            ScheduleChapterRecord(
                id=f"{unit.id}:schedule-chapter:1",
                title=unit.title,
                anchor_page_start=unit.page_start,
                anchor_page_end=unit.page_end,
                source_section_ids=normalized_sources,
                content_slices=[
                    ScheduleChapterContentSliceRecord(
                        page_start=unit.page_start,
                        page_end=unit.page_end,
                        source_section_ids=normalized_sources,
                    )
                ],
            )
        ]

    def _validate_schedule_chapter(
        self,
        *,
        chapter: PlanScheduleChapterProposalV1,
        unit: StudyUnitRecord,
        index: int,
        previous_anchor_start: int,
    ) -> ScheduleChapterRecord:
        if chapter.anchor_page_start < unit.page_start or chapter.anchor_page_end > unit.page_end:
            raise RuntimeError(
                f"plan_proposal_invariant_failed:schedule_chapters.{index - 1}.anchor_page_start:outside_unit"
            )
        if chapter.anchor_page_start < previous_anchor_start:
            raise RuntimeError(
                f"plan_proposal_invariant_failed:schedule_chapters.{index - 1}.anchor_page_start:not_ordered"
            )
        allowed_sources = set(unit.source_section_ids)
        if any(source_id not in allowed_sources for source_id in chapter.source_section_ids):
            raise RuntimeError(
                f"plan_proposal_invariant_failed:schedule_chapters.{index - 1}.source_section_ids:unknown_ref"
            )
        next_slices: list[ScheduleChapterContentSliceRecord] = []
        previous_slice_start = 0
        for slice_index, raw_slice in enumerate(chapter.content_slices):
            if (
                raw_slice.page_start < chapter.anchor_page_start
                or raw_slice.page_end > chapter.anchor_page_end
            ):
                raise RuntimeError(
                    "plan_proposal_invariant_failed:"
                    f"schedule_chapters.{index - 1}.content_slices.{slice_index}:outside_chapter"
                )
            if raw_slice.page_start < previous_slice_start:
                raise RuntimeError(
                    "plan_proposal_invariant_failed:"
                    f"schedule_chapters.{index - 1}.content_slices.{slice_index}:not_ordered"
                )
            if any(source_id not in allowed_sources for source_id in raw_slice.source_section_ids):
                raise RuntimeError(
                    "plan_proposal_invariant_failed:"
                    f"schedule_chapters.{index - 1}.content_slices.{slice_index}.source_section_ids:unknown_ref"
                )
            previous_slice_start = raw_slice.page_start
            next_slices.append(
                ScheduleChapterContentSliceRecord(
                    page_start=raw_slice.page_start,
                    page_end=raw_slice.page_end,
                    source_section_ids=list(raw_slice.source_section_ids),
                )
            )
        return ScheduleChapterRecord(
            id=f"{unit.id}:schedule-chapter:{index}",
            title=chapter.title,
            anchor_page_start=chapter.anchor_page_start,
            anchor_page_end=chapter.anchor_page_end,
            source_section_ids=list(chapter.source_section_ids),
            content_slices=next_slices,
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


def _call_interrupt(callback: Callable[[], None] | None) -> None:
    if callback is None:
        return
    callback()


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


def _learning_plan_failure_status(
    exc: Exception,
    *,
    provider_started: bool,
    candidate_built: bool,
) -> LearningPlanOperationStatus:
    if not provider_started or candidate_built:
        return LearningPlanOperationStatus.NOT_COMMITTED
    if isinstance(exc, LearningPlanOperationError):
        return LearningPlanOperationStatus.NOT_COMMITTED
    detail = str(exc)
    known_not_committed_prefixes = (
        "plan_model_invalid_",
        "plan_model_content_filter",
        "plan_model_tool_loop_exhausted",
        "plan_proposal_",
        "planning_tool_",
        "learning_plan_read_back_failed:",
    )
    if detail.startswith(known_not_committed_prefixes):
        return LearningPlanOperationStatus.NOT_COMMITTED
    return LearningPlanOperationStatus.UNCERTAIN


def _learning_plan_error_code(exc: Exception) -> str:
    raw = str(exc).strip() or type(exc).__name__
    normalized = "".join(
        character if character.isalnum() else "_"
        for character in raw.lower()
    ).strip("_")
    return f"learning_plan_{normalized or 'failed'}"[:128]
