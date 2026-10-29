"""Abrupt exits inside the real Study transaction, using the selected PG scope."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from sqlalchemy import event

from app.core.bootstrap import Container
from app.core.settings import Settings
from tests.support.process_database import process_database_url


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--boundary", required=True)
    args = parser.parse_args()
    container = Container(
        Settings(
            database_url=process_database_url(args.root),
            storage_root=str(args.root),
            auto_migrate_local_data=False,
            plan_provider="mock",
            ocr_engine="disabled",
        )
    )
    session = container.study_session_service.create_session(
        document_id="", persona_id="mentor-aurora", study_unit_id="synthetic-unit"
    )
    (args.root / "identity.json").write_text(
        json.dumps(
            {"session_id": session.id, "client_request_id": "pg-study-commit-request"}
        )
    )
    original = container.study_session_repository.commit_chat_operation_turn
    active = False

    def after_statement(_connection, _cursor, _statement, _parameters, context, _many):
        table = getattr(getattr(context.compiled, "statement", None), "table", None)
        targets = {
            "after_session": "study_sessions",
            "after_trace": "harness_runtime_executions",
            "after_receipt": "study_chat_operations",
        }
        if (
            active
            and context.isupdate
            and table is not None
            and table.name == targets.get(args.boundary)
        ):
            os._exit(73)

    def commit(**kwargs):
        global active
        active = True
        result = original(**kwargs)
        if args.boundary == "after_commit":
            os._exit(73)
        active = False
        return result

    event.listen(container.database.engine, "after_cursor_execute", after_statement)
    container.study_session_repository.commit_chat_operation_turn = commit
    container.study_chat_application().admit(
        session_id=session.id,
        client_request_id="pg-study-commit-request",
        expected_session_revision=0,
        message="Explain a vector",
        message_kind="learner",
        follow_up_id="",
        hidden_message_prefix="",
    )
    raise AssertionError("Study transaction crash boundary was not reached")
