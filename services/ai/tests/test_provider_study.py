"""Study generation and recovery use an injected request, without the SDK/API."""
import json
import unittest
from unittest.mock import Mock

from app.services.provider_study import RemoteStudyProvider
from tests.support.study_chat_samples import study_persona, raw_chat_reply


class StudyProviderTests(unittest.TestCase):
    def provider(self, **overrides):
        config = dict(chat_model="gpt-test", chat_temperature=0.35, chat_max_tokens=800,
                      chat_history_messages=8, chat_tool_max_rounds=4, chat_tools_enabled=True,
                      chat_memory_tool_enabled=True, chat_multimodal_enabled=False,
                      disabled_tools=frozenset(), request=Mock())
        return RemoteStudyProvider(**{**config, **overrides})

    def test_provider_repairs_once_without_tools_then_propagates_invalid(self) -> None:
        invalid = json.dumps({'mood': 'calm', 'action': 'point'})
        responses = [(raw_chat_reply(invalid), []), (raw_chat_reply(invalid), [])]
        request = Mock(side_effect=responses)
        provider = self.provider(request=request, chat_tools_enabled=False)
        with self.assertRaisesRegex(RuntimeError, 'chat_model_invalid_payload'):
            provider.generate_chat(persona=study_persona(), section_id='unit-1', message='Explain vector bases')
        self.assertEqual(request.call_count, 2)
        second_payload = request.call_args_list[1].args[0]
        self.assertNotIn('tools', second_payload)
        self.assertEqual(second_payload['response_format'], {'type': 'json_object'})
        self.assertEqual(second_payload['messages'][-2]['role'], 'assistant')
        self.assertEqual(second_payload['messages'][-2]['content'], invalid)
        self.assertEqual(second_payload['messages'][-1]['role'], 'user')

    def test_repair_preserves_completed_tool_result_and_redacts_public_trace(self) -> None:
        tool_call = {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': '', 'tool_calls': [{'id': 'call-question-1', 'type': 'function', 'function': {'name': 'ask_multiple_choice_question', 'arguments': json.dumps({'topic': 'vector basis', 'difficulty': 'easy', 'option_count': 3})}}]}}]}
        invalid = json.dumps({'mood': 'calm', 'action': 'point'})
        repaired = json.dumps({'text': '先完成题目，再告诉我你的判断。', 'mood': 'calm', 'action': 'point'})
        request = Mock(side_effect=[(tool_call, []), (raw_chat_reply(invalid), []), (raw_chat_reply(repaired), [])])
        provider = self.provider(request=request, chat_tools_enabled=True)
        reply = provider.generate_chat(persona=study_persona(), section_id='unit-1', message='Quiz me about vector bases')
        self.assertEqual(request.call_count, 3)
        recovery_payload = request.call_args_list[2].args[0]
        self.assertNotIn('tools', recovery_payload)
        self.assertTrue(any((message.get('role') == 'tool' for message in recovery_payload['messages'])))
        self.assertIsNotNone(reply.interactive_question)
        self.assertEqual(len(reply.tool_calls), 1)
        private_question = reply.interactive_question
        assert private_question is not None
        self.assertIsNotNone(private_question.answer_key)
        public_trace = reply.tool_calls[0].result_json
        for private_key in ('answer', 'answer_key', 'accepted_answers', 'grading_spec', 'correct_option_key', 'explanation'):
            self.assertNotIn(private_key, public_trace)

    def test_fill_blank_tool_trace_redacts_private_answer(self) -> None:
        tool_call = {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': '', 'tool_calls': [{'id': 'call-fill-blank-1', 'type': 'function', 'function': {'name': 'ask_fill_blank_question', 'arguments': json.dumps({'topic': 'vector basis', 'difficulty': 'easy', 'blank_count': 1})}}]}}]}
        final_reply = json.dumps({'text': '请完成填空题。', 'mood': 'calm', 'action': 'point'})
        request = Mock(side_effect=[(tool_call, []), (raw_chat_reply(final_reply), [])])
        provider = self.provider(request=request, chat_tools_enabled=True)
        reply = provider.generate_chat(persona=study_persona(), section_id='unit-1', message='Give me a fill-blank question')
        self.assertIsNotNone(reply.interactive_question)
        self.assertEqual(len(reply.tool_calls), 1)
        public_result = json.loads(reply.tool_calls[0].result_json)
        for private_key in ('answer', 'answer_key', 'accepted_answers', 'grading_spec', 'correct_option_key', 'explanation'):
            self.assertNotIn(private_key, public_result)

    def test_explicit_null_question_does_not_restore_tool_template(self) -> None:
        tool_call = {'choices': [{'finish_reason': 'tool_calls', 'message': {'content': '', 'tool_calls': [
            {'id': 'call-fill-cancelled', 'type': 'function', 'function': {
                'name': 'ask_fill_blank_question', 'arguments': json.dumps({'topic': '2x+3=11', 'blank_count': 1})}}]}}]}
        final_reply = json.dumps({'text': '本轮不出题。', 'mood': 'calm', 'action': '收起题卡',
                                  'interactive_question': None})
        request = Mock(side_effect=[(tool_call, []), (raw_chat_reply(final_reply), [])])
        reply = self.provider(request=request).generate_chat(
            persona=study_persona(), section_id='unit-1', message='先准备一道题，若无法完成就不要出题。')
        self.assertEqual(len(reply.tool_calls), 1)
        self.assertIsNone(reply.interactive_question)

    def test_noncompliant_tool_loop_has_finite_call_ceiling(self):
        payload = {"choices": [{"finish_reason": "tool_calls", "message": {
            "content": "", "tool_calls": [{"id": "call-invalid", "type": "function",
                "function": {"name": "unknown_tool", "arguments": "{}"}}],
        }}]}
        request = Mock(return_value=(payload, 1))
        with self.assertRaisesRegex(RuntimeError, "chat_model_invalid_payload"):
            self.provider(request=request, chat_tool_max_rounds=1).generate_chat(
                persona=study_persona(), section_id="unit-1", message="test",
            )
        # One configured round plus 12 exempt rounds, then one tool-free repair.
        self.assertEqual(request.call_count, 14)
        self.assertNotIn("tools", request.call_args.args[0])
