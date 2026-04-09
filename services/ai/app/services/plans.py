from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.models.domain import DocumentRecord, LearningGoalInput, LearningPlanRecord
from app.services.local_store import LocalJsonStore


class LearningPlanService:
    def __init__(self, store: LocalJsonStore) -> None:
        self.store = store

    def create_plan(
        self, *, goal: LearningGoalInput, document: DocumentRecord, persona_name: str
    ) -> LearningPlanRecord:
        section_titles = [section.title for section in document.sections] or [document.title]
        plan = LearningPlanRecord(
            id=f"plan-{uuid4().hex[:10]}",
            document_id=document.id,
            persona_id=goal.persona_id,
            objective=goal.objective,
            deadline=goal.deadline,
            overview=(
                f"{persona_name} 将在 {goal.deadline} 前带你完成 {document.title}，"
                f"重点覆盖 {', '.join(section_titles[:2])}。"
            ),
            weekly_focus=section_titles[:3],
            today_tasks=[
                f"通读 {section_titles[0]}，标出本章定义句。",
                f"用 {goal.session_minutes} 分钟完成一次复述练习。",
                "提交一次短答并根据反馈补写教材例子。",
            ],
            created_at=_now(),
        )
        plans = self._load_plans()
        plans.append(plan)
        self._save_plans(plans)
        return plan

    def require_plan(self, plan_id: str) -> LearningPlanRecord:
        plans = self._load_plans()
        for plan in plans:
            if plan.id == plan_id:
                return plan
        raise HTTPException(status_code=404, detail="plan_not_found")

    def _load_plans(self) -> list[LearningPlanRecord]:
        return self.store.load_list("plans", LearningPlanRecord)

    def _save_plans(self, plans: list[LearningPlanRecord]) -> None:
        self.store.save_list("plans", plans)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
