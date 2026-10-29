"""Explicit disposable PostgreSQL scopes for migration and process recovery."""

from __future__ import annotations

import argparse
import io
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tarfile
import socket
import time
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from urllib.request import urlopen
import unittest
from unittest.mock import patch
from uuid import uuid4

from alembic import command
from sqlalchemy import create_engine, text, update
from sqlalchemy.engine import make_url
from sqlalchemy.schema import CreateSchema, DropSchema
from sqlalchemy.exc import DatabaseError

from app.persistence.document_repository import DocumentRepository
from app.persistence.learning_plan_operation_repository import (
    LearningPlanOperationRepository,
)
from app.persistence.study_chat_operation_repository import StudyChatOperationRepository
from app.persistence.tavern_repository import TavernRepository
from app.persistence.study_session_repository import StudySessionRepository
from app.persistence.models import StudySessionRow
from app.core.bootstrap import Container
from app.core.settings import Settings
from tests.support.migrations import alembic_config
from tests.support.process_database import (
    POSTGRES_ENV,
    SCHEMA_FILE,
    open_process_store,
    process_database_url,
)
from tests.test_wave45_process_recovery import Wave45ProcessRecoveryTests

REPO = Path(__file__).resolve().parents[4]
SERVICE = REPO / "services/ai"
OLD_REVISION = "e3a03a9"
CRASH_CASES = {
    "document_pending",
    "document_committed",
    "plan_pending",
    "plan_issued",
    "plan_committed",
    *(
        "document_fault_" + boundary
        for boundary in (
            "before_debug_projection",
            "after_debug_projection",
            "after_document_projection",
            "before_terminal_commit",
        )
    ),
    *(
        "plan_fault_" + boundary
        for boundary in (
            "before_document_projection",
            "after_document_projection",
            "after_debug_projection",
            "after_trace_projection",
            "after_plan_projection",
            "before_terminal_commit",
        )
    ),
    "study_admitted",
    "study_claimed",
    "study_issued",
    "tavern_pending",
    "tavern_partial",
}
STUDY_COMMIT_CASES = {
    "study_commit_" + boundary
    for boundary in ("after_session", "after_trace", "after_receipt", "after_commit")
}


class Probe:
    def __init__(self, url: str, root: Path):
        selected = make_url(url)
        if not selected.drivername.startswith("postgresql") or selected.host not in {
            "127.0.0.1",
            "localhost",
            "::1",
        }:
            raise ValueError(
                "probe requires an explicit loopback PostgreSQL test database"
            )
        self.url, self.root = url, root
        os.environ[POSTGRES_ENV] = url
        root.mkdir(parents=True, exist_ok=True)
        self.state_file = root / "probe.json"
        self.state = (
            json.loads(self.state_file.read_text())
            if self.state_file.exists()
            else {
                "contract": "postgres-recovery-probe-v1",
                "source_revision": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"], cwd=REPO, text=True
                ).strip(),
                "scopes": [],
                "checks": [],
            }
        )
        self.admin = create_engine(url)
        with self.admin.connect() as connection:
            self.state["postgres_version"] = connection.execute(
                text("SELECT version()")
            ).scalar_one()
            self.state.setdefault(
                "initial_database_start",
                connection.execute(text("SELECT pg_postmaster_start_time()"))
                .scalar_one()
                .isoformat(),
            )

    def save(self):
        self.state_file.write_text(
            json.dumps(self.state, ensure_ascii=False, indent=2) + "\n"
        )

    def scope(self, root: Path, label: str):
        root.mkdir(parents=True, exist_ok=True)
        schema = "vibe_pg_accept_" + uuid4().hex
        with self.admin.begin() as connection:
            connection.execute(CreateSchema(schema))
        (root / SCHEMA_FILE).write_text(schema)
        self.state["scopes"].append({"schema": schema, "label": label})
        self.save()
        return process_database_url(root)

    def upgrade(self, url, *, tree=REPO, revision="head"):
        config = alembic_config(self.url)
        config.set_main_option("script_location", str(tree / "services/ai/alembic"))
        # ConfigParser's base URL has no escaped query; the real scoped URL is
        # passed through Alembic's existing environment URL override.
        with patch.dict(os.environ, {"DATABASE_URL": url}):
            command.upgrade(config, revision)

    def migration(self):
        root = self.root / ("historical-" + uuid4().hex[:8])
        url = self.scope(root, "historical_upgrade")
        tree = self.root / "old-source"
        tree.mkdir(exist_ok=True)
        archive = subprocess.check_output(
            [
                "git",
                "archive",
                OLD_REVISION,
                "services/ai/app",
                "services/ai/alembic",
                "services/ai/alembic.ini",
                "packages/shared/fixtures",
            ],
            cwd=REPO,
        )
        with tarfile.open(fileobj=io.BytesIO(archive)) as package:
            package.extractall(tree, filter="data")
        self.upgrade(url, tree=tree)
        seed = subprocess.run(
            [
                sys.executable,
                str(SERVICE / "tests/acceptance/postgres_legacy_seed.py"),
                "--source-tree",
                str(tree),
                "--root",
                str(root),
            ],
            env={**os.environ, "DATABASE_URL": url},
            cwd=tree / "services/ai",
            capture_output=True,
            text=True,
            timeout=60,
        )
        (self.root / "old-seed.log").write_text(seed.stdout + seed.stderr)
        if seed.returncode:
            raise RuntimeError(
                f"historical seed failed; inspect {self.root / 'old-seed.log'}"
            )
        historical = json.loads((root / "historical-identities.json").read_text())
        self.upgrade(url)
        store = open_process_store(root)
        try:
            with store.database.engine.connect() as connection:
                head = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar_one()
                for table, key in [
                    ("document_process_operations", "document_digest"),
                    ("learning_plan_operations", "committed_projection_digest"),
                    ("study_chat_operations", "response_digest"),
                ]:
                    assert (
                        list(
                            connection.execute(
                                text(f"SELECT {key} FROM {table}")
                            ).scalars()
                        )
                        == historical["receipts"][table]
                    )
            document = DocumentRepository(store.database).get(historical["document_id"])
            assert document.revision == 0 and document.status == "processed"
            plan = LearningPlanOperationRepository(
                store.database
            ).get_by_client_request_id(
                client_request_id="historical-plan-request", validate_current=True
            )
            assert plan.status.value == "committed"
            study = StudyChatOperationRepository(
                store.database, chat_attachment_root=store.chat_attachment_root
            ).require(
                session_id=historical["session_id"],
                client_request_id="historical-chat-request",
            )
            assert study.status.value == "committed"
            assert (
                TavernRepository(store.database)
                .get_run(historical["run_id"])
                .status.value
                == "completed"
            )
            self.state["historical"] = historical
            self.state["historical_root"] = str(root)
            self.state["checks"].append(
                {
                    "case": "genuine_historical_upgrade",
                    "from": historical["head"],
                    "to": head,
                    "receipts_unchanged": True,
                    "domain_read_back": ["document", "planning", "study", "tavern"],
                }
            )
        finally:
            store.close()
        self.save()

    def crashes(self):
        probe = self

        class PostgresCrashes(Wave45ProcessRecoveryTests):
            def run_child(self, root, scenario):
                url = probe.scope(root, scenario)
                probe.upgrade(url)
                self.scenario = scenario
                print("PG crash:", scenario, flush=True)
                super().run_child(root, scenario)

            def assert_integrity(self, store):
                self.assertEqual(store.database.engine.dialect.name, "postgresql")
                with store.database.engine.connect() as connection:
                    schema = connection.execute(
                        text("SELECT current_schema()")
                    ).scalar_one()
                    self.assertTrue(schema.startswith("vibe_pg_accept_"))
                    self.assertEqual(
                        connection.execute(
                            text(
                                "SELECT count(*) FROM pg_constraint c JOIN pg_namespace n ON n.oid=c.connamespace WHERE n.nspname=current_schema() AND NOT c.convalidated"
                            )
                        ).scalar_one(),
                        0,
                    )
                probe.state["checks"].append(
                    {
                        "case": self.scenario,
                        "schema": schema,
                        "abrupt_worker_exit": 73,
                        "domain_recovery_assertions": "passed",
                        "postgres_constraints_validated": True,
                    }
                )
                probe.save()

        methods = [
            "test_document_precommit_and_postcommit_process_exit",
            "test_planning_preprovider_issued_and_committed_process_exit",
            "test_process_exit_inside_each_document_and_plan_commit_statement",
            "test_study_expired_admitted_claimed_and_issued_restart",
            "test_tavern_maximum_roster_pending_and_partial_process_restart",
        ]
        result = unittest.TextTestRunner(verbosity=1).run(
            unittest.TestSuite(PostgresCrashes(name) for name in methods)
        )
        self.state["crash_matrix_status"] = (
            "passed" if result.wasSuccessful() else "failed"
        )
        self.save()
        if not result.wasSuccessful():
            raise RuntimeError("PostgreSQL process-crash matrix failed")

    def cleanup(self):
        for scope in self.state["scopes"]:
            if not re.fullmatch(r"vibe_pg_accept_[0-9a-f]{32}", scope["schema"]):
                raise ValueError("refusing to remove a schema not owned by the probe")
            with self.admin.begin() as connection:
                connection.execute(
                    DropSchema(scope["schema"], cascade=True, if_exists=True)
                )
        self.state["owned_schemas_cleaned"] = True
        self.save()

    def study(self):
        cases = []
        for boundary in [
            "after_session",
            "after_trace",
            "after_receipt",
            "after_commit",
        ]:
            root = self.root / ("study-" + boundary)
            url = self.scope(root, "study_commit_" + boundary)
            self.upgrade(url)
            result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "tests.acceptance.postgres_study_commit_worker",
                    "--root",
                    str(root),
                    "--boundary",
                    boundary,
                ],
                cwd=SERVICE,
                capture_output=True,
                text=True,
                timeout=30,
            )
            (root / "worker.log").write_text(result.stdout + result.stderr)
            assert result.returncode == 73, result.stdout + result.stderr
            identity = json.loads((root / "identity.json").read_text())
            store = open_process_store(root)
            try:
                if boundary != "after_commit":
                    with store.database.engine.begin() as connection:
                        connection.execute(
                            text(
                                "UPDATE study_chat_operations SET execution_deadline_at='2000-01-01T00:00:00+00:00' WHERE session_id=:id"
                            ),
                            {"id": identity["session_id"]},
                        )
                operation = StudyChatOperationRepository(
                    store.database, chat_attachment_root=store.chat_attachment_root
                ).require(
                    session_id=identity["session_id"],
                    client_request_id=identity["client_request_id"],
                )
                session = StudySessionRepository(store.database).require(
                    identity["session_id"]
                )
                committed = boundary == "after_commit"
                assert operation.status.value == (
                    "committed" if committed else "uncertain"
                )
                assert (session.revision, len(session.turns)) == (
                    (1, 1) if committed else (0, 0)
                )
                case = {
                    "case": "study_commit_" + boundary,
                    "root": str(root),
                    **identity,
                    "status": operation.status.value,
                    "session_revision": session.revision,
                    "turns": len(session.turns),
                    "response_digest": operation.response_digest,
                    "abrupt_worker_exit": 73,
                }
                cases.append(case)
                self.state["checks"].append(case)
                self.save()
            finally:
                store.close()
        self.state["study_commit_cases"] = cases
        self.save()

    def cas(self):
        from fastapi import HTTPException
        from app.models.api import LearningPlanCreateRequest
        from app.persistence.document_repository import DocumentRevisionConflict
        from tests.support.planning_operations import planning_document, planning_debug

        root = self.root / "cas"
        url = self.scope(root, "concurrent_cas")
        self.upgrade(url)
        container = Container(
            Settings(
                database_url=url,
                storage_root=str(root),
                auto_migrate_local_data=False,
                plan_provider="mock",
                ocr_engine="disabled",
            )
        )
        try:
            document = planning_document(document_id="pg-cas-document")
            documents = container.document_service.repository
            documents.insert(document)
            container.store.save_item(
                "document_debug", document.id, planning_debug(document)
            )
            persona = container.persona_engine.require_persona("mentor-aurora")
            plan = container.plan_service.create_plan(
                goal=LearningPlanCreateRequest(
                    client_request_id="pg-cas-plan",
                    document_id="",
                    persona_id=persona.id,
                    objective="Study vectors",
                ),
                document=None,
                persona_name=persona.name,
                persona=persona,
            )
            plans = container.plan_service.repository
            for domain, read, write, conflict in [
                (
                    "document",
                    lambda: documents.get(document.id),
                    lambda revision, title: documents.rename_study_unit(
                        document_id=document.id,
                        study_unit_id=document.study_units[0].id,
                        title=title,
                        expected_revision=revision,
                    ),
                    DocumentRevisionConflict,
                ),
                (
                    "planning",
                    lambda: plans.require(plan.id),
                    lambda revision, title: plans.mutate(
                        plan.id,
                        lambda value: value.model_copy(update={"course_title": title}),
                        expected_revision=revision,
                    ),
                    HTTPException,
                ),
            ]:
                barrier = Barrier(2)

                def writer(title):
                    revision = read().revision
                    barrier.wait(timeout=5)
                    try:
                        write(revision, title)
                        return "committed"
                    except conflict as error:
                        if isinstance(error, HTTPException):
                            assert error.status_code == 409
                        return "conflict"

                with ThreadPoolExecutor(max_workers=2) as executor:
                    outcomes = list(executor.map(writer, ["writer-a", "writer-b"]))
                assert sorted(outcomes) == ["committed", "conflict"], outcomes
                assert read().revision == 1
                if domain == "document":
                    saved, debug = documents.get_with_debug(document.id)
                    assert saved.study_units[0].title == debug.study_units[0].title
                self.state["checks"].append(
                    {
                        "case": domain + "_concurrent_cas",
                        "outcomes": sorted(outcomes),
                        "revision": 1,
                    }
                )
            session = container.study_session_service.create_session(
                document_id="", persona_id=persona.id, study_unit_id="cas-unit"
            )
            sessions = container.study_session_repository
            barrier = Barrier(2)

            def append(label):
                first = True

                def mutation(value):
                    nonlocal first
                    if first:
                        first = False
                        barrier.wait(timeout=5)
                    value.prepared_study_unit_ids.append(label)

                return sessions.mutate(session_id=session.id, mutation=mutation)

            with ThreadPoolExecutor(max_workers=2) as executor:
                list(executor.map(append, ["writer-a", "writer-b"]))
            before = sessions.require(session.id)
            assert before.revision == 2 and set(before.prepared_study_unit_ids) == {
                "writer-a",
                "writer-b",
            }
            try:
                with container.database.session() as transaction:
                    transaction.execute(
                        update(StudySessionRow)
                        .where(StudySessionRow.id == session.id)
                        .values(status="invalid")
                    )
                    raise RuntimeError("injected rollback")
            except RuntimeError:
                pass
            assert sessions.require(session.id) == before
            self.state["checks"].append(
                {
                    "case": "study_concurrent_cas_and_rollback",
                    "revision": 2,
                    "both_writers_retained": True,
                    "rollback_exact": True,
                }
            )
            self.state["cas_session"] = {"root": str(root), "session_id": session.id}
            self.save()
        finally:
            container.close()

    @contextmanager
    def http_server(self, root):
        listener = socket.socket()
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        log = (root / "http-server.log").open("a")
        worker = subprocess.Popen(
            [
                sys.executable,
                "-m",
                "tests.acceptance.postgres_http_server",
                "--root",
                str(root),
                "--fd",
                str(listener.fileno()),
            ],
            cwd=SERVICE,
            pass_fds=(listener.fileno(),),
            stdout=log,
            stderr=log,
        )
        listener.close()
        base = f"http://127.0.0.1:{port}"

        def get(path):
            with urlopen(base + path, timeout=5) as response:
                return json.load(response)

        try:
            deadline = time.monotonic() + 12
            while True:
                try:
                    get("/health")
                    break
                except Exception:
                    if worker.poll() is not None or time.monotonic() >= deadline:
                        raise RuntimeError(
                            f"HTTP worker failed; inspect {root / 'http-server.log'}"
                        )
                    time.sleep(0.1)
            identity = get("/__acceptance__/identity")
            assert identity["dialect"] == "postgresql"
            assert identity["schema"] == (root / SCHEMA_FILE).read_text().strip()
            yield get, worker.pid
            assert get("/__acceptance__/identity")["provider_calls"] == []
        finally:
            worker.terminate()
            try:
                worker.wait(timeout=8)
            except subprocess.TimeoutExpired:
                worker.kill()
                worker.wait(timeout=5)
            log.close()

    def http(self, *, after_database_restart=False):
        historical = self.state["historical"]
        for visit in range(2):
            with self.http_server(Path(self.state["historical_root"])) as (get, pid):
                document = get(f"/documents/{historical['document_id']}/status")
                assert document["status"] == "processed"
                assert (
                    get(f"/documents/{historical['document_id']}/debug")["document_id"]
                    == historical["document_id"]
                )
                assert (
                    get("/learning-plan-operations/historical-plan-request")["status"]
                    == "committed"
                )
                assert (
                    get(
                        f"/study-sessions/{historical['session_id']}/chat-operations/historical-chat-request"
                    )["status"]
                    == "committed"
                )
                assert (
                    get(f"/tavern/rooms/{historical['room_id']}/runs")["items"][0][
                        "status"
                    ]
                    == "completed"
                )
                self.state["checks"].append(
                    {
                        "case": "application_http_restart",
                        "visit": visit,
                        "pid": pid,
                        "domains": ["document", "planning", "study", "tavern"],
                        "provider_calls": 0,
                        "after_database_restart": after_database_restart,
                    }
                )
        for case in self.state["study_commit_cases"]:
            with self.http_server(Path(case["root"])) as (get, pid):
                receipt = get(
                    f"/study-sessions/{case['session_id']}/chat-operations/{case['client_request_id']}"
                )
                session = get(f"/study-sessions/{case['session_id']}")
                assert receipt["status"] == case["status"]
                assert (
                    session["revision"] == case["session_revision"]
                    and len(session["turns"]) == case["turns"]
                )
                self.state["checks"].append(
                    {
                        "case": case["case"] + "_http",
                        "pid": pid,
                        "status": receipt["status"],
                        "provider_calls": 0,
                        "after_database_restart": after_database_restart,
                    }
                )
        self.save()

    def after_restart(self):
        # The final phase cannot certify a partial run. Each preceding phase
        # records only checks whose assertions actually completed.
        checks = {case["case"]: case for case in self.state["checks"]}
        required = (
            CRASH_CASES
            | STUDY_COMMIT_CASES
            | {
                "genuine_historical_upgrade",
                "document_concurrent_cas",
                "planning_concurrent_cas",
                "study_concurrent_cas_and_rollback",
                "harness_runtime_executions_immutable_guard",
                "harness_effect_journal_immutable_guard",
                "harness_runtime_executions_nonterminal_immutable_guard",
                "harness_effect_journal_nonterminal_immutable_guard",
            }
        )
        assert required <= checks.keys(), (
            f"missing checks: {sorted(required - checks.keys())}"
        )
        assert self.state["crash_matrix_status"] == "passed"
        assert all(
            checks[name]["domain_recovery_assertions"] == "passed"
            for name in CRASH_CASES
        )
        before_http = [
            case
            for case in self.state["checks"]
            if not case.get("after_database_restart", False)
        ]
        assert (
            len(
                {
                    case["pid"]
                    for case in before_http
                    if case["case"] == "application_http_restart"
                }
            )
            >= 2
        )
        assert {case["case"] for case in before_http} >= {
            name + "_http" for name in STUDY_COMMIT_CASES
        }
        with self.admin.connect() as connection:
            started = (
                connection.execute(text("SELECT pg_postmaster_start_time()"))
                .scalar_one()
                .isoformat()
            )
        assert started != self.state["initial_database_start"], (
            "PostgreSQL has not actually restarted"
        )
        case = self.state["cas_session"]
        with self.http_server(Path(case["root"])) as (get, pid):
            session = get(f"/study-sessions/{case['session_id']}")
            assert session["revision"] == 2 and set(
                session["prepared_study_unit_ids"]
            ) == {"writer-a", "writer-b"}
            self.state["checks"].append(
                {
                    "case": "database_restart_cas_http",
                    "pid": pid,
                    "revision": 2,
                    "provider_calls": 0,
                }
            )
        self.http(after_database_restart=True)
        self.state["restarted_database_start"] = started
        self.state["status"] = "passed"
        self.save()

    def guards(self):
        for committed in (True, False):
            root = Path(
                next(
                    case["root"]
                    for case in self.state["study_commit_cases"]
                    if (case["status"] == "committed") == committed
                )
            )
            self._guard_scope(root, terminal=committed)
        self.save()

    def _guard_scope(self, root, *, terminal):
        from app.persistence.models import (
            HarnessRuntimeExecutionRow,
            HarnessEffectJournalRow,
        )

        store = open_process_store(root)
        try:
            for model, identity, field in [
                (HarnessRuntimeExecutionRow, "trace_id", "context_payload"),
                (HarnessEffectJournalRow, "effect_id", "target_refs"),
            ]:
                with store.database.engine.connect() as connection:
                    row = dict(
                        connection.execute(
                            model.__table__.select().where(
                                (model.state == "terminal")
                                if terminal
                                else (model.state != "terminal")
                            )
                        )
                        .mappings()
                        .first()
                    )
                if not terminal:
                    # Equal JSON must remain writable; different JSON must be
                    # rejected by the immutable guard rather than a missing
                    # PostgreSQL JSON equality operator.
                    with store.database.engine.begin() as connection:
                        connection.execute(
                            update(model)
                            .where(getattr(model, identity) == row[identity])
                            .values(**{field: row[field]})
                        )
                try:
                    with store.database.engine.begin() as connection:
                        connection.execute(
                            update(model)
                            .where(getattr(model, identity) == row[identity])
                            .values(**{field: {"forged": True}})
                        )
                except DatabaseError as error:
                    assert "forbidden" in str(error)
                else:
                    raise AssertionError(
                        f"immutable mutation accepted for {model.__tablename__}"
                    )
                with store.database.engine.connect() as connection:
                    restored = dict(
                        connection.execute(
                            model.__table__.select().where(
                                getattr(model, identity) == row[identity]
                            )
                        )
                        .mappings()
                        .one()
                    )
                assert restored == row
                self.state["checks"].append(
                    {
                        "case": model.__tablename__
                        + (
                            "_immutable_guard"
                            if terminal
                            else "_nonterminal_immutable_guard"
                        ),
                        "state": row["state"],
                        "rejected": True,
                        "record_unchanged": True,
                    }
                )
        finally:
            store.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--phase",
        choices=[
            "migration",
            "crashes",
            "study",
            "cas",
            "http",
            "guards",
            "after_restart",
            "cleanup",
        ],
        required=True,
    )
    args = parser.parse_args()
    probe = Probe(args.database_url, args.root)
    try:
        getattr(probe, args.phase)()
    finally:
        probe.admin.dispose()


if __name__ == "__main__":
    main()
