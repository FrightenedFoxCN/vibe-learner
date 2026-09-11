"""Native image parts survive Study tool execution and strict reply repair."""
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from app.services.provider_study import RemoteStudyProvider
from tests.support.study_chat_samples import study_persona, raw_chat_reply


class StudyToolImageTests(unittest.TestCase):
    def test_both_pdf_image_tools_attach_after_receipts_and_survive_repair(self):
        images = [{"page_number": 1, "mime_type": "image/png", "image_url": "data:image/png;base64,fixture-a"}]
        attached = [{"page_number": 2, "mime_type": "image/png", "image_url": "data:image/png;base64,fixture-b"}]
        calls = [
            {"id": "book", "type": "function", "function": {"name": "read_page_range_images", "arguments": '{"page_start":1,"page_end":1}'}},
            {"id": "attachment", "type": "function", "function": {"name": "read_projected_pdf_images", "arguments": '{"page_start":2,"page_end":2}'}},
        ]
        requests = []
        def request(payload, **_kwargs):
            requests.append(payload)
            if len(requests) == 1:
                return {"choices": [{"finish_reason": "tool_calls", "message": {"content": "", "tool_calls": calls}}]}, 1
            messages = payload["messages"]
            tool_indexes = [i for i, m in enumerate(messages) if m["role"] == "tool"]
            image_indexes = [i for i, m in enumerate(messages) if isinstance(m.get("content"), list)
                and any(p.get("type") == "image_url" for p in m["content"])]
            self.assertEqual(len(tool_indexes), 2)
            self.assertEqual(len(image_indexes), 1)
            self.assertLess(max(tool_indexes), image_indexes[0])
            image_parts = [p for p in messages[image_indexes[0]]["content"] if p["type"] == "image_url"]
            self.assertEqual([p["image_url"]["url"] for p in image_parts], [images[0]["image_url"], attached[0]["image_url"]])
            if len(requests) == 2:
                return raw_chat_reply('{"mood":"calm","action":"point"}'), 1
            self.assertNotIn("tools", payload)
            return raw_chat_reply('{"text":"已核对两页。","mood":"calm","action":"point"}'), 1

        runtime = SimpleNamespace(available_tool_names=lambda: ["read_projected_pdf_images"],
            has_tool=lambda name: name == "read_projected_pdf_images",
            execute_tool=lambda *_: {"ok": True, "tool_name": "read_projected_pdf_images",
                "source_kind": "attachment_pdf", "source_id": "attachment-1", "page_start": 2,
                "page_end": 2, "image_count": 1, "images": attached})
        provider = RemoteStudyProvider(chat_model="fixture", chat_temperature=0.2, chat_max_tokens=800,
            chat_history_messages=8, chat_tool_max_rounds=4, chat_tools_enabled=True,
            chat_memory_tool_enabled=False, chat_multimodal_enabled=True, disabled_tools=frozenset(), request=request)
        with patch("app.services.provider_study.read_page_range_images", return_value={"page_start": 1, "page_end": 1,
                "image_count": 1, "images": images}):
            reply = provider.generate_chat(persona=study_persona(), section_id="unit", message="Read both images",
                document_path="fixture.pdf", debug_report=SimpleNamespace(), session_tool_runtime=runtime)
        self.assertEqual(len(requests), 3)
        self.assertEqual(len(reply.tool_calls), 2)
        for trace in reply.tool_calls:
            self.assertNotIn("base64", trace.result_json)
            self.assertNotIn("image_url", trace.result_json)
