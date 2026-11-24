import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_container
from app.api.routers.planning import router as planning_router
from app.api.routers.study import router as study_router
from app.core.bootstrap import Container
from app.core.settings import Settings
from app.models.domain import LearningGoalInput
from app.models.planning import (
    LearningPlanOperationRequestV1,
    LearningPlanOperationStatus,
)
from app.persistence.learning_plan_operation_repository import (
    LearningPlanOperationNotRunning,
)
from tests.support.planning_operations import planning_document


class PlanStreamCancellationTests(TestCase):
    def test_cancellation_wins_before_commit_but_not_after_fence(self):
        for before_commit in (True, False):
            with self.subTest(before_commit=before_commit), TemporaryDirectory() as tmp:
                container = Container(
                    Settings(
                        database_url=f"sqlite:///{tmp}/test.db",
                        storage_root=str(Path(tmp) / "data"),
                        auto_migrate_local_data=False,
                        plan_provider="mock",
                        ocr_engine="disabled",
                    )
                )
                self.addCleanup(container.close)
                app = FastAPI()
                app.include_router(planning_router)
                app.include_router(study_router)
                app.dependency_overrides[get_container] = lambda: container
                client = TestClient(app)
                registry = container.stream_interrupt_registry
                handles = []
                replies = []
                create = registry.create

                def track(**kwargs):
                    handle = create(**kwargs)
                    handles.append(handle)
                    return handle

                def cancel():
                    response = client.post(
                        f"/stream-runs/{handles[0].stream_id}/cancel"
                    )
                    replies.append(response.json())

                if before_commit:
                    service = container.plan_service
                    create_plan = service.create_plan

                    def run(**kwargs):
                        fence = kwargs["before_commit"]

                        def cancel_then_fence():
                            cancel()
                            fence()

                        return create_plan(
                            **{**kwargs, "before_commit": cancel_then_fence}
                        )

                    window = patch.object(service, "create_plan", side_effect=run)
                else:
                    store = container.store
                    mirror = store.mirror_learning_plan_projection

                    def mirror_then_cancel(**kwargs):
                        mirror(**kwargs)
                        cancel()

                    window = patch.object(
                        store,
                        "mirror_learning_plan_projection",
                        side_effect=mirror_then_cancel,
                    )

                with patch.object(registry, "create", side_effect=track), window:
                    response = client.post(
                        "/learning-plans/stream",
                        json={
                            "persona_id": container.persona_engine.list_personas()[
                                0
                            ].id,
                            "objective": "Learn vectors",
                            "client_request_id": "cancel-fixture",
                        },
                    )
                self.assertEqual(response.status_code, 200)
                event = json.loads(response.text.splitlines()[-1])
                operation = client.get(
                    "/learning-plan-operations/cancel-fixture"
                ).json()
                self.assertEqual(len(replies), 1)
                self.assertIs(replies[0]["cancelled"], before_commit)
                self.assertEqual(
                    event["stage"],
                    "stream_cancelled" if before_commit else "stream_completed",
                )
                self.assertEqual(
                    operation["status"], "interrupted" if before_commit else "committed"
                )
                self.assertEqual(
                    event["terminal_evidence"]["commit_status"],
                    "not_committed" if before_commit else "committed",
                )
                container.close()

    def test_replay_cancellation_only_controls_current_stream(self):
        with TemporaryDirectory() as tmp:
            container = Container(
                Settings(
                    database_url=f"sqlite:///{tmp}/test.db",
                    storage_root=str(Path(tmp) / "data"),
                    auto_migrate_local_data=False,
                    plan_provider="mock",
                    ocr_engine="disabled",
                )
            )
            self.addCleanup(container.close)
            app = FastAPI()
            app.include_router(planning_router)
            app.include_router(study_router)
            app.dependency_overrides[get_container] = lambda: container
            client = self.enterContext(TestClient(app))
            payload = {
                "persona_id": container.persona_engine.list_personas()[0].id,
                "objective": "Learn vectors",
                "client_request_id": "replay-cancel-fixture",
            }
            operation_path = "/learning-plan-operations/replay-cancel-fixture"
            initial = client.post("/learning-plans", json=payload)
            self.assertEqual(initial.status_code, 200, initial.text)
            historical = client.get(operation_path).json()
            self.assertEqual(historical["status"], "committed")
            registry = container.stream_interrupt_registry
            service = container.plan_service
            create = registry.create
            admit = service.operation_repository.admit
            create_plan = service.create_plan

            for early in (True, False):
                with self.subTest(early=early):
                    handles = []
                    replies = []

                    def track(**kwargs):
                        handle = create(**kwargs)
                        handles.append(handle)
                        return handle

                    def cancel():
                        reply = client.post(
                            f"/stream-runs/{handles[0].stream_id}/cancel"
                        )
                        reply.raise_for_status()
                        replies.append(reply.json()["cancelled"])

                    def admit_then_cancel(**kwargs):
                        admission = admit(**kwargs)
                        cancel()
                        return admission

                    def cancel_after_publication(**kwargs):
                        publish = kwargs["operation_admitted_callback"]

                        def publish_then_cancel(operation_id):
                            publish(operation_id)
                            cancel()

                        return create_plan(
                            **{
                                **kwargs,
                                "operation_admitted_callback": publish_then_cancel,
                            }
                        )

                    window = (
                        patch.object(
                            service.operation_repository,
                            "admit",
                            side_effect=admit_then_cancel,
                        )
                        if early
                        else patch.object(
                            service, "create_plan", side_effect=cancel_after_publication
                        )
                    )
                    with (
                        patch.object(registry, "create", side_effect=track),
                        patch.object(
                            container.model_provider, "generate_learning_plan"
                        ) as provider,
                        window,
                    ):
                        response = client.post("/learning-plans/stream", json=payload)
                        provider.assert_not_called()
                    self.assertEqual(response.status_code, 200, response.text)
                    events = [json.loads(line) for line in response.text.splitlines()]
                    terminals = [
                        event
                        for event in events
                        if event.get("terminal_evidence") is not None
                    ]
                    self.assertEqual(terminals, events[-1:])
                    terminal = terminals[0]
                    evidence = terminal["terminal_evidence"]
                    self.assertEqual(
                        terminal["stage"],
                        "stream_cancelled" if early else "stream_completed",
                    )
                    self.assertEqual(replies, [early])
                    if early:
                        self.assertEqual(
                            evidence["domain_operation_status"], "not_admitted"
                        )
                        self.assertEqual(evidence["domain_operation_id"], "")
                        self.assertIsNone(terminal.get("committed_projection"))
                    else:
                        self.assertEqual(evidence["commit_status"], "committed")
                        self.assertEqual(
                            evidence["domain_operation_id"], historical["operation_id"]
                        )
                        self.assertEqual(
                            terminal["committed_projection"]["id"],
                            historical["plan_id"],
                        )
                    self.assertEqual(client.get(operation_path).json(), historical)


class DomainOperationLeaseTests(TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.settings = Settings(
            database_url=f"sqlite:///{temp.name}/test.db",
            storage_root=str(Path(temp.name) / "data"),
            auto_migrate_local_data=False,
            plan_provider="mock",
            ocr_engine="disabled",
        )
        self.owner = self.container()
        self.operations = self.owner.plan_service.operation_repository
        self.persona = self.owner.persona_engine.list_personas()[0]
        self.initial_time = datetime(2026, 4, 10, tzinfo=timezone.utc)
        self.now = self.initial_time
        self.enterContext(
            patch(
                "app.persistence.domain_operation_lease._database_utc_now",
                side_effect=lambda session: self.now,
            )
        )

    def container(self):
        instance = Container(self.settings)
        self.addCleanup(instance.close)
        return instance

    def test_second_start_preserves_active_document_and_renewed_plan(self):
        document = planning_document()
        self.owner.document_service.repository.insert(document)
        admitted_document, _ = self.owner.document_service.process_repository.admit(
            document_id=document.id, force_ocr=False
        )
        self.operations.lease.lease_seconds = 0.6

        provider_entered = Event()
        release_provider = Event()
        renewed = Event()
        original_provider = self.owner.model_provider.generate_learning_plan
        original_heartbeat = self.operations.lease.heartbeat

        def blocked_provider(*args, **kwargs):
            provider_entered.set()
            if not release_provider.wait(10):
                raise AssertionError("test did not release provider")
            return original_provider(*args, **kwargs)

        def observe_heartbeat(operation_id):
            attempted_at = self.now
            result = original_heartbeat(operation_id)
            if result and attempted_at > self.initial_time:
                renewed.set()
            return result

        with (
            patch.object(
                self.owner.model_provider,
                "generate_learning_plan",
                side_effect=blocked_provider,
            ),
            patch.object(
                self.operations.lease, "heartbeat", side_effect=observe_heartbeat
            ),
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            work = executor.submit(
                self.owner.plan_service.create_plan,
                goal=LearningGoalInput(
                    persona_id=self.persona.id, objective="Learn vectors"
                ),
                persona=self.persona,
                client_request_id="live-plan",
                expected_document_updated_at="",
            )
            try:
                self.assertTrue(provider_entered.wait(5))
                self.now = self.initial_time + timedelta(seconds=0.4)
                self.assertTrue(
                    renewed.wait(5), "no renewal during blocked provider call"
                )
                self.now = self.initial_time + timedelta(seconds=0.8)

                contender = self.container()
                contender.start()
                contender_plans = contender.plan_service.operation_repository
                active = contender_plans.get_by_client_request_id(
                    client_request_id="live-plan"
                )
                self.assertEqual(active.status.value, "running")
                self.assertEqual(
                    contender.document_service.require_document(document.id).status,
                    "processing",
                )
                self.assertEqual(
                    contender.document_service.process_repository.require(
                        operation_id=admitted_document.operation_id
                    ).status.value,
                    "running",
                )
                # Simulate a recovery scan which supplied a now-stale candidate.
                with patch.object(
                    contender_plans.lease,
                    "recovery_candidates",
                    return_value=[active.operation_id],
                ):
                    self.assertEqual(contender_plans.recover_abandoned(), [])
                self.assertFalse(contender_plans.lease.heartbeat(active.operation_id))
                self.assertEqual(
                    contender_plans.mark_terminal(
                        operation_id=active.operation_id,
                        status=LearningPlanOperationStatus.NOT_COMMITTED,
                        error_code="not_the_owner",
                    ).status.value,
                    "running",
                )
            finally:
                release_provider.set()
            plan = work.result(timeout=10)
        committed = self.operations.require(operation_id=active.operation_id)
        self.assertEqual(committed.status.value, "committed")
        self.assertEqual(committed.plan_id, plan.id)

    def test_sweep_recovers_only_expired_claims_and_fences_old_owner(self):
        def admit(client_request_id):
            return self.operations.admit(
                request=LearningPlanOperationRequestV1(
                    client_request_id=client_request_id,
                    persona_id=self.persona.id,
                    objective="Learn vectors",
                )
            ).operation.operation_id

        pre_provider = admit("before-provider")
        post_provider = admit("after-provider")
        self.operations.mark_provider_started(operation_id=post_provider)
        # An old binary did not write lease records; these rows remain recoverable.
        with patch.object(self.operations.lease, "admit_in_session"):
            legacy = admit("before-leases")

        contender = self.container()
        contender_plans = contender.plan_service.operation_repository
        recovered = Event()
        original_recover = contender_plans.recover_abandoned

        def observe_recovery():
            records = original_recover()
            if any(item.operation_id == post_provider for item in records):
                recovered.set()
            return records

        with (
            patch("app.core.bootstrap._DOMAIN_OPERATION_SWEEP_SECONDS", 0.02),
            patch.object(
                contender_plans, "recover_abandoned", side_effect=observe_recovery
            ),
        ):
            try:
                contender.start()
                self.assertEqual(
                    contender_plans.require(operation_id=legacy).status.value,
                    "not_committed",
                )
                self.assertEqual(
                    contender_plans.require(operation_id=post_provider).status.value,
                    "running",
                )
                self.now += timedelta(seconds=60)
                self.assertFalse(self.operations.lease.heartbeat(pre_provider))
                with self.assertRaises(LearningPlanOperationNotRunning):
                    self.operations.mark_provider_started(operation_id=pre_provider)
                self.assertTrue(
                    recovered.wait(5), "running bootstrap did not sweep expired leases"
                )
                self.assertEqual(
                    contender_plans.require(operation_id=pre_provider).error_code,
                    "learning_plan_abandoned_before_provider_start",
                )
                uncertain = contender_plans.require(operation_id=post_provider)
                self.assertEqual(uncertain.status.value, "uncertain")
                self.assertEqual(
                    uncertain.error_code, "learning_plan_abandoned_after_provider_start"
                )
                self.assertEqual(contender_plans.recover_abandoned(), [])
            finally:
                contender.close()
