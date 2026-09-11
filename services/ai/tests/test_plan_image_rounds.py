"""Mixed image/text tool rounds must preserve the provider message protocol."""
import unittest
from types import SimpleNamespace

from app.services.openai_plan_runner import OpenAIPlanRunner


class PlanImageRoundTests(unittest.TestCase):
    def test_all_tool_receipts_precede_images_and_image_order_is_preserved(self):
        tools = [{"id": key, "type": "function", "function": {"name": name, "arguments": "{}"}}
            for key, name in [("image-a", "read_page_range_images"), ("text", "read_page_range_content"),
                ("image-b", "read_page_range_images")]]
        images = {key: {"role": "user", "content": [{"type": "image_url", "image_url": {"url": "data:image/png;base64," + key}}]}
            for key in ("image-a", "image-b")}

        def execute(call):
            key = call["id"]
            return SimpleNamespace(tool_call_id=key, tool_name=call["function"]["name"], arguments_json="{}",
                argument_contract_version="planning-tool-arguments-v1", result_contract_version="planning-tool-result-v1",
                trace_summary="fixture", trace_result={"ok": True}, provider_result={"ok": True},
                follow_up_messages=[images[key]] if key in images else [])

        requests = []
        def request(payload):
            requests.append(payload)
            if len(requests) == 1:
                return {"choices": [{"finish_reason": "tool_calls", "message": {"content": "", "tool_calls": tools}}]}, 1
            messages = payload["messages"]
            self.assertEqual([m["role"] for m in messages], ["system", "assistant", "tool", "tool", "tool", "user", "user"])
            self.assertEqual([m["tool_call_id"] for m in messages[2:5]], ["image-a", "text", "image-b"])
            self.assertEqual(messages[5:], [images["image-a"], images["image-b"]])
            return {"choices": [{"finish_reason": "stop", "message": {"content": '{"course_title":"fixture"}'}}]}, 1

        runtime = SimpleNamespace(has_tools=lambda: True, openai_tools=lambda: [], begin_round=lambda: None,
            execute_tool_call=execute, current_study_units=lambda: [])
        result = OpenAIPlanRunner(model="fixture", timeout_seconds=1, request_chat_completion=request).run(
            document_id="fixture", messages=[{"role": "system", "content": "fixture"}], tool_runtime=runtime)
        self.assertEqual(result.content, '{"course_title":"fixture"}')
        self.assertEqual(result.tool_messages, requests[-1]["messages"][1:])
        self.assertNotIn("tool_messages", result.trace.model_dump())
        self.assertEqual(len(result.trace.rounds[0].tool_calls), 3)
