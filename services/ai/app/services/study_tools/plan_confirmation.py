from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.models.study_chat_effect import (
    StudyPlanConfirmationEffectAction,
    StudyPlanConfirmationEffectProposalV1,
)
from app.services.study_tools.context import StudyToolContext
from fastapi import HTTPException


@dataclass
class PlanConfirmationTools:
    context: StudyToolContext

    def update_learning_plan(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if not self.context.plan_id:
            raise HTTPException(status_code=400, detail="plan_not_bound")
        course_title = str(arguments.get("course_title") or "").strip()
        note = str(arguments.get("note") or "").strip()
        if not course_title:
            raise HTTPException(status_code=422, detail="plan_update_empty")
        plan = self.context.plans.require_plan(self.context.plan_id)
        if self.context.effects is None:
            raise HTTPException(
                status_code=409, detail="study_chat_effect_collector_required"
            )
        effect = self.context.effects.prepare_plan_confirmation(
            StudyPlanConfirmationEffectProposalV1(
                action=StudyPlanConfirmationEffectAction.UPDATE_PLAN,
                course_title=course_title,
                note=note,
            )
        )
        return {
            "ok": True,
            "tool_name": "update_learning_plan",
            "requires_confirmation": True,
            "effect_state": "prepared",
            "committed": False,
            "prepared_effect_id": effect.effect_id,
            "prepared_proposal": effect.proposal.model_dump(mode="json"),
            "predicted_state": {
                "slot": effect.slot,
                "plan_id": self.context.plan_id,
                "preview_lines": [f"课程标题：{plan.course_title} -> {course_title}"],
            },
        }

    def update_learning_plan_progress(
        self, arguments: dict[str, Any]
    ) -> dict[str, Any]:
        if not self.context.plan_id:
            raise HTTPException(status_code=400, detail="plan_not_bound")
        plan = self.context.plans.require_plan(self.context.plan_id)
        schedule_ids = _collect_schedule_ids(plan, arguments)
        status = str(arguments.get("status") or "").strip()
        note = str(arguments.get("note") or "").strip()
        if not schedule_ids:
            raise HTTPException(status_code=422, detail="schedule_ids_required")
        if status not in {"planned", "in_progress", "completed", "blocked", "skipped"}:
            raise HTTPException(status_code=422, detail="invalid_schedule_status")
        schedule_map = {item.id: item for item in plan.schedule}
        if self.context.effects is None:
            raise HTTPException(
                status_code=409, detail="study_chat_effect_collector_required"
            )
        effect = self.context.effects.prepare_plan_confirmation(
            StudyPlanConfirmationEffectProposalV1(
                action=StudyPlanConfirmationEffectAction.UPDATE_PLAN_PROGRESS,
                schedule_ids=schedule_ids,
                schedule_status=status,
                note=note,
            )
        )
        return {
            "ok": True,
            "tool_name": "update_learning_plan_progress",
            "requires_confirmation": True,
            "effect_state": "prepared",
            "committed": False,
            "prepared_effect_id": effect.effect_id,
            "prepared_proposal": effect.proposal.model_dump(mode="json"),
            "predicted_state": {
                "slot": effect.slot,
                "plan_id": self.context.plan_id,
                "preview_lines": [
                    f"{schedule_id} | {schedule_map[schedule_id].title} -> {status}"
                    for schedule_id in schedule_ids
                    if schedule_id in schedule_map
                ],
            },
        }


def _collect_schedule_ids(plan, arguments: dict[str, Any]) -> list[str]:
    schedule_ids: list[str] = []
    single_schedule_id = str(arguments.get("schedule_id") or "").strip()
    if single_schedule_id:
        schedule_ids.append(single_schedule_id)
    raw_schedule_ids = arguments.get("schedule_ids")
    if isinstance(raw_schedule_ids, list):
        schedule_ids.extend(
            str(item).strip() for item in raw_schedule_ids if str(item).strip()
        )
    study_unit_ids: list[str] = []
    single_study_unit_id = str(arguments.get("study_unit_id") or "").strip()
    if single_study_unit_id:
        study_unit_ids.append(single_study_unit_id)
    raw_study_unit_ids = arguments.get("study_unit_ids")
    if isinstance(raw_study_unit_ids, list):
        study_unit_ids.extend(
            str(item).strip() for item in raw_study_unit_ids if str(item).strip()
        )
    if study_unit_ids:
        for progress in plan.study_unit_progress:
            if progress.unit_id in study_unit_ids:
                schedule_ids.extend(progress.schedule_ids)
    deduped: list[str] = []
    seen: set[str] = set()
    for item in schedule_ids:
        if not item or item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped
