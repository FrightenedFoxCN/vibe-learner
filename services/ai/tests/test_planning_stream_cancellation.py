import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_container
from app.api.routers.planning import router as planning_router
from app.api.routers.study import router as study_router
from app.core.bootstrap import Container
from app.core.settings import Settings


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
