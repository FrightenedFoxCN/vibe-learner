"""Abrupt child-process exit, fresh database connections, authoritative recovery."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from app.models.planning import LearningPlanOperationRequestV1
from app.persistence.harness_operation_repository import (
    HarnessOperationBindingRepository,
)
from app.persistence.harness_workflow_operation_repository import (
    HarnessWorkflowOperationRepository,
)
from app.persistence.learning_plan_operation_repository import (
    LearningPlanOperationRepository,
)
from app.services.documents import DocumentService
from app.services.harness_broad_adoption import (
    HarnessProposalRuntimeService,
)
from app.models.persona_generation import (
    PersonaGenerationInputManifest,
    PersonaGenerationProposalV1,
)
from app.models.scene_generation import (
    SceneGenerationInputManifest,
    SceneGenerationProposalV1,
)
from app.services.local_store import LocalJsonStore
from app.services.model_provider import MockModelProvider
from app.services.persona import PersonaEngine
from app.services.plans import LearningPlanService
from app.services.study_arrangement import StudyArrangementService
from sqlalchemy import text
from tests import test_document_process_operation as document_fixtures
from tests.test_document_process_operation import _FakeArrangement, _FakeParser
from tests.test_learning_plan_operation import _debug, _document, _goal_for, _reply
from tests.test_wave45_input_limits import layer, scene


def crash(*args, **kwargs):
    # Deliberately bypass finally, store.close(), atexit and Python cleanup.
    os._exit(73)


def child(root: Path, scenario: str):
    store = LocalJsonStore(root)
    if scenario.startswith("document"):
        service = DocumentService(store, _FakeParser(), _FakeArrangement())
        if scenario.startswith("document_fault_"):
            service.process_repository.fault_injector = lambda stage: (
                crash() if stage == scenario.removeprefix("document_fault_") else None
            )
        document = document_fixtures.DocumentProcessOperationTests._create_document(
            service, "synthetic.pdf"
        )
        (root / "identity.json").write_text(json.dumps({"document": document.id}))
        if scenario == "document_pending":
            service.process_repository.admit(document_id=document.id, force_ocr=False)
        else:
            service.process_document(document.id)
        crash()
    if scenario.startswith("plan"):
        persona = PersonaEngine(store).require_persona("mentor-aurora")
        if scenario == "plan_committed" or scenario.startswith("plan_fault_"):
            document = _document()
            debug = _debug(document)
            store.save_list("documents", [document])
            store.save_item("document_debug", document.id, debug)
            provider = MockModelProvider()
            repo = LearningPlanOperationRepository(store.database)
            if scenario.startswith("plan_fault_"):
                repo.fault_injector = lambda stage: (
                    crash() if stage == scenario.removeprefix("plan_fault_") else None
                )
            service = LearningPlanService(
                store, StudyArrangementService(), provider, operation_repository=repo
            )
            with patch.object(
                provider, "generate_learning_plan", return_value=_reply(document)
            ):
                result = service.create_plan(
                    goal=_goal_for(document, scenario, persona.id),
                    document=document,
                    persona_name=persona.name,
                    persona=persona,
                    debug_report=debug,
                )
            (root / "identity.json").write_text(json.dumps({"plan": result.id}))
        else:
            repo = LearningPlanOperationRepository(store.database)
            op, _ = repo.admit(
                request=LearningPlanOperationRequestV1(
                    client_request_id=scenario,
                    persona_id=persona.id,
                    objective="Synthetic restart acceptance",
                )
            )
            if scenario == "plan_issued":
                repo.mark_provider_started(operation_id=op.operation_id)
        crash()
    if scenario.startswith("study"):
        from app.models.domain import StudySessionRecord
        from app.models.study_chat_operation import StudyChatOperationRequestPayload
        from app.persistence.study_chat_operation_repository import (
            StudyChatOperationRepository,
        )
        from app.persistence.study_session_repository import StudySessionRepository

        sessions = StudySessionRepository(store.database)
        sessions.create(
            StudySessionRecord(
                id="session-restart",
                document_id="doc",
                persona_id="persona",
                study_unit_id="unit",
                status="active",
                turns=[],
                revision=0,
                last_turn_sequence=0,
                created_at="2026-09-09T00:00:00Z",
                updated_at="2026-09-09T00:00:00Z",
            )
        )
        repo = StudyChatOperationRepository(store.database)
        op = repo.admit(
            session_id="session-restart",
            client_request_id="restart-study-request",
            request_payload=StudyChatOperationRequestPayload(
                message="synthetic",
                message_kind="learner",
                follow_up_id="",
                hidden_message_prefix="",
                expected_session_revision=0,
                attachments=[],
            ),
        )
        if scenario != "study_admitted":
            op, claimed = repo.claim(operation_id=op.operation_id, timeout_seconds=30)
            assert claimed
            if scenario == "study_issued":
                repo.mark_provider_started(
                    operation_id=op.operation_id, execution_token=op.execution_token
                )
        (root / "identity.json").write_text(json.dumps({"operation": op.operation_id}))
        crash()
    if scenario.startswith("tavern"):
        from app.models.api import CreatePersonaRequest
        from app.models.tavern import CreateTavernRoomRequest, TavernTurnRequest
        from app.persistence.tavern_repository import TavernRepository
        from app.services.tavern import TavernService
        from tests.test_tavern_facilitated import SequencedTavernProvider

        engine = PersonaEngine(store)
        personas = [
            engine.create_persona(
                CreatePersonaRequest(
                    name=f"Synthetic {i}",
                    summary="Synthetic",
                    system_prompt="Synthetic",
                    slots=[],
                )
            )
            for i in range(6)
        ]
        repo = TavernRepository(store.database)
        provider = SequencedTavernProvider()
        service = TavernService(
            repository=repo, persona_engine=engine, model_provider=provider
        )
        room = service.create_room(
            CreateTavernRoomRequest(
                title="t" * 80,
                persona_ids=[p.id for p in personas],
                opening_prompt="o" * 2000,
                idempotency_key="restart-room-key",
            )
        )
        payload = TavernTurnRequest(
            input={"kind": "user_message", "content": "x" * 4000},
            mode="facilitated",
            target_persona_ids=[p.id for p in personas[:4]],
            guidance="g" * 1000,
            idempotency_key="restart-turn-key",
            expected_room_revision=room.room.revision,
        )
        (root / "identity.json").write_text(json.dumps({"room": room.room.id}))
        if scenario == "tavern_pending":
            service._execute_run = crash
        else:
            original = provider.generate_tavern_actor_reply

            def interrupted(**kwargs):
                if len(provider.calls) == 1:
                    crash()
                return original(**kwargs)

            provider.generate_tavern_actor_reply = interrupted
        service.run_turn(room_id=room.room.id, payload=payload)
        raise AssertionError("tavern crash point was not reached")
    service = HarnessProposalRuntimeService.from_database(store.database)
    # Terminal trace already persisted, generic row still running: separate crash window.
    if scenario.endswith("terminal"):
        service.workflow_operations.terminalize = crash

    def generate(_):
        if scenario.endswith("generating"):
            crash()
        if scenario.startswith("persona"):
            return PersonaGenerationProposalV1(
                request_kind="slot_assist",
                slot=dict(kind="tone", label="Tone", content="Synthetic patient tutor"),
            )
        return SceneGenerationProposalV1(
            used_model="fixture", used_web_search=False, proposal=scene([layer()])
        )

    if scenario.startswith("persona"):
        service.run_persona(
            manifest=PersonaGenerationInputManifest(
                request_kind="slot_assist",
                mode="keywords",
                requested_count=1,
                input_char_count=9,
            ),
            protected_input={"text": "synthetic"},
            generate=generate,
        )
    else:
        service.run_scene(
            manifest=SceneGenerationInputManifest(
                mode="keywords", requested_layer_count=1, input_char_count=9
            ),
            protected_input={"text": "synthetic"},
            generate=generate,
        )
    raise AssertionError("crash point was not reached")


class Wave45ProcessRecoveryTests(unittest.TestCase):
    def run_child(self, root, scenario):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.test_wave45_process_recovery",
                "--crash-child",
                str(root),
                scenario,
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        self.assertEqual(result.returncode, 73, result.stdout + result.stderr)

    def assert_integrity(self, store):
        with store.database.engine.connect() as conn:
            self.assertEqual(
                conn.exec_driver_sql("PRAGMA integrity_check").scalar(), "ok"
            )
            self.assertEqual(conn.exec_driver_sql("PRAGMA foreign_key_check").all(), [])

    def test_document_precommit_and_postcommit_process_exit(self):
        for scenario in ("document_pending", "document_committed"):
            with self.subTest(scenario=scenario), TemporaryDirectory() as folder:
                root = Path(folder)
                self.run_child(root, scenario)
                store = LocalJsonStore(root)
                try:
                    parser = _FakeParser()
                    service = DocumentService(store, parser, _FakeArrangement())
                    identity = json.loads((root / "identity.json").read_text())
                    op = service.process_repository.latest(
                        document_id=identity["document"]
                    )
                    binding = service.process_repository.require_harness_operation(
                        op.operation_id
                    )
                    recovered = service.recover_abandoned_operations()
                    final = service.process_repository.require(
                        operation_id=op.operation_id
                    )
                    self.assertEqual(
                        final.status.value,
                        "failed" if scenario.endswith("pending") else "committed",
                    )
                    self.assertEqual(
                        recovered, 1 if scenario.endswith("pending") else 0
                    )
                    self.assertEqual(service.recover_abandoned_operations(), 0)
                    self.assertEqual(
                        service.process_repository.require_harness_operation(
                            op.operation_id
                        ),
                        binding,
                    )
                    self.assertEqual(parser.force_ocr_calls, [])
                    self.assert_integrity(store)
                finally:
                    store.close()

    def test_planning_preprovider_issued_and_committed_process_exit(self):
        for scenario, status in (
            ("plan_pending", "not_committed"),
            ("plan_issued", "uncertain"),
            ("plan_committed", "committed"),
        ):
            with self.subTest(scenario=scenario), TemporaryDirectory() as folder:
                root = Path(folder)
                self.run_child(root, scenario)
                store = LocalJsonStore(root)
                try:
                    repo = LearningPlanOperationRepository(store.database)
                    op = repo.get_by_client_request_id(client_request_id=scenario)
                    binding = repo.require_harness_operation(op.operation_id)
                    repo.recover_abandoned()
                    final = repo.require(
                        operation_id=op.operation_id, validate_current=True
                    )
                    self.assertEqual(final.status.value, status)
                    self.assertEqual(repo.recover_abandoned(), [])
                    self.assertEqual(
                        repo.require_harness_operation(op.operation_id), binding
                    )
                    with store.database.engine.connect() as conn:
                        self.assertEqual(
                            conn.execute(
                                text("SELECT count(*) FROM learning_plans")
                            ).scalar(),
                            1 if status == "committed" else 0,
                        )
                    if status == "committed":
                        persona = PersonaEngine(store).require_persona("mentor-aurora")
                        provider = MockModelProvider()
                        service = LearningPlanService(
                            store, StudyArrangementService(), provider
                        )
                        document = _document()
                        with patch.object(
                            provider,
                            "generate_learning_plan",
                            side_effect=AssertionError("duplicate provider call"),
                        ):
                            replay = service.create_plan(
                                goal=_goal_for(document, scenario, persona.id),
                                document=document,
                                persona_name=persona.name,
                                persona=persona,
                                debug_report=_debug(document),
                            )
                        self.assertEqual(
                            replay.id,
                            json.loads((root / "identity.json").read_text())["plan"],
                        )
                    self.assert_integrity(store)
                finally:
                    store.close()

    def test_process_exit_inside_each_document_and_plan_commit_statement(self):
        stages = {
            "document": (
                "before_debug_projection",
                "after_debug_projection",
                "after_document_projection",
                "before_terminal_commit",
            ),
            "plan": (
                "before_document_projection",
                "after_document_projection",
                "after_debug_projection",
                "after_trace_projection",
                "after_plan_projection",
                "before_terminal_commit",
            ),
        }
        for workflow, boundaries in stages.items():
            for boundary in boundaries:
                with (
                    self.subTest(workflow=workflow, boundary=boundary),
                    TemporaryDirectory() as folder,
                ):
                    root = Path(folder)
                    self.run_child(root, f"{workflow}_fault_{boundary}")
                    store = LocalJsonStore(root)
                    try:
                        if workflow == "document":
                            service = DocumentService(
                                store, _FakeParser(), _FakeArrangement()
                            )
                            doc_id = json.loads((root / "identity.json").read_text())[
                                "document"
                            ]
                            service.recover_abandoned_operations()
                            final = service.process_repository.latest(
                                document_id=doc_id
                            )
                            self.assertEqual(final.status.value, "failed")
                            self.assertFalse(
                                service.require_document(doc_id).debug_ready
                            )
                            with store.database.engine.connect() as conn:
                                self.assertEqual(
                                    conn.execute(
                                        text(
                                            "SELECT count(*) FROM document_debug_records"
                                        )
                                    ).scalar(),
                                    0,
                                )
                        else:
                            repo = LearningPlanOperationRepository(store.database)
                            repo.recover_abandoned()
                            final = repo.get_by_client_request_id(
                                client_request_id=f"plan_fault_{boundary}"
                            )
                            self.assertEqual(final.status.value, "uncertain")
                            from app.models.domain import (
                                DocumentDebugRecord,
                                DocumentRecord,
                            )

                            base = _document()
                            self.assertEqual(
                                store.load_list("documents", DocumentRecord)[
                                    0
                                ].model_dump(mode="json"),
                                base.model_dump(mode="json"),
                            )
                            self.assertEqual(
                                store.load_item(
                                    "document_debug", base.id, DocumentDebugRecord
                                ).model_dump(mode="json"),
                                _debug(base).model_dump(mode="json"),
                            )
                            with store.database.engine.connect() as conn:
                                for table in ("learning_plans", "planning_traces"):
                                    self.assertEqual(
                                        conn.execute(
                                            text(f"SELECT count(*) FROM {table}")
                                        ).scalar(),
                                        0,
                                    )
                        self.assert_integrity(store)
                    finally:
                        store.close()

    def test_study_expired_admitted_claimed_and_issued_restart(self):
        from app.persistence.study_chat_operation_repository import (
            StudyChatOperationRepository,
        )

        for scenario in ("study_admitted", "study_claimed", "study_issued"):
            with self.subTest(scenario=scenario), TemporaryDirectory() as folder:
                root = Path(folder)
                self.run_child(root, scenario)
                store = LocalJsonStore(root)
                try:
                    op_id = json.loads((root / "identity.json").read_text())[
                        "operation"
                    ]
                    # Advance persisted deadlines, avoiding a real 30-second sleep per case.
                    with store.database.engine.begin() as conn:
                        conn.execute(
                            text(
                                "UPDATE study_chat_operations SET created_at='2000-01-01T00:00:00+00:00', execution_deadline_at=CASE WHEN status='admitted' THEN '' ELSE '2000-01-01T00:00:00+00:00' END WHERE operation_id=:id"
                            ),
                            {"id": op_id},
                        )
                    repo = StudyChatOperationRepository(store.database)
                    final = repo.require(
                        session_id="session-restart",
                        client_request_id="restart-study-request",
                    )
                    receipt = repo.receipt(final)
                    self.assertEqual(
                        final.status.value,
                        "not_committed"
                        if scenario == "study_admitted"
                        else "uncertain",
                    )
                    self.assertEqual(
                        receipt.safe_to_retry, scenario == "study_admitted"
                    )
                    _, claimed = repo.claim(operation_id=op_id, timeout_seconds=30)
                    self.assertFalse(claimed)
                    with store.database.engine.connect() as conn:
                        self.assertEqual(
                            conn.execute(
                                text(
                                    "SELECT revision FROM study_sessions WHERE id='session-restart'"
                                )
                            ).scalar_one(),
                            0,
                        )
                    self.assert_integrity(store)
                finally:
                    store.close()

    def test_tavern_maximum_roster_pending_and_partial_process_restart(self):
        from app.persistence.tavern_repository import TavernRepository
        from app.services.tavern import TavernService
        from tests.test_tavern_facilitated import SequencedTavernProvider

        for scenario in ("tavern_pending", "tavern_partial"):
            with self.subTest(scenario=scenario), TemporaryDirectory() as folder:
                root = Path(folder)
                self.run_child(root, scenario)
                store = LocalJsonStore(root)
                try:
                    repo = TavernRepository(store.database)
                    room_id = json.loads((root / "identity.json").read_text())["room"]
                    run = repo.get_run_by_idempotency_key(
                        room_id=room_id, idempotency_key="restart-turn-key"
                    )
                    previous = [
                        m.model_dump(mode="json")
                        for m in repo.list_run_messages(run.id)
                    ]
                    self.assertEqual(
                        len(previous), 1 if scenario == "tavern_partial" else 0
                    )
                    binding = repo.require_harness_operation(run.id)
                    with store.database.engine.begin() as conn:
                        conn.execute(
                            text(
                                "UPDATE tavern_run_steps SET lease_expires_at='2000-01-01T00:00:00+00:00' WHERE status='generating'"
                            )
                        )
                    provider = SequencedTavernProvider()
                    service = TavernService(
                        repository=repo,
                        persona_engine=PersonaEngine(store),
                        model_provider=provider,
                    )
                    recovered = service.resume_run(room_id=room_id, run_id=run.id)
                    self.assertEqual(recovered.run.status.value, "completed")
                    self.assertEqual(len(provider.calls), 4 - len(previous))
                    messages = repo.list_run_messages(run.id)
                    self.assertEqual(len(messages), 4)
                    self.assertEqual(
                        [m.model_dump(mode="json") for m in messages[: len(previous)]],
                        previous,
                    )
                    self.assertEqual(len({m.id for m in messages}), 4)
                    self.assertEqual(repo.require_harness_operation(run.id), binding)
                    service.resume_run(room_id=room_id, run_id=run.id)
                    self.assertEqual(len(provider.calls), 4 - len(previous))
                    self.assert_integrity(store)
                finally:
                    store.close()

    def test_persona_scene_generation_and_terminal_trace_crash_windows(self):
        for workflow in ("persona", "scene"):
            for phase in ("generating", "terminal"):
                with (
                    self.subTest(workflow=workflow, phase=phase),
                    TemporaryDirectory() as folder,
                ):
                    root = Path(folder)
                    self.run_child(root, f"{workflow}_{phase}")
                    store = LocalJsonStore(root)
                    try:
                        repo = HarnessWorkflowOperationRepository(store.database)
                        with store.database.engine.connect() as conn:
                            before = conn.execute(
                                text(
                                    "SELECT harness_operation_id FROM harness_workflow_operations"
                                )
                            ).scalar_one()
                        binding = HarnessOperationBindingRepository(
                            store.database
                        ).resolve_harness_id(harness_operation_id=before)
                        self.assertEqual(repo.recover_abandoned_operations(), 1)
                        self.assertEqual(repo.recover_abandoned_operations(), 0)
                        with store.database.engine.connect() as conn:
                            row = conn.execute(
                                text(
                                    "SELECT status, harness_operation_id FROM harness_workflow_operations"
                                )
                            ).one()
                            self.assertEqual(
                                row[0], "completed" if phase == "terminal" else "failed"
                            )
                            self.assertEqual(row[1], before)
                            traces = conn.execute(
                                text(
                                    "SELECT terminal_trace FROM harness_runtime_executions"
                                )
                            ).all()
                            self.assertEqual(len(traces), 1)
                            self.assertEqual(
                                traces[0][0] not in (None, "null"), phase == "terminal"
                            )
                        self.assertEqual(
                            HarnessOperationBindingRepository(
                                store.database
                            ).resolve_harness_id(harness_operation_id=before),
                            binding,
                        )
                        self.assert_integrity(store)
                    finally:
                        store.close()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--crash-child":
        child(Path(sys.argv[2]), sys.argv[3])
    else:
        unittest.main()
