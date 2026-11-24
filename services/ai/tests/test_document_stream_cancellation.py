import json
from contextlib import nullcontext
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient

from app.app_factory import create_app
from app.core.settings import Settings
from app.services.stream_interrupts import StreamInterruptedError


class DocumentStreamCancellationTests(TestCase):
    def test_cancel_after_commit_keeps_committed_terminal(self):
        self._assert_terminal_matches_commit(cancel_before=False)

    def test_cancel_before_commit_preserves_checkpoint_only(self):
        self._assert_terminal_matches_commit(cancel_before=True)

    def test_committed_checkpoint_replay_respects_transport_cancellation(self):
        with TemporaryDirectory() as tmp, fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((72, 72), "Vector spaces and linear transformations.")
            app = create_app(
                settings=Settings(
                    database_url=f"sqlite:///{tmp}/test.db",
                    storage_root=str(Path(tmp) / "data"),
                    auto_migrate_local_data=False,
                    plan_provider="mock",
                    ocr_engine="disabled",
                )
            )
            with TestClient(app) as client:
                upload = client.post(
                    "/documents",
                    files={"file": ("vectors.pdf", pdf.tobytes(), "application/pdf")},
                )
                document_id = upload.raise_for_status().json()["id"]
                path = f"/documents/{document_id}"
                service = app.state.container.document_service

                def interrupt():
                    raise StreamInterruptedError("stream_interrupted")

                with self.assertRaises(StreamInterruptedError):
                    service.process_document(document_id, before_commit=interrupt)
                source = client.get(path + "/checkpoint").raise_for_status().json()
                payload = {"resume_from_operation_id": source["operation_id"]}
                client.post(path + "/process", json=payload).raise_for_status()
                committed = client.get(path + "/checkpoint").raise_for_status().json()
                self.assertEqual(committed["operation_status"], "committed")
                read_back = service._resume_read_back
                process = service.process_document

                for admission_race, cancel_before in product((True, False), repeat=2):
                    with self.subTest(
                        admission_race=admission_race, cancel_before=cancel_before
                    ):
                        replies = []

                        def cancel():
                            report = client.get(path + "/process-events")
                            stream_id = report.raise_for_status().json()["operation_id"]
                            response = client.post(f"/stream-runs/{stream_id}/cancel")
                            replies.append(
                                response.raise_for_status().json()["cancelled"]
                            )

                        def read_then_cancel(operation_id):
                            result = read_back(operation_id)
                            if cancel_before:
                                cancel()
                            return result

                        def process_then_cancel(*args, **kwargs):
                            result = process(*args, **kwargs)
                            if not cancel_before:
                                cancel()
                            return result

                        # Simulate the child becoming visible only at admission.
                        child_lookup = (
                            patch.object(
                                service.checkpoints, "resume_child", return_value=None
                            )
                            if admission_race
                            else nullcontext()
                        )
                        with (
                            child_lookup,
                            patch.object(
                                service,
                                "_resume_read_back",
                                side_effect=read_then_cancel,
                            ),
                            patch.object(
                                service,
                                "process_document",
                                side_effect=process_then_cancel,
                            ),
                        ):
                            response = client.post(
                                path + "/process/stream", json=payload
                            )
                        events = [
                            json.loads(line)
                            for line in response.raise_for_status().text.splitlines()
                        ]
                        self.assertEqual(replies, [cancel_before])
                        self.assertEqual(
                            [event["stage"] for event in events],
                            [
                                "stream_cancelled"
                                if cancel_before
                                else "stream_completed"
                            ],
                        )
                        terminal = events[0]
                        evidence = terminal["terminal_evidence"]
                        if cancel_before:
                            self.assertEqual(evidence["commit_status"], "not_committed")
                            self.assertEqual(
                                evidence["domain_operation_status"], "not_admitted"
                            )
                            self.assertEqual(evidence["domain_operation_id"], "")
                            self.assertIsNone(terminal["committed_projection"])
                        else:
                            self.assertEqual(evidence["commit_status"], "committed")
                            self.assertEqual(
                                evidence["domain_operation_id"],
                                committed["operation_id"],
                            )
                            projection = {
                                key: value
                                for key, value in terminal[
                                    "committed_projection"
                                ].items()
                                if key != "harness_trace"
                            }
                            self.assertEqual(projection, committed["result"])
                        current = (
                            client.get(path + "/checkpoint").raise_for_status().json()
                        )
                        self.assertEqual(current, committed)

    def _assert_terminal_matches_commit(self, *, cancel_before: bool):
        with TemporaryDirectory() as tmp, fitz.open() as pdf:
            page = pdf.new_page()
            page.insert_text((72, 72), "Vector spaces and linear transformations.")
            app = create_app(
                settings=Settings(
                    database_url=f"sqlite:///{tmp}/test.db",
                    storage_root=str(Path(tmp) / "data"),
                    auto_migrate_local_data=False,
                    plan_provider="mock",
                    ocr_engine="disabled",
                )
            )
            with TestClient(app) as client:
                upload = client.post(
                    "/documents",
                    files={"file": ("vectors.pdf", pdf.tobytes(), "application/pdf")},
                )
                upload.raise_for_status()
                path = f"/documents/{upload.json()['id']}"
                container = app.state.container
                registry = container.stream_interrupt_registry
                service = container.document_service
                original_create = registry.create
                mirror = service._mirror_current_document_projection
                process = service.process_document
                stream_ids = []
                replies = []

                def track(**kwargs):
                    handle = original_create(**kwargs)
                    stream_ids.append(handle.stream_id)
                    return handle

                def cancel():
                    response = client.post(f"/stream-runs/{stream_ids[0]}/cancel")
                    response.raise_for_status()
                    replies.append(response.json()["cancelled"])

                def cancel_before_fence(*args, **kwargs):
                    fence = kwargs["before_commit"]

                    def cancel_then_fence():
                        cancel()
                        fence()

                    return process(
                        *args, **{**kwargs, "before_commit": cancel_then_fence}
                    )

                def cancel_after_commit(document_id, *, debug_report=None):
                    mirror(document_id, debug_report=debug_report)
                    if debug_report is not None:
                        cancel()

                window = (
                    patch.object(
                        service, "process_document", side_effect=cancel_before_fence
                    )
                    if cancel_before
                    else patch.object(
                        service,
                        "_mirror_current_document_projection",
                        side_effect=cancel_after_commit,
                    )
                )
                with patch.object(registry, "create", side_effect=track), window:
                    response = client.post(path + "/process/stream")
                response.raise_for_status()
                events = [json.loads(line) for line in response.text.splitlines()]
                terminal = events[-1]
                terminal_stages = {
                    "stream_completed",
                    "stream_cancelled",
                    "stream_error",
                }
                self.assertEqual(
                    sum(event["stage"] in terminal_stages for event in events), 1
                )
                self.assertEqual(
                    terminal["stage"],
                    "stream_cancelled" if cancel_before else "stream_completed",
                )
                self.assertEqual(replies, [cancel_before])
                self.assertEqual(
                    terminal["terminal_evidence"]["commit_status"],
                    "not_committed" if cancel_before else "committed",
                )
                checkpoint = client.get(path + "/checkpoint")
                checkpoint.raise_for_status()
                receipt = checkpoint.json()
                self.assertEqual(
                    receipt["projection_state"],
                    "checkpoint_only" if cancel_before else "committed",
                )
                status = client.get(path + "/status")
                status.raise_for_status()
                if cancel_before:
                    self.assertNotEqual(status.json()["status"], "processed")
                    self.assertIsNone(receipt["result"])
                else:
                    self.assertEqual(status.json()["status"], "processed")
                    self.assertEqual(status.json(), receipt["result"])
