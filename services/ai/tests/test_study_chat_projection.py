from tests.support.api import isolated_client
import json
from types import SimpleNamespace
from unittest.mock import patch
from fastapi import FastAPI
from app.api import routes
from app.models.domain import ChatToolCallTraceRecord, StudyChatResult
from app.models.study_chat_operation import StudyChatOperationRequestPayload
from tests.support.study_chat import StudyChatOperationTestCase


app = FastAPI()
app.include_router(routes.router)


class StudyChatProjectionTests(StudyChatOperationTestCase):
    def test_historical_question_tool_traces_are_redacted_on_all_public_replays(self) -> None:
        request_payload = StudyChatOperationRequestPayload(
            message="Give me a historical question",
            message_kind="learner",
            follow_up_id="",
            hidden_message_prefix="",
            expected_session_revision=0,
            attachments=[],
        )
        operation = self.operations.admit(
            session_id="session-invalid-reply",
            client_request_id="historical-trace-request-0001",
            request_payload=request_payload,
        )
        running, claimed = self.operations.claim(
            operation_id=operation.operation_id,
            timeout_seconds=30,
        )
        self.assertTrue(claimed)
        self.operations.mark_provider_started(
            operation_id=running.operation_id,
            execution_token=running.execution_token,
        )
        result = StudyChatResult(
            reply="Historical question trace",
            citations=[],
            character_events=[],
            tool_calls=[
                ChatToolCallTraceRecord(
                    tool_call_id="historical-mcq",
                    tool_name="ask_multiple_choice_question",
                    arguments_json="{}",
                    result_summary="question",
                    result_json=json.dumps(
                        {
                            "ok": True,
                            "question_type": "multiple_choice",
                            "question": "Pick one",
                            "answer_key": "A",
                            "explanation": "private MCQ explanation",
                        }
                    ),
                ),
                ChatToolCallTraceRecord(
                    tool_call_id="historical-fill",
                    tool_name="ask_fill_blank_question",
                    arguments_json="{}",
                    result_summary="question",
                    result_json=json.dumps(
                        {
                            "ok": True,
                            "question_type": "fill_blank",
                            "question": "Fill one",
                            "answer": "private fill answer",
                            "explanation": "private fill explanation",
                        }
                    ),
                ),
            ],
        )
        _, stored_payload = self.sessions.commit_chat_operation_turn(
            operation_id=running.operation_id,
            execution_token=running.execution_token,
            learner_message=request_payload.message,
            learner_message_kind=request_payload.message_kind,
            learner_attachments=[],
            result=result,
            prepared_study_unit_id=None,
            completed_follow_up_id="",
            cancel_pending_follow_ups=True,
            prepared_effect_batch=None,
            build_response_payload=lambda session: {
                **result.model_dump(mode="json"),
                "session": session.model_dump(mode="json"),
            },
        )
        self.assertIn("answer_key", stored_payload["tool_calls"][0]["result_json"])
        self.assertIn("answer", stored_payload["tool_calls"][1]["result_json"])
        session_service = SimpleNamespace(require_session=self.sessions.require)

        with (
            patch.object(self.container, "study_chat_operation_repository", self.operations),
            patch.object(self.container, "study_session_service", session_service),
            isolated_client(app, self.container) as client,
        ):
            responses = [
                client.get("/study-sessions/session-invalid-reply"),
                client.get(
                    "/study-sessions/session-invalid-reply/chat-operations/"
                    "historical-trace-request-0001"
                ),
                client.post(
                    "/study-sessions/session-invalid-reply/chat",
                    json={
                        "client_request_id": "historical-trace-request-0001",
                        "expected_session_revision": 0,
                        "message": request_payload.message,
                        "message_kind": request_payload.message_kind,
                        "follow_up_id": "",
                        "hidden_message_prefix": "",
                    },
                ),
            ]

        for response in responses:
            self.assertEqual(response.status_code, 200, response.text)
        turn_payloads = [
            responses[0].json()["turns"][0],
            responses[1].json()["result"]["session"]["turns"][0],
            responses[2].json()["result"]["session"]["turns"][0],
        ]
        top_level_traces = [
            responses[1].json()["result"]["tool_calls"],
            responses[2].json()["result"]["tool_calls"],
        ]
        for traces in [
            *(turn["tool_calls"] for turn in turn_payloads),
            *top_level_traces,
        ]:
            self.assertEqual(len(traces), 2)
            for trace in traces:
                public_result = json.loads(trace["result_json"])
                for private_key in (
                    "answer",
                    "answer_key",
                    "accepted_answers",
                    "grading_spec",
                    "correct_option_key",
                    "explanation",
                ):
                    self.assertNotIn(private_key, public_result)
