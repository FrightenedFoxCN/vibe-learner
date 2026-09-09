"""Planning capability: captured configuration, bounded fallback and strict proposal repair."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from pydantic import ValidationError

from app.core.logging import get_logger
from app.models.domain import (
    DocumentDebugRecord, LearningGoalInput, LearningPlanRecord, PersonaProfile,
    PlanningQuestionRecord, PlanGenerationTraceRecord, StudyUnitRecord,
)
from app.models.planning import LearningPlanProposalV1
from app.services.model_recovery import record_model_recovery
from app.services.model_tool_config import PLAN_STAGE, TOOL_CATALOG
from app.services.openai_plan_runner import OpenAIPlanRunner
from app.services.plan_prompt import build_learning_plan_context, build_learning_plan_messages
from app.services.plan_tool_runtime import build_plan_tool_runtime
from app.services.provider_callbacks import _call_interrupt, _emit_progress
from app.services.provider_capabilities import PlanningModelCapability, PlanModelReply, PlanScheduleItem
from app.services.provider_payload import _extract_json_payload

logger = get_logger("vibe_learner.model_provider")


@dataclass(frozen=True)
class RemotePlanningProvider(PlanningModelCapability):
    plan_model: str
    plan_tools_enabled: bool
    fallback_plan_model: str
    fallback_disable_tools: bool
    multimodal_enabled: bool
    timeout_seconds: int
    disabled_tools: frozenset[str]
    request: Callable[..., tuple[dict[str, Any], int]]
    runner_factory: Callable[..., OpenAIPlanRunner] = OpenAIPlanRunner

    def supports_page_image_tools(self) -> bool:
        return self.multimodal_enabled

    def plan_tools_runtime_enabled(self) -> bool:
        return self.plan_tools_enabled

    def generate_learning_plan(
        self,
        *,
        persona: PersonaProfile,
        document_title: str,
        goal: LearningGoalInput,
        study_units: list[StudyUnitRecord],
        document_path: str | None = None,
        debug_report: DocumentDebugRecord | None = None,
        planning_questions: list[PlanningQuestionRecord] | None = None,
        existing_plan: LearningPlanRecord | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
        interrupt_check: Callable[[], None] | None = None,
    ) -> PlanModelReply:
        planning_context = build_learning_plan_context(
            study_units=study_units,
            debug_report=debug_report,
        )
        messages = build_learning_plan_messages(
            persona=persona,
            document_title=document_title,
            goal=goal,
            study_units=study_units,
            debug_report=debug_report,
            planning_questions=planning_questions,
            existing_plan=existing_plan,
        )
        tool_runtime = self._build_plan_tool_runtime(
            study_units=study_units,
            detail_map=planning_context["detail_map"],
            debug_report=debug_report,
            document_path=document_path,
            tools_enabled=self.plan_tools_enabled,
            planning_questions=planning_questions,
            progress_callback=progress_callback,
        )
        active_tool_runtime = tool_runtime
        active_model = self.plan_model
        run_result = self._run_plan_model(
            model=self.plan_model,
            document_id=goal.document_id,
            messages=messages,
            tool_runtime=tool_runtime,
            progress_callback=progress_callback,
            interrupt_check=interrupt_check,
        )
        if (
            self.fallback_plan_model
            and self.fallback_plan_model != self.plan_model
            and run_result is None
        ):
            fallback_tools_enabled = self.plan_tools_enabled and not self.fallback_disable_tools
            fallback_runtime = self._build_plan_tool_runtime(
                study_units=study_units,
                detail_map=planning_context["detail_map"],
                debug_report=debug_report,
                document_path=document_path,
                tools_enabled=fallback_tools_enabled,
                planning_questions=planning_questions,
                progress_callback=progress_callback,
            )
            logger.warning(
                "model.plan.fallback start primary=%s fallback=%s tools_enabled=%s",
                self.plan_model,
                self.fallback_plan_model,
                fallback_tools_enabled,
            )
            _emit_progress(
                progress_callback,
                "model_fallback_started",
                {
                    "primary_model": self.plan_model,
                    "fallback_model": self.fallback_plan_model,
                    "fallback_tools_enabled": fallback_tools_enabled,
                },
            )
            run_result = self._run_plan_model(
                model=self.fallback_plan_model,
                document_id=goal.document_id,
                messages=messages,
                tool_runtime=fallback_runtime,
                progress_callback=progress_callback,
                interrupt_check=interrupt_check,
                allow_fallback=False,
            )
            if run_result is not None:
                active_tool_runtime = fallback_runtime
                active_model = self.fallback_plan_model
                _emit_progress(
                    progress_callback,
                    "model_fallback_succeeded",
                    {
                        "fallback_model": self.fallback_plan_model,
                    },
                )
        if run_result is None:
            raise RuntimeError("plan_model_empty_response")
        _call_interrupt(interrupt_check)
        final_trace = run_result.trace
        try:
            proposal = _decode_learning_plan_proposal(run_result.content)
            _validate_learning_plan_proposal_refs(proposal, active_tool_runtime.current_study_units() or study_units)
        except PlanningProposalDecodeError as first_error:
            recovery = record_model_recovery(
                category="schema_retry",
                reason="plan_proposal_schema_invalid",
                strategy="strict_contract_repair",
                attempts=2,
                note=first_error.path,
            )
            _emit_progress(
                progress_callback,
                "model_recovery_attempt",
                {
                    "attempt": 1,
                    "reason": "plan_proposal_schema_invalid",
                    "strategy": "strict_contract_repair",
                    "path": first_error.path,
                },
            )
            repair_units = active_tool_runtime.current_study_units() or study_units
            repair_messages = [
                *build_learning_plan_messages(
                    persona=persona, document_title=document_title, goal=goal,
                    study_units=repair_units, debug_report=debug_report,
                    planning_questions=active_tool_runtime.current_planning_questions(),
                    existing_plan=existing_plan,
                ),
                {"role": "assistant", "content": run_result.content},
                {
                    "role": "user",
                    "content": (
                        "上一次最终计划未通过 learning-plan-proposal-v1 严格校验，"
                        f"首个错误路径为 {first_error.path or '$'}，错误类型为 {first_error.reason}。请只重新输出完整 JSON；"
                        "不得输出 plan/schedule/chapter ID、revision、状态或时间，不得遗漏或丢弃章节。"
                    ),
                },
            ]
            repaired_result = self._run_plan_model(
                model=active_model,
                document_id=goal.document_id,
                messages=repair_messages,
                tool_runtime=self._build_plan_tool_runtime(
                    study_units=repair_units,
                    detail_map=build_learning_plan_context(study_units=repair_units, debug_report=debug_report)["detail_map"],
                    debug_report=debug_report, document_path=document_path, tools_enabled=False,
                    planning_questions=active_tool_runtime.current_planning_questions(),
                    progress_callback=progress_callback,
                ),
                progress_callback=progress_callback,
                interrupt_check=interrupt_check,
                allow_fallback=False,
            )
            if repaired_result is None:
                raise RuntimeError("plan_proposal_repair_empty_response") from first_error
            try:
                proposal = _decode_learning_plan_proposal(repaired_result.content)
                _validate_learning_plan_proposal_refs(proposal, repair_units)
            except PlanningProposalDecodeError as repair_error:
                raise RuntimeError(
                    f"plan_proposal_schema_invalid:{repair_error.path or '$'}:{repair_error.reason}"
                ) from repair_error
            if repaired_result.trace.rounds:
                repaired_result.trace.rounds[0].recoveries.insert(0, recovery)
            final_trace = _merge_plan_generation_traces(
                first=run_result.trace,
                second=repaired_result.trace,
            )
        schedule_items = [
            PlanScheduleItem(
                unit_id=item.unit_id,
                title=item.title,
                focus=item.focus,
                activity_type=item.activity_type,
                schedule_chapters=list(item.schedule_chapters),
            )
            for item in proposal.schedule
        ]
        active_study_units = active_tool_runtime.current_study_units() or study_units
        planning_questions = active_tool_runtime.current_planning_questions()
        return PlanModelReply(
            course_title=proposal.course_title,
            overview=proposal.overview,
            today_tasks=list(proposal.today_tasks),
            schedule=schedule_items,
            revised_study_units=active_study_units if _study_units_changed(study_units, active_study_units) else None,
            planning_questions=planning_questions,
            debug_trace=final_trace,
        )


    def _build_plan_tool_runtime(
        self,
        *,
        study_units: list[StudyUnitRecord],
        detail_map: dict[str, object],
        debug_report: DocumentDebugRecord | None,
        document_path: str | None,
        tools_enabled: bool,
        planning_questions: list[PlanningQuestionRecord] | None = None,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
    ):
        if not tools_enabled:
            return build_plan_tool_runtime(
                study_units=study_units, detail_map=detail_map,
                planning_questions=planning_questions,
                disabled_tools=set(TOOL_CATALOG[PLAN_STAGE]),
            )
        return build_plan_tool_runtime(
            study_units=study_units,
            detail_map=detail_map,
            debug_report=debug_report,
            document_path=document_path,
            multimodal_enabled=self.multimodal_enabled,
            planning_questions=planning_questions,
            progress_callback=progress_callback,
            disabled_tools=set(self.disabled_tools),
        )


    def _run_plan_model(
        self,
        *,
        model: str,
        document_id: str,
        messages: list[dict[str, object]],
        tool_runtime,
        progress_callback: Callable[[str, dict[str, object]], None] | None,
        interrupt_check: Callable[[], None] | None = None,
        allow_fallback: bool = True,
    ):
        runner = self.runner_factory(
            model=model,
            timeout_seconds=self.timeout_seconds,
            request_chat_completion=(
                lambda payload: self.request(
                    payload,
                    request_kind="plan",
                    model=model,
                )
            ),
        )
        try:
            return runner.run(
                document_id=document_id,
                messages=messages,
                tool_runtime=tool_runtime,
                progress_callback=progress_callback,
                interrupt_check=interrupt_check,
            )
        except RuntimeError as exc:
            if allow_fallback and str(exc) in {"plan_model_empty_response", "plan_model_tool_loop_exhausted"}:
                return None
            raise



class PlanningProposalDecodeError(RuntimeError):
    def __init__(self, *, path: str, reason: str) -> None:
        super().__init__(f"plan_proposal_schema_invalid:{path or '$'}:{reason}")
        self.path = path
        self.reason = reason



def _validate_learning_plan_proposal_refs(
    proposal: LearningPlanProposalV1, study_units: list[StudyUnitRecord],
) -> None:
    """Validate against the post-tool snapshot before the one repair allowance."""
    units = {unit.id: unit for unit in study_units}
    for index, item in enumerate(proposal.schedule):
        path = f"schedule.{index}"
        unit = units.get(item.unit_id)
        if unit is None:
            raise PlanningProposalDecodeError(path=f"{path}.unit_id", reason="unknown_ref")
        allowed = set(unit.source_section_ids)
        for chapter_index, chapter in enumerate(item.schedule_chapters):
            chapter_path = f"{path}.schedule_chapters.{chapter_index}"
            if not set(chapter.source_section_ids).issubset(allowed):
                raise PlanningProposalDecodeError(path=f"{chapter_path}.source_section_ids", reason="unknown_ref")
            for slice_index, content_slice in enumerate(chapter.content_slices):
                if not set(content_slice.source_section_ids).issubset(allowed):
                    raise PlanningProposalDecodeError(
                        path=f"{chapter_path}.content_slices.{slice_index}.source_section_ids",
                        reason="unknown_ref",
                    )



def _decode_learning_plan_proposal(content: str) -> LearningPlanProposalV1:
    try:
        payload = _extract_json_payload(content)
    except RuntimeError as exc:
        raise PlanningProposalDecodeError(path="$", reason=str(exc)) from exc
    try:
        return LearningPlanProposalV1.model_validate(payload)
    except ValidationError as exc:
        first_error = exc.errors(include_url=False)[0]
        path = ".".join(str(item) for item in first_error.get("loc", ())) or "$"
        reason = str(first_error.get("type") or "validation_error")
        invariant = str(first_error.get("ctx", {}).get("error", ""))
        if invariant in {
            "duplicate_schedule_unit_ref", "duplicate_source_section_id",
            "page_end_before_page_start", "anchor_page_end_before_start",
        }:
            reason = invariant
        raise PlanningProposalDecodeError(path=path, reason=reason) from exc



def _merge_plan_generation_traces(
    *,
    first: PlanGenerationTraceRecord,
    second: PlanGenerationTraceRecord,
) -> PlanGenerationTraceRecord:
    offset = len(first.rounds)
    repaired_rounds = [
        item.model_copy(update={"round_index": offset + index})
        for index, item in enumerate(second.rounds)
    ]
    return first.model_copy(update={"rounds": [*first.rounds, *repaired_rounds]})



def _study_units_changed(
    original_units: list[StudyUnitRecord],
    current_units: list[StudyUnitRecord],
) -> bool:
    if len(original_units) != len(current_units):
        return True
    for original, current in zip(original_units, current_units):
        if (
            original.id != current.id
            or original.title != current.title
            or original.page_start != current.page_start
            or original.page_end != current.page_end
            or original.include_in_plan != current.include_in_plan
        ):
            return True
    return False

