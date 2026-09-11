"""Pure application-owned Plan progress projections shared by reads and revisions."""
from app.models.domain import (LearningPlanRecord, LearningGoalInput, StudyScheduleRecord,
    PlanProgressSummaryRecord, StudyUnitProgressRecord)


class PlanProgressProjector:
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



def refresh_plan_progress(plan):
    return PlanProgressProjector()._refresh_plan_derived_fields(plan)
