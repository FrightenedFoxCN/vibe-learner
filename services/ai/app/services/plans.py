from __future__ import annotations

from datetime import datetime, timezone
import json
from typing import Callable
from uuid import uuid4

from fastapi import HTTPException

from app.models.domain import (
    DocumentDebugRecord,
    DocumentRecord,
    DocumentSection,
    LearningGoalInput,
    VersionedLearningPlanRecord as LearningPlanRecord,
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
from app.models.harness import canonical_harness_digest
from app.models.planning import PlanScheduleChapterProposalV1
from app.models.harness_operation import HarnessDomainOperationKind
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
from app.models.plan_progress import PlanProgressProjector
from app.persistence.learning_plan_repository import LearningPlanRepository
from app.services.local_store import LocalJsonStore
from app.services.provider_capabilities import PlanningModelCapability
from app.services.stream_interrupts import StreamInterruptedError
from app.services.study_arrangement import StudyArrangementService
from app.services.harness_broad_adoption import (
    HarnessProposalRuntimeService,
)
from app.models.planning_runtime import (
    LearningPlanInputManifest,
    LearningPlanRuntimeOutputV1,
    PlanningToolExecutionEvidenceV1,
    PlanningToolExecutionInputManifest,
)
from app.services.harness_runtime import HarnessOperationRuntime, HarnessRuntimePreparedOutput


class LearningPlanService:
    def __init__(
        self,
        store: LocalJsonStore,
        arrangement_service: StudyArrangementService,
        model_provider: PlanningModelCapability,
        operation_repository: LearningPlanOperationRepository | None = None,
        harness_service: HarnessProposalRuntimeService | None = None,
    ) -> None:
        self.store = store
        self.repository = LearningPlanRepository(store.database)
        self.arrangement_service = arrangement_service
        self.model_provider = model_provider
        self.operation_repository = operation_repository or LearningPlanOperationRepository(
            store.database
        )
        self.harness_service = harness_service or HarnessProposalRuntimeService.from_database(
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
            if operation.status != LearningPlanOperationStatus.COMMITTED:
                raise HTTPException(
                    status_code=409,
                    detail=f"learning_plan_operation_{operation.status.value}",
                )
            if operation_admitted_callback is not None:
                operation_admitted_callback(operation.operation_id)
            projection = operation.committed_projection
            if projection is None:
                raise RuntimeError("learning_plan_committed_projection_missing")
            return projection.plan.model_copy(deep=True)

        provider_started = False
        candidate_built = False
        runtime_prepared: HarnessRuntimePreparedOutput | None = None
        harness_runtime: HarnessOperationRuntime | None = None

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
            operation_binding = self.operation_repository.harness_operations.require_domain(
                domain_operation_kind=HarnessDomainOperationKind.LEARNING_PLAN_GENERATION,
                domain_operation_id=operation.operation_id,
            )

            def generate_plan(
                protected: dict[str, object],
            ) -> LearningPlanRuntimeOutputV1:
                protected_goal = LearningGoalInput.model_validate(protected["goal"])
                protected_document = (
                    DocumentRecord.model_validate(protected["document"])
                    if protected.get("document") is not None
                    else None
                )
                protected_debug = (
                    DocumentDebugRecord.model_validate(protected["debug_report"])
                    if protected.get("debug_report") is not None
                    else None
                )
                protected_persona = PersonaProfile.model_validate(protected["persona"])
                result = self._build_plan_candidate(
                    goal=protected_goal,
                    document=protected_document,
                    persona_name=str(protected["persona_name"]),
                    persona=protected_persona,
                    debug_report=protected_debug,
                    progress_callback=progress_callback,
                    interrupt_check=interrupt_check,
                    provider_start_callback=mark_provider_started,
                )
                return LearningPlanRuntimeOutputV1(
                    plan=result[0],
                    document=result[1],
                    debug_report=result[2],
                    trace=result[3],
                )

            runtime_prepared, harness_runtime = self.harness_service.prepare_plan(
                operation_binding=operation_binding,
                manifest=LearningPlanInputManifest(
                    client_request_id=client_request_id,
                    document_id=document.id if document is not None else "",
                    persona_id=persona.id,
                    creation_mode="document" if document is not None else "goal_only",
                ),
                protected_input={
                    "goal": goal.model_dump(mode="json", exclude_none=False),
                    "document": (
                        document.model_dump(mode="json", exclude_none=False)
                        if document is not None
                        else None
                    ),
                    "debug_report": (
                        debug_report.model_dump(mode="json", exclude_none=False)
                        if debug_report is not None
                        else None
                    ),
                    "persona_name": persona_name,
                    "persona": persona.model_dump(mode="json", exclude_none=False),
                },
                generate=generate_plan,
            )
            runtime_output = LearningPlanRuntimeOutputV1.model_validate(
                runtime_prepared.output
            )
            plan, projected_document, projected_debug, trace = (
                runtime_output.plan,
                runtime_output.document,
                runtime_output.debug_report,
                runtime_output.trace,
            )
            candidate_built = True
            if trace is not None:
                tool_calls = [
                    item
                    for round_record in trace.rounds
                    for item in round_record.tool_calls
                ]
                for tool_index, tool_call in enumerate(tool_calls, start=1):
                    tool_duration_ms = next(
                        (
                            round_record.elapsed_ms
                            for round_record in trace.rounds
                            if tool_call in round_record.tool_calls
                        ),
                        0,
                    )
                    tool_call_id = tool_call.tool_call_id or "unattributed"
                    try:
                        result_payload = json.loads(tool_call.result_json)
                    except (TypeError, json.JSONDecodeError):
                        result_payload = {"raw": tool_call.result_json}
                    result_contract_version = (
                        tool_call.result_contract_version or "planning-tool-error-v1"
                    )
                    evidence = PlanningToolExecutionEvidenceV1(
                        tool_name=tool_call.tool_name or "unattributed",
                        tool_call_id=tool_call_id,
                        result_contract_version=result_contract_version,
                        arguments_digest=canonical_harness_digest(tool_call.arguments_json),
                        result_digest=canonical_harness_digest(result_payload),
                        outcome=(
                            "failed"
                            if isinstance(result_payload, dict)
                            and result_payload.get("ok") is False
                            else "validated"
                        ),
                        duration_ms=tool_duration_ms,
                    )
                    self.harness_service.emit_planning_tool_evidence(
                        operation_binding=operation_binding,
                        parent_trace_id=runtime_prepared.execution.trace_id,
                        trace_slot=tool_index,
                        input_manifest=PlanningToolExecutionInputManifest(
                            document_id=plan.document_id,
                            tool_name=tool_call.tool_name or "unattributed",
                            tool_call_id=tool_call_id,
                        ),
                        evidence=evidence,
                        protected_input={
                            "arguments_json": tool_call.arguments_json,
                            "result_json": tool_call.result_json,
                        },
                    )
            self.operation_repository.commit_success(
                operation_id=operation.operation_id,
                plan=plan,
                document=projected_document,
                debug_report=projected_debug,
                trace=trace,
                harness_runtime=harness_runtime,
                runtime_prepared=runtime_prepared,
            )
        except StreamInterruptedError:
            self.operation_repository.mark_terminal(
                operation_id=operation.operation_id,
                status=LearningPlanOperationStatus.INTERRUPTED,
                error_code="learning_plan_interrupted",
                harness_runtime=harness_runtime,
                runtime_prepared=runtime_prepared,
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
                harness_runtime=harness_runtime,
                runtime_prepared=runtime_prepared,
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
        return self._refresh_plan_derived_fields(self.repository.require(plan_id))

    def update_plan(self, *, plan_id: str, course_title: str | None = None,
                    expected_revision: int | None = None) -> LearningPlanRecord:
        title = (course_title or "").strip()
        if not title:
            raise HTTPException(422, "course_title_required")
        def mutate(plan):
            plan.course_title = title
            return self._refresh_plan_derived_fields(plan)
        return self.repository.mutate(plan_id, mutate, expected_revision=expected_revision)

    def update_progress(self, *, plan_id: str, schedule_ids: list[str], status: str,
                        note: str = "", actor: str = "user", source: str = "ui",
                        expected_revision: int | None = None) -> LearningPlanRecord:
        ids = list(dict.fromkeys(value.strip() for value in schedule_ids if value.strip()))
        status = status.strip()
        if not ids:
            raise HTTPException(422, "schedule_ids_required")
        if status not in {"planned", "in_progress", "completed", "blocked", "skipped"}:
            raise HTTPException(422, "invalid_schedule_status")
        def mutate(plan):
            if not set(ids) <= {item.id for item in plan.schedule}:
                raise HTTPException(404, "schedule_items_not_found")
            for item in plan.schedule:
                if item.id in ids:
                    item.status = status
            plan.progress_events.append(PlanProgressEventRecord(
                id=f"progress-event-{uuid4().hex}", actor=actor, source=source,
                schedule_ids=ids, status=status, note=note.strip(), created_at=_now(),
            ))
            return self._refresh_plan_derived_fields(plan)
        return self.repository.mutate(plan_id, mutate, expected_revision=expected_revision)

    def answer_planning_question(self, *, plan_id: str, question_id: str, answer: str,
                                 expected_revision: int | None = None) -> LearningPlanRecord:
        answer = answer.strip()
        if not answer:
            raise HTTPException(422, "planning_question_answer_required")
        def mutate(plan):
            for question in plan.planning_questions:
                if question.id == question_id:
                    question.answer = answer
                    question.status = "answered"
                    question.answered_at = _now()
                    return self._refresh_plan_derived_fields(plan)
            raise HTTPException(404, "planning_question_not_found")
        # Saving an answer never implicitly executes a provider or replaces a plan.
        return self.repository.mutate(plan_id, mutate, expected_revision=expected_revision)

    def resolve_confirmation(self, *, session_id: str, confirmation_id: str, decision: str, note: str = ""):
        def apply(plan, confirmation):
            payload = confirmation.payload
            if confirmation.action_type == "update_plan":
                title = str(payload.get("course_title") or "").strip()
                if not title:
                    raise HTTPException(422, "course_title_required")
                plan.course_title = title
            elif confirmation.action_type == "update_plan_progress":
                ids = list(dict.fromkeys(payload.get("schedule_ids") or []))
                status = str(payload.get("status") or "")
                if not ids or not set(ids) <= {item.id for item in plan.schedule}:
                    raise HTTPException(409, "plan_confirmation_schedule_unavailable")
                if status not in {"planned", "in_progress", "completed", "blocked", "skipped"}:
                    raise HTTPException(422, "invalid_schedule_status")
                for item in plan.schedule:
                    if item.id in ids:
                        item.status = status
                plan.progress_events.append(PlanProgressEventRecord(
                    id=f"progress-event-{uuid4().hex}", actor="user", source="chat_confirmation",
                    schedule_ids=ids, status=status, note=str(payload.get("note") or note), created_at=_now(),
                ))
            else:
                raise HTTPException(400, "unsupported_confirmation_action")
            return self._refresh_plan_derived_fields(plan)
        return self.repository.resolve_confirmation(session_id, confirmation_id, decision, note, _now(), apply)

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

    def delete_plan(self, plan_id: str, expected_revision: int | None = None) -> None:
        self.repository.mutate(plan_id, lambda plan: plan, expected_revision=expected_revision, deleted=True)

    def update_study_unit_title(self, *, document_id: str, study_unit_id: str,
                               title: str) -> list[LearningPlanRecord]:
        title = title.strip()
        if not title:
            raise HTTPException(422, "study_unit_title_required")
        updated = []
        for plan in self.list_plans():
            if plan.document_id != document_id or not any(unit.id == study_unit_id for unit in plan.study_units):
                continue
            def mutate(current):
                for unit in current.study_units:
                    if unit.id == study_unit_id:
                        unit.title = title
                return self._refresh_plan_derived_fields(current)
            updated.append(self.repository.mutate(plan.id, mutate))
        return updated

    def list_plans(self) -> list[LearningPlanRecord]:
        return self._load_plans()

    def _load_plans(self) -> list[LearningPlanRecord]:
        return [self._refresh_plan_derived_fields(plan) for plan in self.store.load_list("plans", LearningPlanRecord)]

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

    def _build_progress_summary(self, schedule):
        return PlanProgressProjector()._build_progress_summary(schedule)

    def _build_study_unit_progress(self, plan):
        return PlanProgressProjector()._build_study_unit_progress(plan)

    def _refresh_plan_derived_fields(self, plan):
        return PlanProgressProjector()._refresh_plan_derived_fields(plan)

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
