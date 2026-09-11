"""Deterministic Plan Revision patch regression; not independent model quality."""
from __future__ import annotations

import json
from uuid import uuid4

from app.models.domain import VersionedLearningPlanRecord, StudyScheduleRecord, StudyUnitRecord
from app.models.harness import HarnessContractRef
from app.models.plan_revision import PlanRevisionRequestV1, PlanRevisionProposalV1, apply_patch, proposal_from_plan
from app.persistence.plan_revision_repository import PlanRevisionRepository
from app.persistence.learning_plan_repository import LearningPlanRepository
from app.services.harness_stage_evals import (ROOT, StageAuthority, build_harness_stage_runner,
    close_stage_runner, gate_execution)

SUITE = HarnessContractRef(name="plan_revision_regression", version="plan-revision-regression-v1")
CATALOG = ROOT / "packages/shared/fixtures/harness/plan-revision-regression-v1.json"


def fixture_plan(plan_id="eval-plan"):
    return VersionedLearningPlanRecord(id=plan_id, document_id="", persona_id="mentor",
        creation_mode="goal_only", course_title="Loops", objective="Learn loops", overview="Read and practice",
        today_tasks=["Read"], study_units=[StudyUnitRecord(id="u1", document_id="", title="Loops",
            page_start=1, page_end=1, source_section_ids=[], summary="Loop practice")], schedule=[
            StudyScheduleRecord(id="read", unit_id="u1", title="Read", focus="Read loops", activity_type="reading", status="completed"),
            StudyScheduleRecord(id="practice", unit_id="u1", title="Practice", focus="Use loops", activity_type="practice")],
        created_at="2026-09-11T00:00:00Z")


class RevisionAuthority(StageAuthority):
    def __init__(self, store):
        super().__init__(store)
        self.revisions = PlanRevisionRepository(store.database)

    def admit(self, **_):
        plan = fixture_plan("eval-plan-" + uuid4().hex)
        LearningPlanRepository(self.store.database).import_legacy([plan])
        _, binding = self.revisions.admit(plan.id, PlanRevisionRequestV1(
            client_request_id="eval-" + uuid4().hex, base_revision=0, instruction="Reorder existing work"))
        return binding

    def finish(self, binding, success):
        # Stage-only measurement: an admitted operation ends without claiming a Plan commit.
        self.revisions.fail(binding.domain_operation_id, status="failed")


def execute_revision(stage, payload):
    if stage != "plan_revision":
        raise ValueError("revision_eval_stage_mismatch")
    base = fixture_plan()
    proposal = proposal_from_plan(base, "Reorder existing work")
    raw = proposal.model_dump(mode="json")
    scenario = payload["scenario"]
    if scenario == "reorder":
        raw["schedule"].reverse()
    elif scenario == "foreign_target":
        raw["schedule"][0]["schedule_ref"] = "foreign"
    elif scenario == "duplicate_target":
        raw["schedule"][1]["schedule_ref"] = "read"
    elif scenario == "missing_target":
        raw["schedule"].pop()
    elif scenario == "owned_field":
        raw["schedule"][0]["status"] = "pending"
    elif scenario == "blank_task":
        raw["today_tasks"] = ["  "]
    elif scenario == "rollback":
        base.overview = "New overview"
        base.revision = 3
    else:
        raise ValueError("revision_eval_scenario_unknown")
    try:
        result = apply_patch(base, PlanRevisionProposalV1.model_validate(raw))
    except ValueError:
        return {"accepted": False}
    return {"accepted": True, "identity_preserved": {x.id for x in result.schedule} == {x.id for x in base.schedule},
            "progress_preserved": {x.id: x.status for x in result.schedule} == {x.id: x.status for x in base.schedule},
            "revision_preserved": result.revision == base.revision,
            "reordered": result.schedule[0].id == "practice",
            "historical_restored": result.overview == "Read and practice"}


def build_plan_revision_runner():
    return build_harness_stage_runner(catalog_path=CATALOG,
        suites={"planning:plan_revision": SUITE}, authority_factory=RevisionAuthority, execute_case=execute_revision)


def main():
    runner = build_plan_revision_runner()
    try:
        cases = runner.stage_cases[SUITE.name]
        execution = runner.run(runner.stage_runs[SUITE.name], cases, selected_suites=[SUITE],
                               release_gate=True, deterministic_gate=True)
        passed = gate_execution(execution, 7)
        print(json.dumps({"suite": SUITE.name, "samples": len(execution.raw_samples),
            "gate": "passed" if passed else "failed", "report": execution.report.status, "failures": [f.failure_code for s in execution.raw_samples for f in s.failures]}))
        return 0 if passed else 1
    finally:
        close_stage_runner(runner)


if __name__ == "__main__":
    raise SystemExit(main())
