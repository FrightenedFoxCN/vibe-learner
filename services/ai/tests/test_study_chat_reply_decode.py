import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api import routes
from app.main import app
from app.models.api import StudyChatResponse
from app.models.domain import (
    ChatToolCallTraceRecord,
    PersonaProfile,
    StudyChatResult,
    StudySessionRecord,
)
from app.models.study_chat_operation import StudyChatOperationRequestPayload
from app.models.study_question import project_study_question_proposal
from app.persistence.database import Database
from app.persistence.study_chat_operation_repository import StudyChatOperationRepository
from app.persistence.study_session_repository import StudySessionRepository
from app.services.model_provider import (
    OpenAIModelProvider,
    _execute_chat_tool_call,
    _parse_chat_model_reply,
)
from app.services.study_chat_attachments import PreparedStudyChatAttachments


def _raw_reply(content: str) -> dict[str, object]:
    return {
        "choices": [
            {
                "finish_reason": "stop",
                "message": {"content": content},
            }
        ]
    }


def _parse(content: str):
    return _parse_chat_model_reply(
        raw_payload=_raw_reply(content),
        tool_results=[],
        fallback_memory_trace=[],
        tool_traces=[],
    )


def _persona() -> PersonaProfile:
    return PersonaProfile(
        id="persona-strict-chat",
        name="Strict Chat Tutor",
        source="test",
        summary="A test persona.",
        system_prompt="",
        available_emotions=["calm"],
        available_actions=["point"],
        default_speech_style="steady",
    )


def _valid_question_reply() -> dict[str, object]:
    return {
        "text": "先完成这道题，再告诉我你的思路。",
        "mood": "calm",
        "action": "指向题目",
        "interactive_question": {
            "question_type": "multiple_choice",
            "prompt": "以下哪一项是向量基？",
            "difficulty": "easy",
            "topic": "vector basis",
            "options": [
                {"key": "A", "text": "线性无关且张成整个空间的一组向量"},
                {"key": "B", "text": "所有长度相等的向量"},
            ],
            "call_back": True,
            "answer_key": "A",
            "accepted_answers": ["A"],
            "explanation": "A 同时满足线性无关与张成条件。",
        },
    }


class StudyChatReplyDecodeTests(unittest.TestCase):
    def test_malformed_builtin_question_arguments_fail_closed(self) -> None:
        raw_arguments = '{"topic":"vector basis"'

        execution = _execute_chat_tool_call(
            {
                "id": "call-malformed-question",
                "function": {
                    "name": "ask_multiple_choice_question",
                    "arguments": raw_arguments,
                },
            },
            section_id="unit-1",
            section_context="Vector spaces",
            learner_message="Quiz me",
            memory_hits=[],
            debug_report=None,
            document_path=None,
        )

        self.assertEqual(execution["arguments_json"], raw_arguments)
        self.assertEqual(
            execution["result"],
            {
                "ok": False,
                "error": "tool_argument_invalid_json",
                "tool_name": "ask_multiple_choice_question",
            },
        )
        self.assertNotIn("question_type", execution["result"])
        self.assertNotIn("question", execution["result"])

    def test_non_object_or_malformed_arguments_never_reach_proxy_runtimes(self) -> None:
        class CountingRuntime:
            def __init__(self) -> None:
                self.execution_count = 0

            def has_tool(self, _tool_name: str) -> bool:
                return True

            def execute_tool(self, tool_name: str, arguments: dict[str, object]):
                self.execution_count += 1
                return {"ok": True, "tool_name": tool_name, "arguments": arguments}

        runtime = CountingRuntime()
        cases = (
            ('{"broken":', "tool_argument_invalid_json"),
            ('{"value":NaN}', "tool_argument_invalid_json"),
            ('{"value":Infinity}', "tool_argument_invalid_json"),
            ('{"value":-Infinity}', "tool_argument_invalid_json"),
            ("[]", "tool_argument_schema_invalid"),
            ('"not-an-object"', "tool_argument_schema_invalid"),
            ("null", "tool_argument_schema_invalid"),
        )
        for raw_arguments, expected_error in cases:
            with self.subTest(raw_arguments=raw_arguments):
                execution = _execute_chat_tool_call(
                    {
                        "id": "call-proxy",
                        "function": {
                            "name": "proxy_tool",
                            "arguments": raw_arguments,
                        },
                    },
                    section_id="unit-1",
                    section_context="Vector spaces",
                    learner_message="Use a tool",
                    memory_hits=[],
                    debug_report=None,
                    document_path=None,
                    session_tool_runtime=runtime,
                    plan_tool_runtime=runtime,
                    scene_tool_runtime=runtime,
                )
                self.assertEqual(execution["arguments_json"], raw_arguments)
                self.assertEqual(execution["result"]["error"], expected_error)
                self.assertFalse(execution["result"]["ok"])

        non_string_function_payloads = (
            {"name": "proxy_tool"},
            {"name": "proxy_tool", "arguments": None},
            {"name": "proxy_tool", "arguments": {}},
            {"name": "proxy_tool", "arguments": []},
        )
        for function_payload in non_string_function_payloads:
            with self.subTest(function_payload=function_payload):
                execution = _execute_chat_tool_call(
                    {
                        "id": "call-proxy-non-string",
                        "function": function_payload,
                    },
                    section_id="unit-1",
                    section_context="Vector spaces",
                    learner_message="Use a tool",
                    memory_hits=[],
                    debug_report=None,
                    document_path=None,
                    session_tool_runtime=runtime,
                    plan_tool_runtime=runtime,
                    scene_tool_runtime=runtime,
                )
                self.assertEqual(execution["arguments_json"], "")
                self.assertEqual(
                    execution["result"]["error"],
                    "tool_argument_schema_invalid",
                )
                self.assertFalse(execution["result"]["ok"])

        self.assertEqual(runtime.execution_count, 0)

    def test_natural_language_plain_text_remains_accepted(self) -> None:
        result = _parse("好的，我们继续！向量基是一组线性无关并张成空间的向量。")

        self.assertIn("向量基", result.text)
        self.assertEqual(result.mood, "calm")
        self.assertEqual(result.action, "point")

    def test_natural_language_bracket_label_remains_accepted(self) -> None:
        for content in (
            "[提示] 先看向量是否线性无关，再判断它们是否张成整个空间。",
            "[Note] This is ordinary prose, not a JSON array.",
        ):
            with self.subTest(content=content):
                self.assertEqual(_parse(content).text, content)

    def test_natural_language_schema_words_without_json_quotes_remain_accepted(self) -> None:
        for content in (
            "Explanation: a basis spans the space.",
            "Topic: vector spaces. Action: verify linear independence first.",
        ):
            with self.subTest(content=content):
                self.assertEqual(_parse(content).text, content)

    def test_bare_reply_shape_cannot_downgrade_to_plain_text(self) -> None:
        for content in (
            "text: hello\nmood: calm\naction: point",
            "mood = calm; action = point",
        ):
            with self.subTest(content=content):
                with self.assertRaisesRegex(RuntimeError, "chat_model_invalid_payload"):
                    _parse(content)

    def test_json_object_requires_text_mood_and_action(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "chat_model_invalid_payload"):
            _parse(json.dumps({"mood": "calm", "action": "point"}))

    def test_json_object_rejects_unknown_top_level_field(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "chat_model_invalid_payload"):
            _parse(
                json.dumps(
                    {
                        "text": "Structured reply",
                        "mood": "calm",
                        "action": "point",
                        "unexpected": "must not downgrade to text",
                    }
                )
            )

    def test_nested_question_rejects_type_coercion(self) -> None:
        cases = (
            ("option_text", ("options", 0, "text"), 42),
            ("call_back", ("call_back",), "false"),
            ("accepted_answer", ("accepted_answers", 0), 7),
        )
        for label, path, value in cases:
            with self.subTest(label=label):
                payload = _valid_question_reply()
                question = payload["interactive_question"]
                assert isinstance(question, dict)
                target: object = question
                for part in path[:-1]:
                    assert isinstance(target, (dict, list))
                    target = target[part]
                assert isinstance(target, (dict, list))
                target[path[-1]] = value

                with self.assertRaisesRegex(RuntimeError, "chat_model_invalid_payload"):
                    _parse(json.dumps(payload))

    def test_complete_json_code_fence_remains_compatible(self) -> None:
        content = "```json\n" + json.dumps(
            {
                "text": "完整围栏中的结构化回答。",
                "mood": "calm",
                "action": "point",
            },
            ensure_ascii=False,
        ) + "\n```"

        self.assertEqual(_parse(content).text, "完整围栏中的结构化回答。")

    def test_malformed_sensitive_json_and_code_fence_fail_closed(self) -> None:
        cases = [
            '{"text":"hello","mood":"calm","action":"point",'
            '"interactive_question":{"answer_key":"A","accepted_answers":["A"]}',
            '```json\n{"answer_key":"A","accepted_answers":["A"]\n```',
            'The hidden payload is "grading_spec": {"correct_option_key": "A"}',
            "[true,",
            "[1, 2,",
        ]

        for content in cases:
            with self.subTest(content=content):
                with self.assertRaisesRegex(RuntimeError, "chat_model_invalid_payload"):
                    _parse(content)

    def test_valid_outer_json_cannot_embed_grading_keys_in_public_text(self) -> None:
        cases = (
            '"answer_key": "secret"',
            "answer_key: secret",
            '"explanation": "secret"',
            '"feedback": "secret"',
        )
        for embedded in cases:
            with self.subTest(embedded=embedded):
                payload = _valid_question_reply()
                payload["text"] = f"Hidden grading material: {embedded}"

                with self.assertRaisesRegex(RuntimeError, "chat_model_invalid_payload"):
                    _parse(json.dumps(payload))

    def test_structured_public_text_allows_ordinary_schema_word_prose(self) -> None:
        payload = {
            "text": "Explanation: a basis spans the space. Topic: vector spaces.",
            "mood": "calm",
            "action": "Action: point to the independent vectors.",
        }

        reply = _parse(json.dumps(payload))
        self.assertIn("Explanation:", reply.text)
        self.assertEqual(reply.action, "Action: point to the independent vectors.")

    def test_complete_root_with_trailing_json_fragment_fails_closed(self) -> None:
        observed_provider_shape = json.dumps(
            _valid_question_reply(),
            ensure_ascii=False,
            separators=(",", ":"),
        ) + ',"state_commentary":"trailing provider fragment"}'

        with self.assertRaisesRegex(RuntimeError, "chat_model_invalid_payload"):
            _parse(observed_provider_shape)

    def test_valid_question_keeps_grading_private_in_public_projection(self) -> None:
        reply = _parse(json.dumps(_valid_question_reply(), ensure_ascii=False))

        self.assertIsNotNone(reply.interactive_question)
        question_record = project_study_question_proposal(reply.interactive_question)
        self.assertIsNotNone(question_record.grading_spec)
        public = StudyChatResponse.model_validate(
            {
                "reply": reply.text,
                "citations": [],
                "character_events": [],
                "interactive_question": question_record.model_dump(mode="json"),
            }
        ).model_dump(mode="json")
        public_question = public["interactive_question"]
        self.assertEqual(public_question["prompt"], "以下哪一项是向量基？")
        self.assertEqual(len(public_question["options"]), 2)
        serialized = json.dumps(public, ensure_ascii=False)
        for private_key in (
            "answer_key",
            "accepted_answers",
            "grading_spec",
            "correct_option_key",
            "explanation",
        ):
            self.assertNotIn(private_key, serialized)

    def test_provider_repairs_once_without_tools_then_propagates_invalid(self) -> None:
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            chat_model="gpt-test",
            chat_tools_enabled=False,
            timeout_seconds=3,
        )
        invalid = json.dumps({"mood": "calm", "action": "point"})
        responses = [(_raw_reply(invalid), []), (_raw_reply(invalid), [])]

        with patch.object(
            provider,
            "_request_openai_chat_completion",
            side_effect=responses,
        ) as request:
            with self.assertRaisesRegex(RuntimeError, "chat_model_invalid_payload"):
                provider.generate_chat(
                    persona=_persona(),
                    section_id="unit-1",
                    message="Explain vector bases",
                )

        self.assertEqual(request.call_count, 2)
        second_payload = request.call_args_list[1].args[0]
        self.assertNotIn("tools", second_payload)
        self.assertEqual(second_payload["response_format"], {"type": "json_object"})
        self.assertEqual(second_payload["messages"][-2]["role"], "assistant")
        self.assertEqual(second_payload["messages"][-2]["content"], invalid)
        self.assertEqual(second_payload["messages"][-1]["role"], "user")

    def test_repair_preserves_completed_tool_result_and_redacts_public_trace(self) -> None:
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            chat_model="gpt-test",
            timeout_seconds=3,
        )
        tool_call = {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call-question-1",
                                "type": "function",
                                "function": {
                                    "name": "ask_multiple_choice_question",
                                    "arguments": json.dumps(
                                        {
                                            "topic": "vector basis",
                                            "difficulty": "easy",
                                            "option_count": 3,
                                        }
                                    ),
                                },
                            }
                        ],
                    },
                }
            ]
        }
        invalid = json.dumps({"mood": "calm", "action": "point"})
        repaired = json.dumps(
            {
                "text": "先完成题目，再告诉我你的判断。",
                "mood": "calm",
                "action": "point",
            }
        )

        with patch.object(
            provider,
            "_request_openai_chat_completion",
            side_effect=[(tool_call, []), (_raw_reply(invalid), []), (_raw_reply(repaired), [])],
        ) as request:
            reply = provider.generate_chat(
                persona=_persona(),
                section_id="unit-1",
                message="Quiz me about vector bases",
            )

        self.assertEqual(request.call_count, 3)
        recovery_payload = request.call_args_list[2].args[0]
        self.assertNotIn("tools", recovery_payload)
        self.assertTrue(
            any(message.get("role") == "tool" for message in recovery_payload["messages"])
        )
        self.assertIsNotNone(reply.interactive_question)
        self.assertEqual(len(reply.tool_calls), 1)
        private_question = reply.interactive_question
        assert private_question is not None
        self.assertIsNotNone(private_question.answer_key)
        public_trace = reply.tool_calls[0].result_json
        for private_key in (
            "answer",
            "answer_key",
            "accepted_answers",
            "grading_spec",
            "correct_option_key",
            "explanation",
        ):
            self.assertNotIn(private_key, public_trace)

    def test_fill_blank_tool_trace_redacts_private_answer(self) -> None:
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            chat_model="gpt-test",
            timeout_seconds=3,
        )
        tool_call = {
            "choices": [
                {
                    "finish_reason": "tool_calls",
                    "message": {
                        "content": "",
                        "tool_calls": [
                            {
                                "id": "call-fill-blank-1",
                                "type": "function",
                                "function": {
                                    "name": "ask_fill_blank_question",
                                    "arguments": json.dumps(
                                        {
                                            "topic": "vector basis",
                                            "difficulty": "easy",
                                            "blank_count": 1,
                                        }
                                    ),
                                },
                            }
                        ],
                    },
                }
            ]
        }
        final_reply = json.dumps(
            {
                "text": "请完成填空题。",
                "mood": "calm",
                "action": "point",
            }
        )

        with patch.object(
            provider,
            "_request_openai_chat_completion",
            side_effect=[(tool_call, []), (_raw_reply(final_reply), [])],
        ):
            reply = provider.generate_chat(
                persona=_persona(),
                section_id="unit-1",
                message="Give me a fill-blank question",
            )

        self.assertIsNotNone(reply.interactive_question)
        self.assertEqual(len(reply.tool_calls), 1)
        public_result = json.loads(reply.tool_calls[0].result_json)
        for private_key in (
            "answer",
            "answer_key",
            "accepted_answers",
            "grading_spec",
            "correct_option_key",
            "explanation",
        ):
            self.assertNotIn(private_key, public_result)


class StudyChatReplyRouteBoundaryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = TemporaryDirectory()
        self.database = Database(f"sqlite:///{Path(self.temp.name) / 'test.db'}")
        self.database.create_schema()
        self.sessions = StudySessionRepository(self.database)
        self.operations = StudyChatOperationRepository(self.database)
        self.sessions.create(
            StudySessionRecord(
                id="session-invalid-reply",
                document_id="doc",
                persona_id="persona-strict-chat",
                study_unit_id="unit-1",
                status="active",
                turns=[],
                revision=0,
                last_turn_sequence=0,
                created_at="2026-08-25T00:00:00+00:00",
                updated_at="2026-08-25T00:00:00+00:00",
            )
        )

    def tearDown(self) -> None:
        self.database.dispose()
        self.temp.cleanup()

    def test_repair_failure_marks_operation_uncertain_and_commits_no_turn(self) -> None:
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            chat_model="gpt-test",
            chat_tools_enabled=False,
            timeout_seconds=3,
        )
        invalid = json.dumps({"mood": "calm", "action": "point"})
        responses = [(_raw_reply(invalid), []), (_raw_reply(invalid), [])]

        def run_failed_chat(**_kwargs: object):
            return provider.generate_chat(
                persona=_persona(),
                section_id="unit-1",
                message="Explain vector bases",
            )

        runtime_settings = SimpleNamespace(
            effective_settings=lambda: SimpleNamespace(
                openai_timeout_seconds=3,
                openai_chat_tool_max_rounds=1,
            )
        )
        session_service = SimpleNamespace(require_session=self.sessions.require)
        prepared = PreparedStudyChatAttachments(
            records=[],
            attachment_context="",
            multimodal_parts=[],
        )

        with (
            patch.object(routes.container, "study_chat_operation_repository", self.operations),
            patch.object(routes.container, "study_session_service", session_service),
            patch.object(routes.container, "runtime_settings_service", runtime_settings),
            patch.object(routes.container, "model_provider", provider),
            patch.object(routes.container, "store", object()),
            patch.object(routes, "prepare_study_chat_attachments", return_value=prepared),
            patch.object(routes, "cleanup_staged_study_chat_operation_attachments"),
            patch.object(routes, "_run_study_chat", side_effect=run_failed_chat),
            patch.object(
                provider,
                "_request_openai_chat_completion",
                side_effect=responses,
            ) as request,
        ):
            receipt = routes._admit_and_run_study_chat(
                session_id="session-invalid-reply",
                client_request_id="invalid-reply-request-0001",
                expected_session_revision=0,
                message="Explain vector bases",
                message_kind="learner",
                follow_up_id="",
                hidden_message_prefix="",
                attachment_inputs=[],
            )

        self.assertEqual(request.call_count, 2)
        self.assertEqual(receipt.status, "uncertain")
        self.assertFalse(receipt.safe_to_retry)
        self.assertIsNone(receipt.result)
        session = self.sessions.require("session-invalid-reply")
        self.assertEqual(session.revision, 0)
        self.assertEqual(session.last_turn_sequence, 0)
        self.assertEqual(session.turns, [])

    def test_route_forwards_validated_session_prelude_kind_to_execution(self) -> None:
        captured: dict[str, object] = {}

        def fail_after_capture(**kwargs: object):
            captured.update(kwargs)
            raise RuntimeError("captured_message_kind")

        runtime_settings = SimpleNamespace(
            effective_settings=lambda: SimpleNamespace(
                openai_timeout_seconds=3,
                openai_chat_tool_max_rounds=1,
            )
        )
        session_service = SimpleNamespace(require_session=self.sessions.require)
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            chat_model="gpt-test",
            timeout_seconds=3,
        )
        prepared = PreparedStudyChatAttachments(
            records=[],
            attachment_context="",
            multimodal_parts=[],
        )

        with (
            patch.object(routes.container, "study_chat_operation_repository", self.operations),
            patch.object(routes.container, "study_session_service", session_service),
            patch.object(routes.container, "runtime_settings_service", runtime_settings),
            patch.object(routes.container, "model_provider", provider),
            patch.object(routes.container, "store", object()),
            patch.object(routes, "prepare_study_chat_attachments", return_value=prepared),
            patch.object(routes, "cleanup_staged_study_chat_operation_attachments"),
            patch.object(routes, "_run_study_chat", side_effect=fail_after_capture),
        ):
            receipt = routes._admit_and_run_study_chat(
                session_id="session-invalid-reply",
                client_request_id="prelude-kind-forwarding-0001",
                expected_session_revision=0,
                message="正式对话开始前的预处理消息",
                message_kind=" session_prelude ",
                follow_up_id="",
                hidden_message_prefix="",
                attachment_inputs=[],
            )

        self.assertEqual(receipt.status, "uncertain")
        self.assertEqual(captured["message_kind"], "session_prelude")

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
            patch.object(routes.container, "study_chat_operation_repository", self.operations),
            patch.object(routes.container, "study_session_service", session_service),
            patch.object(routes, "_cleanup_terminal_study_chat_staging"),
            TestClient(app) as client,
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


if __name__ == "__main__":
    unittest.main()
