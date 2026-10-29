"""Generate genuinely old persisted records with an archived application tree."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-tree", type=Path, required=True)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--export-only", action="store_true")
    args = parser.parse_args()
    sys.path.insert(0, str(args.source_tree / "services/ai"))
    import fitz
    import inspect
    from alembic import command
    from alembic.config import Config
    from fastapi.testclient import TestClient
    from sqlalchemy import text, create_engine, MetaData, Table, select, JSON, null
    from app.app_factory import create_app
    from app.core.settings import Settings
    from app.models.persona_generation import (
        PersonaGenerationInputManifest,
        PersonaGenerationProposalV1,
    )
    from app.models.scene_generation import (
        SceneGenerationInputManifest,
        SceneGenerationProposalV1,
    )

    assert Path(inspect.getfile(create_app)).is_relative_to(args.source_tree)
    target_url = os.environ["DATABASE_URL"]
    source_url = f"sqlite:///{args.root / 'historical-source.db'}"
    os.environ["DATABASE_URL"] = source_url
    config = Config(str(args.source_tree / "services/ai/alembic.ini"))
    config.set_main_option(
        "script_location", str(args.source_tree / "services/ai/alembic")
    )
    command.upgrade(config, "head")
    settings = Settings(
        database_url=source_url,
        storage_root=str(args.root),
        auto_migrate_local_data=False,
        plan_provider="mock",
        ocr_engine="disabled",
    )
    app = create_app(settings=settings)

    def checked(response):
        assert response.status_code == 200, response.text
        return response.json()

    with TestClient(app) as client:
        persona = checked(client.get("/personas"))["items"][0]
        with fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((72, 80), "Chapter 1 Vector spaces", fontsize=18)
            for index in range(12):
                page.insert_text(
                    (72, 110 + index * 20),
                    "Vectors can be added and multiplied by scalars. Linear maps preserve these operations.",
                )
            content = pdf.tobytes()
        document = checked(
            client.post(
                "/documents",
                files={"file": ("historical.pdf", content, "application/pdf")},
            )
        )
        processed = checked(
            client.post(f"/documents/{document['id']}/process", json={})
        )
        plan = checked(
            client.post(
                "/learning-plans",
                json=dict(
                    document_id=document["id"],
                    persona_id=persona["id"],
                    objective="Understand vectors",
                    client_request_id="historical-plan-request",
                    expected_document_updated_at=processed["updated_at"],
                ),
            )
        )
        session = checked(
            client.post(
                "/study-sessions",
                json=dict(
                    document_id=document["id"],
                    plan_id=plan["id"],
                    persona_id=persona["id"],
                    study_unit_id=plan["study_units"][0]["id"],
                ),
            )
        )
        chat = checked(
            client.post(
                f"/study-sessions/{session['id']}/chat",
                json=dict(
                    client_request_id="historical-chat-request",
                    expected_session_revision=session["revision"],
                    message="Explain vectors",
                ),
            )
        )
        assert chat["status"] == "committed", chat
        room = checked(
            client.post(
                "/tavern/rooms",
                json=dict(
                    title="Historical room",
                    persona_ids=[persona["id"]],
                    idempotency_key="historical-room",
                ),
            )
        )
        turn = checked(
            client.post(
                f"/tavern/rooms/{room['room']['id']}/turns",
                json=dict(
                    input={"kind": "user_message", "content": "A historical topic"},
                    mode="direct",
                    target_persona_ids=[persona["id"]],
                    idempotency_key="historical-turn",
                    expected_room_revision=0,
                ),
            )
        )
        assert turn["run"]["status"] == "completed", turn
        container = app.state.container

        def generate_persona(protected):
            result = container.model_provider.generate_persona_cards_from_keywords(
                keywords=str(protected["input_text"]),
                count=protected.get("count"),
            )
            return PersonaGenerationProposalV1.model_validate(
                {
                    "request_kind": "card_batch",
                    "used_model": result.get("used_model", ""),
                    "used_web_search": result.get("used_web_search", False),
                    "summary": result.get("summary", ""),
                    "relationship": result.get("relationship", ""),
                    "learner_address": result.get("learner_address", ""),
                    "cards": result["cards"],
                },
                strict=True,
            )

        container.harness_proposal_runtime.run_persona(
            manifest=PersonaGenerationInputManifest(
                request_kind="card_batch",
                mode="keywords",
                requested_count=2,
                input_char_count=len("historical mentor"),
            ),
            protected_input={
                "mode": "keywords",
                "input_text": "historical mentor",
                "count": 2,
            },
            generate=generate_persona,
        )

        def generate_scene(protected):
            result = container.model_provider.generate_scene_tree_from_keywords(
                keywords=str(protected["input_text"]),
                layer_count=protected.get("layer_count"),
            )
            return SceneGenerationProposalV1.model_validate(
                {
                    "used_model": result.get("used_model", ""),
                    "used_web_search": result.get("used_web_search", False),
                    "proposal": result["proposal"],
                },
                strict=True,
            )

        container.harness_proposal_runtime.run_scene(
            manifest=SceneGenerationInputManifest(
                mode="keywords",
                requested_layer_count=2,
                input_char_count=len("historical classroom"),
            ),
            protected_input={
                "mode": "keywords",
                "input_text": "historical classroom",
                "layer_count": 2,
            },
            generate=generate_scene,
        )
        database = app.state.container.database
        with database.engine.connect() as connection:
            old_head = connection.execute(
                text("SELECT version_num FROM alembic_version")
            ).scalar_one()
            receipts = {}
            for table, key in [
                ("document_process_operations", "document_digest"),
                ("learning_plan_operations", "committed_projection_digest"),
                ("study_chat_operations", "response_digest"),
            ]:
                receipts[table] = list(
                    connection.execute(text(f"SELECT {key} FROM {table}")).scalars()
                )
        payload = {
            "head": old_head,
            "document_id": document["id"],
            "plan_id": plan["id"],
            "session_id": session["id"],
            "room_id": room["room"]["id"],
            "run_id": turn["run"]["id"],
            "persona_id": persona["id"],
            "receipts": receipts,
            "payload_digests": {
                name: hashlib.sha256(
                    json.dumps(
                        value, ensure_ascii=False, sort_keys=True, separators=(",", ":")
                    ).encode()
                ).hexdigest()
                for name, value in [
                    ("document", processed),
                    ("chat_receipt", chat),
                    ("tavern_turn", turn),
                ]
            },
        }
        with database.engine.connect() as connection:
            artifacts = []
            for artifact in connection.execute(
                text(
                    "SELECT artifact_id, artifact_type, contract_name, "
                    "contract_version, payload_digest, payload, expires_at, "
                    "registered_at FROM harness_artifacts ORDER BY artifact_id"
                )
            ).mappings():
                grants = list(
                    connection.execute(
                        text(
                            "SELECT s.grant_id, s.permission, "
                            "g.harness_operation_id, g.expires_at "
                            "FROM harness_artifact_grant_scopes s "
                            "JOIN harness_artifact_grants g "
                            "ON g.grant_id=s.grant_id "
                            "WHERE s.artifact_id=:artifact_id "
                            "ORDER BY s.grant_id"
                        ),
                        {"artifact_id": artifact["artifact_id"]},
                    ).mappings()
                )
                artifacts.append(
                    {
                        "artifact_id": artifact["artifact_id"],
                        "artifact_type": artifact["artifact_type"],
                        "contract_name": artifact["contract_name"],
                        "contract_version": artifact["contract_version"],
                        "payload_digest": artifact["payload_digest"],
                        "payload_base64": base64.b64encode(artifact["payload"]).decode(
                            "ascii"
                        ),
                        "expires_at": artifact["expires_at"],
                        "registered_at": artifact["registered_at"],
                        "grants": [dict(grant) for grant in grants],
                    }
                )
            payload["historical_artifacts"] = artifacts
        if args.export_only:
            payload["seed_backend"] = "old-version SQLite application export"
            (args.root / "historical-identities.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
            )
            return
        target = create_engine(target_url)
        try:
            metadata = MetaData()
            with database.engine.connect() as source, target.begin() as destination:
                metadata.reflect(bind=destination)
                for table in metadata.sorted_tables:
                    if table.name == "alembic_version":
                        continue
                    original = Table(table.name, MetaData(), autoload_with=source)
                    nullable_json = [
                        column
                        for column in original.columns
                        if column.nullable and isinstance(column.type, JSON)
                    ]
                    values = source.execute(
                        select(
                            original,
                            *(
                                column.is_(None).label("sql_null_" + column.name)
                                for column in nullable_json
                            ),
                        )
                    ).mappings()
                    rows = []
                    for value in values:
                        row = {
                            column.name: value[column.name]
                            for column in original.columns
                        }
                        for column in nullable_json:
                            if value["sql_null_" + column.name]:
                                row[column.name] = null()
                        rows.append(row)
                    self_refs = [
                        foreign_key.parent.key
                        for foreign_key in table.foreign_keys
                        if foreign_key.column.table.name == table.name
                    ]
                    primary_key = next(iter(table.primary_key.columns)).key
                    identities = {row[primary_key] for row in rows}
                    inserted = set()
                    while rows:
                        available = [
                            row
                            for row in rows
                            if all(
                                row[column] is None
                                or row[column] not in identities
                                or row[column] in inserted
                                for column in self_refs
                            )
                        ]
                        assert available, f"unresolved self-reference in {table.name}"
                        for row in available:
                            destination.execute(table.insert().values(**row))
                            inserted.add(row[primary_key])
                            rows.remove(row)
        finally:
            target.dispose()
        payload["seed_backend"] = (
            "old-version SQLite; exact rows restored into old Alembic PostgreSQL schema"
        )
        (args.root / "historical-identities.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        )


if __name__ == "__main__":
    main()
