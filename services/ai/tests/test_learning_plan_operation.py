from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from pydantic import ValidationError

from app.models.api import LearningPlanCreateRequest
from app.models.domain import (
    DocumentDebugRecord,
    DocumentRecord,
    PlanGenerationTraceRecord,
    StudyUnitRecord,
)
from app.models.planning import (
    LearningPlanOperationRequestV1,
    LearningPlanOperationStatus,
    LearningPlanProjectionState,
    PlanContentSliceProposalV1,
    PlanScheduleChapterProposalV1,
)
from app.models.harness_operation import (
    HarnessDomainOperationKind,
    HarnessOperationResolutionStatus,
)
from app.persistence.learning_plan_operation_repository import (
    LearningPlanAlreadyActive,
    LearningPlanOperationRepository,
    LearningPlanReadBackError,
    LearningPlanRequestConflict,
    LearningPlanStaleDebugProjection,
    LearningPlanStaleDocument,
)
from app.services.local_store import LocalJsonStore
from app.services.model_provider import MockModelProvider, PlanModelReply, PlanScheduleItem
from app.services.persona import PersonaEngine
from app.services.plans import LearningPlanService
from app.services.stream_interrupts import StreamInterruptedError
from app.services.study_arrangement import StudyArrangementService


class LearningPlanOperationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        self.store = LocalJsonStore(Path(self.temp_dir.name))
        self.persona = PersonaEngine(self.store).require_persona("mentor-aurora")
        self.document = _document()
        self.debug = _debug(self.document)
        self.store.save_list("documents", [self.document])
        self.store.save_item("document_debug", self.document.id, self.debug)

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_success_commits_all_projections_and_duplicate_reuses_snapshot(self) -> None:
        provider = MockModelProvider()
        repository = LearningPlanOperationRepository(self.store.database)
        service = LearningPlanService(
            self.store,
            StudyArrangementService(),
            provider,
            operation_repository=repository,
        )
        goal = self._goal("plan-request-success")

        with patch.object(
            provider,
            "generate_learning_plan",
            return_value=_reply(self.document),
        ) as generate:
            first = service.create_plan(
                goal=goal,
                document=self.document.model_copy(deep=True),
                persona_name=self.persona.name,
                persona=self.persona,
                debug_report=self.debug.model_copy(deep=True),
            )
            duplicate = service.create_plan(
                goal=goal,
                document=self.document.model_copy(deep=True),
                persona_name=self.persona.name,
                persona=self.persona,
                debug_report=self.debug.model_copy(deep=True),
            )

        self.assertEqual(generate.call_count, 1)
        self.assertEqual(duplicate.model_dump(mode="json"), first.model_dump(mode="json"))
        operation = service.require_operation(client_request_id=goal.client_request_id)
        self.assertEqual(operation.status, LearningPlanOperationStatus.COMMITTED)
        self.assertEqual(operation.projection_state, LearningPlanProjectionState.COMMITTED)
        self.assertEqual(operation.plan_id, first.id)
        self.assertIsNotNone(operation.committed_projection)
        self.assertEqual(operation.committed_projection.plan.id, first.id)
        repository.require(operation_id=operation.operation_id, validate_current=True)
        self.assertEqual([item.id for item in service.list_plans()], [first.id])

    def test_admission_persists_one_harness_operation_identity(self) -> None:
        repository = LearningPlanOperationRepository(self.store.database)
        request = LearningPlanOperationRequestV1(
            client_request_id="plan-request-harness-identity",
            document_id="",
            persona_id=self.persona.id,
            objective="Verify durable identity",
        )

        operation, duplicate = repository.admit(request=request)
        resolution = repository.harness_operations.resolve_domain(
            domain_operation_kind=(
                HarnessDomainOperationKind.LEARNING_PLAN_GENERATION
            ),
            domain_operation_id=operation.operation_id,
        )

        self.assertFalse(duplicate)
        self.assertEqual(
            resolution.status,
            HarnessOperationResolutionStatus.RESOLVED,
        )
        assert resolution.binding is not None
        self.assertEqual(resolution.binding.workflow.value, "planning")
        self.assertEqual(resolution.binding.entry_stage.value, "plan_generation")

    def test_every_commit_fault_rolls_back_all_projections(self) -> None:
        stages = (
            "before_document_projection",
            "after_document_projection",
            "after_debug_projection",
            "after_trace_projection",
            "after_plan_projection",
            "before_terminal_commit",
        )
        for stage in stages:
            with self.subTest(stage=stage), TemporaryDirectory() as temp_dir:
                store = LocalJsonStore(Path(temp_dir))
                try:
                    persona = PersonaEngine(store).require_persona("mentor-aurora")
                    document = _document(document_id=f"doc-{stage}")
                    debug = _debug(document)
                    store.save_list("documents", [document])
                    store.save_item("document_debug", document.id, debug)
                    base_document = document.model_dump(mode="json")
                    base_debug = debug.model_dump(mode="json")

                    def inject(actual_stage: str) -> None:
                        if actual_stage == stage:
                            raise RuntimeError(f"fault:{stage}")

                    provider = MockModelProvider()
                    repository = LearningPlanOperationRepository(
                        store.database,
                        fault_injector=inject,
                    )
                    service = LearningPlanService(
                        store,
                        StudyArrangementService(),
                        provider,
                        operation_repository=repository,
                    )
                    goal = _goal_for(document, f"plan-request-{stage}", persona.id)

                    with patch.object(
                        provider,
                        "generate_learning_plan",
                        return_value=_reply(document),
                    ):
                        with self.assertRaisesRegex(RuntimeError, f"fault:{stage}"):
                            service.create_plan(
                                goal=goal,
                                document=document.model_copy(deep=True),
                                persona_name=persona.name,
                                persona=persona,
                                debug_report=debug.model_copy(deep=True),
                            )

                    operation = service.require_operation(
                        client_request_id=goal.client_request_id
                    )
                    self.assertEqual(
                        operation.status,
                        LearningPlanOperationStatus.NOT_COMMITTED,
                    )
                    self.assertEqual(
                        operation.projection_state,
                        LearningPlanProjectionState.NOT_COMMITTED,
                    )
                    self.assertEqual(service.list_plans(), [])
                    self.assertEqual(
                        store.load_list("documents", DocumentRecord)[0].model_dump(
                            mode="json"
                        ),
                        base_document,
                    )
                    self.assertEqual(
                        store.load_item(
                            "document_debug",
                            document.id,
                            DocumentDebugRecord,
                        ).model_dump(mode="json"),
                        base_debug,
                    )
                    self.assertIsNone(
                        store.load_item(
                            "planning_trace",
                            document.id,
                            PlanGenerationTraceRecord,
                        )
                    )
                finally:
                    store.close()

    def test_document_change_after_admission_blocks_commit_without_partial_write(self) -> None:
        provider = MockModelProvider()
        service = LearningPlanService(
            self.store,
            StudyArrangementService(),
            provider,
        )
        goal = self._goal("plan-request-stale-during-provider")

        def mutate_document_then_reply(**_kwargs) -> PlanModelReply:
            changed = self.document.model_copy(deep=True)
            changed.title = "Concurrent title"
            changed.updated_at = "2026-08-24T10:01:00+00:00"
            self.store.save_list("documents", [changed])
            return _reply(self.document)

        with patch.object(
            provider,
            "generate_learning_plan",
            side_effect=mutate_document_then_reply,
        ):
            with self.assertRaisesRegex(RuntimeError, "learning_plan_stale_document"):
                service.create_plan(
                    goal=goal,
                    document=self.document.model_copy(deep=True),
                    persona_name=self.persona.name,
                    persona=self.persona,
                    debug_report=self.debug.model_copy(deep=True),
                )

        operation = service.require_operation(client_request_id=goal.client_request_id)
        self.assertEqual(operation.status, LearningPlanOperationStatus.NOT_COMMITTED)
        self.assertEqual(service.list_plans(), [])
        self.assertEqual(
            self.store.load_list("documents", DocumentRecord)[0].title,
            "Concurrent title",
        )
        self.assertEqual(
            self.store.load_item(
                "document_debug",
                self.document.id,
                DocumentDebugRecord,
            ).model_dump(mode="json"),
            self.debug.model_dump(mode="json"),
        )

    def test_debug_change_after_admission_blocks_commit_without_partial_write(self) -> None:
        provider = MockModelProvider()
        service = LearningPlanService(
            self.store,
            StudyArrangementService(),
            provider,
        )
        goal = self._goal("plan-request-stale-debug")

        def mutate_debug_then_reply(**_kwargs) -> PlanModelReply:
            changed = self.debug.model_copy(deep=True)
            changed.total_characters += 1
            self.store.save_item("document_debug", self.document.id, changed)
            return _reply(self.document)

        with patch.object(
            provider,
            "generate_learning_plan",
            side_effect=mutate_debug_then_reply,
        ):
            with self.assertRaises(LearningPlanStaleDebugProjection):
                service.create_plan(
                    goal=goal,
                    document=self.document.model_copy(deep=True),
                    persona_name=self.persona.name,
                    persona=self.persona,
                    debug_report=self.debug.model_copy(deep=True),
                )

        operation = service.require_operation(client_request_id=goal.client_request_id)
        self.assertEqual(operation.status, LearningPlanOperationStatus.NOT_COMMITTED)
        self.assertEqual(service.list_plans(), [])
        self.assertEqual(
            self.store.load_list("documents", DocumentRecord)[0].model_dump(mode="json"),
            self.document.model_dump(mode="json"),
        )
        self.assertEqual(
            self.store.load_item(
                "document_debug",
                self.document.id,
                DocumentDebugRecord,
            ).total_characters,
            self.debug.total_characters + 1,
        )

    def test_admission_rejects_active_duplicate_and_payload_drift(self) -> None:
        repository = LearningPlanOperationRepository(self.store.database)
        request = LearningPlanOperationRequestV1.model_validate(
            self._goal("plan-request-admission").model_dump(mode="json")
            | {"document_id": self.document.id}
        )
        repository.admit(request=request)

        with self.assertRaises(LearningPlanAlreadyActive):
            repository.admit(request=request)

        other_key = request.model_copy(
            update={"client_request_id": "plan-request-active-sibling"}
        )
        with self.assertRaises(LearningPlanAlreadyActive):
            repository.admit(request=other_key)

        drifted = request.model_copy(update={"objective": "Different objective"})
        with self.assertRaises(LearningPlanRequestConflict):
            repository.admit(request=drifted)

    def test_admission_rejects_stale_document_watermark(self) -> None:
        repository = LearningPlanOperationRepository(self.store.database)
        request = LearningPlanOperationRequestV1(
            client_request_id="plan-request-stale-admission",
            document_id=self.document.id,
            persona_id=self.persona.id,
            objective="Stale request",
            expected_document_updated_at="2026-08-24T09:59:00+00:00",
        )

        with self.assertRaises(LearningPlanStaleDocument):
            repository.admit(request=request)

        self.assertIsNone(
            repository.get_by_client_request_id(
                client_request_id=request.client_request_id
            )
        )

    def test_public_request_requires_stable_identity_and_document_watermark(self) -> None:
        with self.assertRaises(ValidationError):
            LearningPlanCreateRequest(
                document_id=self.document.id,
                persona_id=self.persona.id,
                objective="Missing operation identity",
                expected_document_updated_at=self.document.updated_at,
            )
        with self.assertRaises(ValidationError):
            LearningPlanCreateRequest(
                client_request_id="plan-request-missing-watermark",
                document_id=self.document.id,
                persona_id=self.persona.id,
                objective="Missing document watermark",
            )

    def test_startup_recovery_distinguishes_provider_start(self) -> None:
        repository = LearningPlanOperationRepository(self.store.database)
        before_request = LearningPlanOperationRequestV1(
            client_request_id="plan-request-abandoned-before",
            document_id="",
            persona_id=self.persona.id,
            objective="Before provider",
        )
        after_request = LearningPlanOperationRequestV1(
            client_request_id="plan-request-abandoned-after",
            document_id="",
            persona_id=self.persona.id,
            objective="After provider",
        )
        before, _ = repository.admit(request=before_request)
        after, _ = repository.admit(request=after_request)
        repository.mark_provider_started(operation_id=after.operation_id)

        recovered = {item.operation_id: item for item in repository.recover_abandoned()}

        self.assertEqual(
            recovered[before.operation_id].status,
            LearningPlanOperationStatus.NOT_COMMITTED,
        )
        self.assertEqual(
            recovered[after.operation_id].status,
            LearningPlanOperationStatus.UNCERTAIN,
        )

    def test_committed_read_back_detects_projection_tampering(self) -> None:
        provider = MockModelProvider()
        repository = LearningPlanOperationRepository(self.store.database)
        service = LearningPlanService(
            self.store,
            StudyArrangementService(),
            provider,
            operation_repository=repository,
        )
        goal = self._goal("plan-request-read-back")
        with patch.object(
            provider,
            "generate_learning_plan",
            return_value=_reply(self.document),
        ):
            plan = service.create_plan(
                goal=goal,
                document=self.document.model_copy(deep=True),
                persona_name=self.persona.name,
                persona=self.persona,
                debug_report=self.debug.model_copy(deep=True),
            )
        operation = service.require_operation(client_request_id=goal.client_request_id)
        tampered = plan.model_copy(update={"course_title": "Tampered title"})
        self.store.save_list("plans", [tampered])

        with self.assertRaises(LearningPlanReadBackError):
            repository.require(
                operation_id=operation.operation_id,
                validate_current=True,
            )

    def test_interrupt_before_provider_is_terminal_and_has_no_projection(self) -> None:
        provider = MockModelProvider()
        service = LearningPlanService(
            self.store,
            StudyArrangementService(),
            provider,
        )
        goal = self._goal("plan-request-interrupted")

        with self.assertRaises(StreamInterruptedError):
            service.create_plan(
                goal=goal,
                document=self.document.model_copy(deep=True),
                persona_name=self.persona.name,
                persona=self.persona,
                debug_report=self.debug.model_copy(deep=True),
                interrupt_check=lambda: (_ for _ in ()).throw(
                    StreamInterruptedError("stream_interrupted")
                ),
            )

        operation = service.require_operation(client_request_id=goal.client_request_id)
        self.assertEqual(operation.status, LearningPlanOperationStatus.INTERRUPTED)
        self.assertEqual(service.list_plans(), [])

    def test_interrupt_after_provider_is_terminal_and_has_no_projection(self) -> None:
        provider = MockModelProvider()
        service = LearningPlanService(
            self.store,
            StudyArrangementService(),
            provider,
        )
        goal = self._goal("plan-request-interrupted-after-provider")
        interrupt_count = 0

        def interrupt_after_provider() -> None:
            nonlocal interrupt_count
            interrupt_count += 1
            if interrupt_count >= 2:
                raise StreamInterruptedError("stream_interrupted")

        with patch.object(
            provider,
            "generate_learning_plan",
            return_value=_reply(self.document),
        ):
            with self.assertRaises(StreamInterruptedError):
                service.create_plan(
                    goal=goal,
                    document=self.document.model_copy(deep=True),
                    persona_name=self.persona.name,
                    persona=self.persona,
                    debug_report=self.debug.model_copy(deep=True),
                    interrupt_check=interrupt_after_provider,
                )

        operation = service.require_operation(client_request_id=goal.client_request_id)
        self.assertEqual(operation.status, LearningPlanOperationStatus.INTERRUPTED)
        self.assertTrue(operation.provider_started_at)
        self.assertEqual(service.list_plans(), [])

    def _goal(self, client_request_id: str) -> LearningPlanCreateRequest:
        return _goal_for(self.document, client_request_id, self.persona.id)


def _goal_for(
    document: DocumentRecord,
    client_request_id: str,
    persona_id: str,
) -> LearningPlanCreateRequest:
    return LearningPlanCreateRequest(
        client_request_id=client_request_id,
        expected_document_updated_at=document.updated_at,
        document_id=document.id,
        persona_id=persona_id,
        objective="Master vectors",
    )


def _document(*, document_id: str = "doc-plan-operation") -> DocumentRecord:
    unit = StudyUnitRecord(
        id=f"{document_id}:study-unit:1",
        document_id=document_id,
        title="Vectors",
        page_start=1,
        page_end=12,
        unit_kind="chapter",
        include_in_plan=True,
        source_section_ids=["raw-1"],
        summary="Vector foundations.",
        confidence=0.95,
    )
    return DocumentRecord(
        id=document_id,
        title="Linear Algebra",
        original_filename="linear-algebra.pdf",
        stored_path="/tmp/linear-algebra.pdf",
        status="processed",
        ocr_status="completed",
        created_at="2026-08-24T10:00:00+00:00",
        updated_at="2026-08-24T10:00:00+00:00",
        sections=[],
        study_units=[unit],
        study_unit_count=1,
        page_count=12,
        chunk_count=2,
        preview_excerpt="Vectors",
        debug_ready=True,
    )


def _debug(document: DocumentRecord) -> DocumentDebugRecord:
    return DocumentDebugRecord(
        document_id=document.id,
        parser_name="test-parser",
        processed_at=document.updated_at,
        page_count=document.page_count,
        total_characters=1000,
        extraction_method="text",
        pages=[],
        sections=[],
        study_units=[item.model_copy(deep=True) for item in document.study_units],
        chunks=[],
        warnings=[],
        dominant_language_hint="en",
    )


def _reply(document: DocumentRecord) -> PlanModelReply:
    unit = document.study_units[0]
    return PlanModelReply(
        course_title="Linear Algebra / Vectors",
        overview="A committed plan.",
        today_tasks=["Read vector definitions."],
        schedule=[
            PlanScheduleItem(
                unit_id=unit.id,
                title="Vectors deep read",
                focus="Definitions and examples.",
                activity_type="learn",
                schedule_chapters=[
                    PlanScheduleChapterProposalV1(
                        title="Vectors",
                        anchor_page_start=unit.page_start,
                        anchor_page_end=unit.page_end,
                        source_section_ids=["raw-1"],
                        content_slices=[
                            PlanContentSliceProposalV1(
                                page_start=unit.page_start,
                                page_end=unit.page_end,
                                source_section_ids=["raw-1"],
                            )
                        ],
                    )
                ],
            )
        ],
        debug_trace=PlanGenerationTraceRecord(
            document_id=document.id,
            model="test-model",
            created_at="2026-08-24T10:00:01+00:00",
            rounds=[],
        ),
    )


if __name__ == "__main__":
    unittest.main()
