"""Provider-free HTTP confirmation/restart probe using an actually parsed PDF.

Run from services/ai: PYTHONPATH=. uv run python tests/acceptance/study_unit_revision_probe.py
All state is temporary. This exercises API and persistence, not live model quality.
"""

import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory

import fitz
from app.app_factory import create_app
from app.core.bootstrap import Container
from app.core.settings import Settings
from app.models.harness import canonical_harness_digest
from app.models.study_unit_revision import StudyUnitRevisionCommittedProjectionV1
from app.persistence.models import (
    HarnessRuntimeExecutionRow,
    StudyUnitRevisionOperationRow,
)
from app.services.model_provider import MockModelProvider
from app.services.plan_tool_runtime import build_plan_tool_runtime
from fastapi.testclient import TestClient
from sqlalchemy import select


class SuggestionProvider(MockModelProvider):
    def generate_learning_plan(self, **kwargs):
        reply = super().generate_learning_plan(**kwargs)
        runtime = build_plan_tool_runtime(
            study_units=kwargs["study_units"], debug_report=kwargs["debug_report"]
        )
        result = runtime.execute_tool_call(
            {
                "id": "probe-revise",
                "type": "function",
                "function": {
                    "name": "revise_study_units",
                    "arguments": json.dumps(
                        {
                            "rationale": "Separate prefatory material",
                            "study_units": [
                                {
                                    "title": "Preface",
                                    "page_start": 1,
                                    "page_end": 1,
                                    "unit_kind": "front_matter",
                                    "include_in_plan": False,
                                },
                                {
                                    "title": "Confirmed core",
                                    "page_start": 2,
                                    "page_end": 4,
                                    "unit_kind": "chapter",
                                    "include_in_plan": True,
                                },
                            ],
                        }
                    ),
                },
            }
        )
        assert result.result["requires_confirmation"]
        assert runtime.current_study_units() == kwargs["study_units"]
        reply.study_unit_suggestions = runtime.proposed_study_units()
        return reply


class ProbeContainer(Container):
    def _build_model_provider(self, settings):
        return SuggestionProvider()


def ok(response, status=200):
    assert response.status_code == status, (response.status_code, response.text[:1000])
    return response.json()


def main():
    with fitz.open() as pdf:
        for index in range(4):
            page = pdf.new_page()
            page.insert_text((50, 50), f"Chapter {index + 1}: Vector spaces")
            page.insert_textbox(
                fitz.Rect(50, 90, 550, 720),
                "\n".join(
                    f"Example {line}: Vectors have magnitude and direction. Linear maps preserve vector addition."
                    for line in range(20)
                ),
                fontsize=10,
            )
        pdf.set_toc([[1, "Vectors", 1], [1, "Linear maps", 3]])
        payload = pdf.tobytes()
    with TemporaryDirectory(prefix="vibe-unit-revision-http-") as folder:
        root = Path(folder)
        settings = Settings(
            database_url=f"sqlite:///{root / 'app.db'}",
            storage_root=str(root / "data"),
            plan_provider="mock",
            auto_migrate_local_data=False,
        )
        app = create_app(settings=settings, container_factory=ProbeContainer)
        with TestClient(app) as client:
            document = ok(
                client.post(
                    "/documents",
                    files={"file": ("book.pdf", payload, "application/pdf")},
                )
            )
            document = ok(client.post(f"/documents/{document['id']}/process"))
            document_id = document["id"]
            plans = [
                ok(
                    client.post(
                        "/learning-plans",
                        json={
                            "document_id": document_id,
                            "persona_id": "mentor-aurora",
                            "objective": "Study the textbook",
                            "client_request_id": f"unit-probe-{i}",
                            "expected_document_updated_at": document["updated_at"],
                        },
                    )
                )
                for i in range(3)
            ]
            assert all(plan["study_units"] == document["study_units"] for plan in plans)
            previews = [
                ok(client.get(f"/learning-plans/{plan['id']}/study-unit-revision"))
                for plan in plans
            ]
            assert (
                ok(client.get(f"/documents/{document_id}/status"))["revision"]
                == document["revision"]
            )

            def decision(index, action):
                return client.post(
                    f"/learning-plans/{plans[index]['id']}/study-unit-revision/{previews[index]['preview']['operation_id']}/decision",
                    json={"decision": action},
                )

            with ThreadPoolExecutor(max_workers=2) as pool:
                responses = list(pool.map(lambda _: decision(0, "accept"), range(2)))
            assert all(response.status_code in {200, 409} for response in responses)
            accepted = ok(
                client.get(f"/learning-plans/{plans[0]['id']}/study-unit-revision")
            )
            assert accepted["status"] == "accepted"
            assert accepted["result"]["revision"] == document["revision"] + 1
            assert ok(decision(1, "accept"))["status"] == "conflict"
            assert ok(decision(2, "reject"))["status"] == "rejected"
            ok(decision(2, "accept"), 409)
            with app.state.container.database.session() as session:
                row = session.get(
                    StudyUnitRevisionOperationRow, accepted["preview"]["operation_id"]
                )
                receipt = StudyUnitRevisionCommittedProjectionV1.model_validate(
                    row.decision_receipt
                )
                trace = session.scalar(
                    select(HarnessRuntimeExecutionRow).where(
                        HarnessRuntimeExecutionRow.harness_operation_id
                        == row.harness_operation_id
                    )
                ).terminal_trace
                assert trace["commit_evidence"][
                    "payload_digest"
                ] == canonical_harness_digest(receipt)
                assert receipt.document.revision == receipt.planning_context_revision
        # A new application/container opens the same database and only queries.
        with TestClient(create_app(settings=settings)) as client:
            restored = ok(
                client.get(f"/learning-plans/{plans[0]['id']}/study-unit-revision")
            )
            current = ok(client.get(f"/documents/{document_id}/status"))
            context = ok(client.get(f"/documents/{document_id}/planning-context"))
            debug = ok(client.get(f"/documents/{document_id}/debug"))
            assert restored == accepted
            assert (
                current["revision"]
                == context["document_revision"]
                == accepted["planning_context_revision"]
            )
            assert (
                current["study_units"]
                == debug["study_units"]
                == accepted["result"]["study_units"]
            )
            assert [unit["title"] for unit in context["study_units"]] == [
                "Preface",
                "Confirmed core",
            ]
            assert (
                ok(client.get("/learning-plan-operations/unit-probe-0"))["plan"][
                    "study_units"
                ]
                == document["study_units"]
            )
        print(
            json.dumps(
                {
                    "actual_pdf_parse": "passed",
                    "conservative_plans": 3,
                    "concurrent_accept": "passed",
                    "stale_accept": "conflict",
                    "reject_then_accept": 409,
                    "atomic_receipt_trace": "passed",
                    "http_restart_readback": "passed",
                    "revision": current["revision"],
                }
            )
        )


if __name__ == "__main__":
    main()
