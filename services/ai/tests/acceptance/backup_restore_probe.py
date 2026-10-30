"""Stopped-service backup/restore acceptance with real files and HTTP processes.

Run from services/ai:
PYTHONPATH=. uv run python tests/acceptance/backup_restore_probe.py \
  --output /tmp/vibe-backup-restore/report.json

Only disposable synthetic data is used. This proves same-path SQLite/file
restoration, not desktop installation, Vault recovery or portable migration.
"""

from __future__ import annotations

import argparse
from contextlib import asynccontextmanager, contextmanager
import hashlib
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import sys
from tempfile import TemporaryDirectory
import threading
import time

import fitz
import httpx


def digest(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def json_digest(value: object) -> str:
    return digest(json.dumps(value, sort_keys=True, ensure_ascii=False).encode())


def file_manifest(root: Path) -> dict:
    return {
        str(path.relative_to(root)): {
            "bytes": path.stat().st_size,
            "sha256": digest(path.read_bytes()),
        }
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def database_state(path: Path) -> dict:
    with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchall()
        foreign_keys = connection.execute("PRAGMA foreign_key_check").fetchall()
        assert integrity == [("ok",)], integrity
        assert not foreign_keys, foreign_keys
        tables = {}
        for (name,) in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        ).fetchall():
            quoted = '"' + name.replace('"', '""') + '"'
            rows = connection.execute(f"SELECT * FROM {quoted}").fetchall()
            # Only equality/integrity evidence is emitted, not protected rows.
            tables[name] = {
                "rows": len(rows),
                "sha256": json_digest(sorted(repr(row) for row in rows)),
            }
    return {"integrity_check": "ok", "foreign_key_errors": 0, "tables": tables}


def serve(root: Path, port: int) -> None:
    # Explicit Settings never reads the user's .env or installation data.
    from app.app_factory import create_app
    from app.core.bootstrap import Container
    from app.core.settings import Settings
    from app.services.model_provider import MockModelProvider
    import uvicorn

    counts = {"planning": 0, "study": 0, "tavern": 0}
    lock = threading.Lock()

    class CountedMock(MockModelProvider):
        def generate_learning_plan(self, *args, **kwargs):
            with lock:
                counts["planning"] += 1
            return super().generate_learning_plan(*args, **kwargs)

        def generate_chat(self, *args, **kwargs):
            with lock:
                counts["study"] += 1
            return super().generate_chat(*args, **kwargs)

        def generate_tavern_actor_reply(self, *args, **kwargs):
            with lock:
                counts["tavern"] += 1
            return super().generate_tavern_actor_reply(*args, **kwargs)

    class MockOnlyContainer(Container):
        def _build_model_provider(self, settings):
            if settings.plan_provider != "mock" or settings.has_any_runtime_api_key():
                raise RuntimeError("backup_acceptance_requires_mock_without_secrets")
            return CountedMock()

    (root / "database").mkdir(parents=True, exist_ok=True)
    app = create_app(
        settings=Settings(
            database_url=f"sqlite:///{root / 'database' / 'runtime.sqlite3'}",
            storage_root=str(root / "data"),
            auto_migrate_local_data=False,
            plan_provider="mock",
            ocr_engine="disabled",
            openai_base_url="http://127.0.0.1:1/disabled",
        ),
        container_factory=MockOnlyContainer,
    )
    application_lifespan = app.router.lifespan_context

    @asynccontextmanager
    async def observed_lifespan(application):
        async with application_lifespan(application):
            yield
        # Uvicorn may re-raise SIGTERM after a successful graceful shutdown.
        # Record application cleanup before accepting that process exit status.
        (root.parent / f"stopped-{port}.json").write_text('{"closed": true}\n')

    app.router.lifespan_context = observed_lifespan

    @app.get("/__acceptance__/provider-calls")
    def provider_calls():
        with lock:
            return dict(counts)

    # Any accidental remote provider/model-resource call fails rather than bills.
    def local_network_only(event, args):
        if event == "socket.connect":
            address = args[1]
            if isinstance(address, tuple) and address[0] not in {
                "127.0.0.1",
                "::1",
            }:
                raise RuntimeError("backup_acceptance_external_network_denied")

    sys.addaudithook(local_network_only)
    uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")


@contextmanager
def backend(root: Path, output: Path, phase: str, report: dict):
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    shutdown_marker = root.parent / f"stopped-{port}.json"
    shutdown_marker.unlink(missing_ok=True)
    env = {
        key: os.environ[key]
        for key in ("PATH", "TMPDIR", "LANG", "SYSTEMROOT")
        if key in os.environ
    }
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[2])
    env["LITELLM_LOCAL_MODEL_COST_MAP"] = "True"
    with (output / f"{phase}.log").open("wb") as log:
        process = subprocess.Popen(
            [
                sys.executable,
                str(Path(__file__).resolve()),
                "--serve",
                str(root),
                "--port",
                str(port),
            ],
            env=env,
            cwd=root.parent,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        record = {"phase": phase, "pid": process.pid}
        report["processes"].append(record)
        try:
            with httpx.Client(
                base_url=f"http://127.0.0.1:{port}", timeout=30, trust_env=False
            ) as client:
                deadline = time.monotonic() + 40
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError(f"{phase}: backend exited; see {log.name}")
                    try:
                        if client.get("/health").status_code == 200:
                            break
                    except httpx.TransportError:
                        pass
                    time.sleep(0.1)
                else:
                    raise RuntimeError(f"{phase}: readiness deadline; see {log.name}")
                yield client
        finally:
            if process.poll() is None:
                process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
                record["forced_kill"] = True
            record["exit_code"] = process.returncode
            record["graceful_shutdown"] = shutdown_marker.exists()
            assert process.returncode in {0, -15} and record["graceful_shutdown"], (
                record
            )


def accepted(response: httpx.Response):
    assert response.status_code == 200, (response.status_code, response.text[:500])
    return response.json()


def textbook() -> bytes:
    with fitz.open() as pdf:
        for index in range(3):
            page = pdf.new_page()
            page.insert_textbox(
                fitz.Rect(40, 40, 550, 790),
                f"Chapter {index + 1}: Vector spaces\n\n"
                + "\n\n".join(
                    [
                        "Vectors have magnitude and direction. Addition combines vectors. "
                        "Linear transformations preserve addition and scalar multiplication."
                    ]
                    * 12
                ),
                fontsize=12,
            )
        return pdf.tobytes()


def seed(client: httpx.Client, pdf: bytes) -> dict:
    persona = accepted(
        client.post(
            "/personas",
            json={
                "name": "Backup mentor",
                "summary": "Synthetic restoration acceptance",
                "system_prompt": "Explain vectors clearly and stay in character.",
                "slots": [],
            },
        )
    )
    scene = accepted(
        client.post(
            "/scene-library",
            json={
                "expected_revision": 0,
                "scene_name": "Backup classroom",
                "scene_summary": "A synthetic classroom for restoration acceptance.",
                "selected_layer_id": "backup-layer",
                "collapsed_layer_ids": [],
                "scene_layers": [
                    {
                        "id": "backup-layer",
                        "reuse_id": "backup-reuse",
                        "title": "Classroom",
                        "scope_label": "room",
                        "summary": "A quiet classroom.",
                        "atmosphere": "Calm",
                        "rules": "Explain before changing the example.",
                        "entrance": "Enter by the door.",
                        "children": [],
                        "objects": [],
                    }
                ],
            },
        )
    )
    document = accepted(
        client.post(
            "/documents",
            files={
                "file": ("backup-vectors.pdf", pdf, "application/pdf"),
            },
        )
    )
    doc_id = document["id"]
    document = accepted(client.post(f"/documents/{doc_id}/process"))
    assert document["status"] == "processed" and document["debug_ready"]
    plan = accepted(
        client.post(
            "/learning-plans",
            json={
                "document_id": doc_id,
                "persona_id": persona["id"],
                "expected_document_updated_at": document["updated_at"],
                "client_request_id": "backup-plan-request",
                "objective": "Learn vector spaces",
                "scene_profile": scene["scene_profile"],
            },
        )
    )
    session = accepted(
        client.post(
            "/study-sessions",
            json={
                "document_id": doc_id,
                "persona_id": persona["id"],
                "plan_id": plan["id"],
                "study_unit_id": plan["schedule"][0]["unit_id"],
                "scene_profile": scene["scene_profile"],
            },
        )
    )
    sid = session["id"]
    receipt = accepted(
        client.post(
            f"/study-sessions/{sid}/chat-with-attachments",
            data={
                "client_request_id": "backup-chat-request",
                "expected_session_revision": "0",
                "message": "Explain the attached vector notes",
                "message_kind": "learner",
            },
            files={"files": ("vector-notes.pdf", pdf, "application/pdf")},
        )
    )
    assert receipt["status"] == "committed"
    session = accepted(client.get(f"/study-sessions/{sid}"))
    attachment = session["turns"][0]["learner_attachments"][0]
    room = accepted(
        client.post(
            "/tavern/rooms",
            json={
                "title": "Backup room",
                "persona_ids": [persona["id"]],
                "scene_profile": scene["scene_profile"],
                "idempotency_key": "backup-room-request",
            },
        )
    )
    rid = room["room"]["id"]
    turn = accepted(
        client.post(
            f"/tavern/rooms/{rid}/turns",
            json={
                "input": {"kind": "user_message", "content": "Discuss vectors"},
                "mode": "direct",
                "target_persona_ids": [persona["id"]],
                "expected_room_revision": room["room"]["revision"],
                "idempotency_key": "backup-tavern-request",
            },
        )
    )
    assert turn["run"]["status"] == "completed"
    current = accepted(client.get(f"/tavern/rooms/{rid}"))
    accepted(
        client.patch(
            f"/tavern/rooms/{rid}",
            json={
                "expected_revision": current["room"]["revision"],
                "status": "archived",
            },
        )
    )
    return {
        "document": doc_id,
        "plan": plan["id"],
        "session": sid,
        "scene": scene["scene_id"],
        "room": rid,
        "attachment": attachment["attachment_id"],
    }


def run(output: Path, report: dict) -> None:
    with TemporaryDirectory(prefix="vibe-backup-restore-") as temporary:
        root = Path(temporary)
        live = root / "installation"
        live.mkdir()
        pdf = textbook()
        with backend(live, output, "seed", report) as client:
            ids = seed(client, pdf)
            json_routes = [
                "/documents",
                f"/documents/{ids['document']}/status",
                f"/documents/{ids['document']}/debug",
                f"/learning-plans/{ids['plan']}",
                f"/study-sessions/{ids['session']}",
                f"/study-sessions/{ids['session']}/chat-operations/backup-chat-request",
                "/personas",
                "/scene-library",
                f"/scene-library/{ids['scene']}",
                "/runtime-settings",
                "/model-tools/config",
                "/tavern/rooms",
                f"/tavern/rooms/{ids['room']}",
                f"/tavern/rooms/{ids['room']}/runs",
                f"/tavern/rooms/{ids['room']}/run-recovery",
            ]
            expected = {route: accepted(client.get(route)) for route in json_routes}
            file_routes = [
                f"/documents/{ids['document']}/file",
                f"/study-sessions/{ids['session']}/attachments/{ids['attachment']}/file",
            ]
            for route in file_routes:
                response = client.get(route)
                assert response.status_code == 200 and response.content == pdf, route
            report["seed_provider_calls"] = accepted(
                client.get("/__acceptance__/provider-calls")
            )

        # No writer survives graceful shutdown. Copy both independently configured
        # DB and storage roots, including SQLite siblings and diagnostic files.
        manifest = file_manifest(live)
        before_db = database_state(live / "database" / "runtime.sqlite3")
        backup = root / "backup"
        shutil.copytree(live, backup)
        assert file_manifest(backup) == manifest
        # A rename removes the old configured paths. It cannot satisfy the reads
        # below. Original files and backup files must be distinct copies.
        live.rename(root / "removed-installation")
        report["backup_file_count"] = len(manifest)
        report["backup_total_bytes"] = sum(item["bytes"] for item in manifest.values())
        report["backup_manifest"] = manifest

        # Negative control: valid DB rows alone do not restore file-backed data.
        live.mkdir()
        shutil.copytree(backup / "database", live / "database")
        with backend(live, output, "database-only", report) as client:
            accepted(client.get(f"/study-sessions/{ids['session']}"))
            missing = {route: client.get(route).status_code for route in file_routes}
            assert set(missing.values()) == {404}, missing
            report["database_only_file_reads"] = missing
        shutil.rmtree(live)

        shutil.copytree(backup, live)
        assert file_manifest(live) == manifest
        assert database_state(live / "database" / "runtime.sqlite3") == before_db
        for relative in manifest:
            assert (live / relative).stat().st_ino != (backup / relative).stat().st_ino
        report["exact_copy_before_restart"] = True

        with backend(live, output, "restored", report) as client:
            comparisons = {}
            for route, saved in expected.items():
                actual = accepted(client.get(route))
                assert actual == saved, route
                comparisons[route] = {"equal": True, "sha256": json_digest(actual)}
            for route in file_routes:
                response = client.get(route)
                assert response.status_code == 200 and response.content == pdf, route
                comparisons[route] = {"equal": True, "sha256": digest(response.content)}
            assert accepted(client.get("/__acceptance__/provider-calls")) == {
                "planning": 0,
                "study": 0,
                "tavern": 0,
            }
            report["restored_reads"] = comparisons

            # Replaying the committed identity only returns its original receipt.
            replay = accepted(
                client.post(
                    f"/study-sessions/{ids['session']}/chat-with-attachments",
                    data={
                        "client_request_id": "backup-chat-request",
                        "expected_session_revision": "0",
                        "message": "Explain the attached vector notes",
                        "message_kind": "learner",
                    },
                    files={"files": ("vector-notes.pdf", pdf, "application/pdf")},
                )
            )
            assert (
                replay
                == expected[
                    f"/study-sessions/{ids['session']}/chat-operations/backup-chat-request"
                ]
            )
            assert accepted(client.get("/__acceptance__/provider-calls"))["study"] == 0
            current = accepted(client.get(f"/study-sessions/{ids['session']}"))
            assert len(current["turns"]) == 1

            new = accepted(
                client.post(
                    f"/study-sessions/{ids['session']}/chat",
                    json={
                        "client_request_id": "backup-chat-after-restore",
                        "expected_session_revision": current["revision"],
                        "message": "Continue after restoring",
                        "message_kind": "learner",
                    },
                )
            )
            assert new["status"] == "committed"
            updated = accepted(client.get(f"/study-sessions/{ids['session']}"))
            assert len(updated["turns"]) == 2
            assert updated["revision"] == current["revision"] + 1
            assert accepted(client.get("/__acceptance__/provider-calls"))["study"] == 1
            report["committed_identity_replay_provider_calls"] = 0
            report["new_chat_after_restore"] = {"turns": 2, "provider_calls": 1}
        report["final_database"] = database_state(live / "database" / "runtime.sqlite3")
        report["status"] = "passed"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("/tmp/vibe-backup-restore/report.json")
    )
    parser.add_argument("--serve", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--port", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve is not None:
        serve(args.serve, args.port)
        return
    args.output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "scope": "same-path stopped-service SQLite/file backup restore via real HTTP processes",
        "source_sha256": digest(Path(__file__).read_bytes()),
        "mock_only": True,
        "processes": [],
        "status": "failed",
        "excludes": [
            "native installation",
            "Vault",
            "cross-device migration",
            "live backup",
        ],
    }
    try:
        run(args.output.parent, report)
    finally:
        args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                key: report[key]
                for key in (
                    "status",
                    "backup_file_count",
                    "backup_total_bytes",
                    "new_chat_after_restore",
                )
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
