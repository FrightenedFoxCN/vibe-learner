from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from app.models.domain import VersionedLearningPlanRecord, StudyScheduleRecord, StudyUnitRecord
from app.models.plan_revision import PlanRevisionRequestV1, PlanRevisionProposalV1, PlanRevisionDecodeError
from app.persistence.learning_plan_repository import LearningPlanRepository
from app.persistence.plan_revision_repository import PlanRevisionRepository
from app.services.local_store import LocalJsonStore
from app.services.model_provider import MockModelProvider
from app.services.harness_broad_adoption import HarnessProposalRuntimeService
from app.services.plan_revision import PlanRevisionService


def fixture_plan():
    return VersionedLearningPlanRecord(id="plan-cas", document_id="", persona_id="mentor", creation_mode="goal_only",
        course_title="Loops", objective="Learn loops", overview="Practice loops", today_tasks=["Read"],
        study_units=[StudyUnitRecord(id="unit-1", document_id="", title="Loops", page_start=1, page_end=1,
                                    unit_kind="chapter", include_in_plan=True, source_section_ids=[], summary="Loops", confidence=1)],
        schedule=[StudyScheduleRecord(id="schedule-a", unit_id="unit-1", title="Read", focus="Read loops", activity_type="reading"),
                  StudyScheduleRecord(id="schedule-b", unit_id="unit-1", title="Practice", focus="Use loops", activity_type="practice")],
        created_at="2026-09-11T00:00:00Z")


class PlanRevisionTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.store = LocalJsonStore(Path(self.temp.name))
        self.plans = LearningPlanRepository(self.store.database)
        self.plans.import_legacy([fixture_plan()])
        self.operations = PlanRevisionRepository(self.store.database)
        self.provider = MockModelProvider()
        self.service = PlanRevisionService(self.operations, HarnessProposalRuntimeService.from_database(self.store.database), self.provider)

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def request(self, key="revision-1", base=0, **kwargs):
        return PlanRevisionRequestV1(client_request_id=key, base_revision=base, instruction="Use more examples", **kwargs)

    def test_preview_accept_and_duplicate_decision(self):
        ready = self.service.create("plan-cas", self.request())
        self.assertEqual(ready.status, "ready", ready.model_dump())
        self.assertEqual(self.plans.require("plan-cas").revision, 0)
        accepted = self.service.decide("plan-cas", "revision-1", "accept")
        self.assertEqual(accepted.status, "accepted", accepted.model_dump())
        self.assertEqual(accepted.result.revision, 1)
        self.assertEqual(self.service.decide("plan-cas", "revision-1", "accept"), accepted)
        self.assertEqual(self.plans.require("plan-cas").revision, 1)
        self.assertEqual(self.service.create("plan-cas", self.request()), accepted)

    def test_progress_change_conflicts_without_losing_new_state(self):
        self.service.create("plan-cas", self.request())
        def mutate(plan):
            plan.schedule[0].status = "completed"
            return plan
        self.plans.mutate("plan-cas", mutate)
        result = self.service.decide("plan-cas", "revision-1", "accept")
        self.assertEqual(result.status, "conflict", result.model_dump())
        self.assertEqual(self.plans.require("plan-cas").schedule[0].status, "completed")
        self.assertEqual(self.plans.require("plan-cas").revision, 1)

    def test_same_key_mismatch_and_reject(self):
        self.service.create("plan-cas", self.request())
        with self.assertRaises(HTTPException):
            self.service.create("plan-cas", PlanRevisionRequestV1(client_request_id="revision-1", base_revision=0, instruction="Other"))
        rejected = self.service.decide("plan-cas", "revision-1", "reject")
        self.assertEqual(rejected.status, "rejected")
        self.assertEqual(self.plans.require("plan-cas").revision, 0)

    def test_rollback_is_new_revision_and_preserves_progress(self):
        self.service.create("plan-cas", self.request())
        self.service.decide("plan-cas", "revision-1", "accept")
        def progress(plan):
            plan.schedule[1].status = "completed"
            return plan
        self.plans.mutate("plan-cas", progress)
        request = PlanRevisionRequestV1(client_request_id="rollback", base_revision=2, rollback_revision=0)
        ready = self.service.create("plan-cas", request)
        self.assertEqual(ready.status, "ready")
        result = self.service.decide("plan-cas", "rollback", "accept")
        self.assertEqual(result.result.revision, 3)
        self.assertEqual(result.result.overview, fixture_plan().overview)
        self.assertEqual(result.result.schedule[1].status, "completed")

    def test_known_invalid_provider_response_is_failed_not_uncertain(self):
        with patch.object(self.provider, "generate_plan_revision", side_effect=PlanRevisionDecodeError("invalid")) as provider:
            result = self.service.create("plan-cas", self.request())
        self.assertEqual(result.status, "failed")
        self.assertEqual(provider.call_count, 1)
        self.assertEqual(self.plans.require("plan-cas").revision, 0)

    def test_ambiguous_provider_failure_is_query_only(self):
        with patch.object(self.provider, "generate_plan_revision", side_effect=TimeoutError("transport")) as provider:
            result = self.service.create("plan-cas", self.request())
            recovered = self.service.create("plan-cas", self.request())
        self.assertEqual(result.status, "uncertain")
        self.assertEqual(recovered, result)
        self.assertEqual(provider.call_count, 1)

    def test_insert_only_import_and_delete_tombstone(self):
        self.plans.mutate("plan-cas", lambda plan: plan, deleted=True)
        self.assertEqual(self.store.load_list("plans", VersionedLearningPlanRecord), [])
        with self.assertRaises(ValueError):
            self.plans.import_legacy([fixture_plan()])


if __name__ == "__main__":
    unittest.main()
