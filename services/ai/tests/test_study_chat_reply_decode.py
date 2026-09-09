from tests.support.study_chat_samples import study_persona, raw_chat_reply, question_reply

import json
import unittest


from app.models.api import StudyChatResponse
from app.models.study_question import project_study_question_proposal
from app.services.provider_study import _execute_chat_tool_call, _parse_chat_model_reply


def _parse(content: str):
    return _parse_chat_model_reply(
        raw_payload=raw_chat_reply(content),
        tool_results=[],
        fallback_memory_trace=[],
        tool_traces=[],
    )


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

        self.assertEqual(
            execution["arguments_json"],
            '{"contract_version":"study-chat-tool-arguments-v1","redacted":true}',
        )
        self.assertNotIn(raw_arguments, execution["arguments_json"])
        self.assertFalse(execution["result"]["ok"])
        self.assertEqual(
            execution["result"]["error"],
            "tool_argument_invalid_json",
        )
        self.assertEqual(
            execution["result"]["tool_name"],
            "ask_multiple_choice_question",
        )
        self.assertNotIn("question_type", execution["result"])
        self.assertNotIn("question", execution["result"])

    def test_non_object_or_malformed_arguments_never_reach_proxy_runtimes(self) -> None:
        class CountingRuntime:
            def __init__(self) -> None:
                self.execution_count = 0

            def has_tool(self, _tool_name: str) -> bool:
                return True

            def available_tool_names(self) -> list[str]:
                return ["read_session_memory"]

            def execute_tool(self, tool_name: str, arguments: dict[str, object]):
                self.execution_count += 1
                return {"ok": True, "tool_name": tool_name, "arguments": arguments}

        runtime = CountingRuntime()
        cases = (
            ('{"broken":', "tool_argument_invalid_json"),
            ('{"value":NaN}', "tool_argument_schema_invalid"),
            ('{"value":Infinity}', "tool_argument_schema_invalid"),
            ('{"value":-Infinity}', "tool_argument_schema_invalid"),
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
                            "name": "read_session_memory",
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
                self.assertEqual(
                    execution["arguments_json"],
                    '{"contract_version":"study-chat-tool-arguments-v1","redacted":true}',
                )
                self.assertNotIn(raw_arguments, execution["arguments_json"])
                self.assertEqual(execution["result"]["error"], expected_error)
                self.assertFalse(execution["result"]["ok"])

        non_string_function_payloads = (
            {"name": "read_session_memory"},
            {"name": "read_session_memory", "arguments": None},
            {"name": "read_session_memory", "arguments": {}},
            {"name": "read_session_memory", "arguments": []},
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
                self.assertEqual(
                    execution["arguments_json"],
                    '{"contract_version":"study-chat-tool-arguments-v1","redacted":true}',
                )
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
                payload = question_reply()
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
                payload = question_reply()
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
            question_reply(),
            ensure_ascii=False,
            separators=(",", ":"),
        ) + ',"state_commentary":"trailing provider fragment"}'

        with self.assertRaisesRegex(RuntimeError, "chat_model_invalid_payload"):
            _parse(observed_provider_shape)

    def test_valid_question_keeps_grading_private_in_public_projection(self) -> None:
        reply = _parse(json.dumps(question_reply(), ensure_ascii=False))

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





if __name__ == "__main__":
    unittest.main()
