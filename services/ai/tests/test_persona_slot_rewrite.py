
from tests.support.provider_payloads import setting_wire_reply
from tests.support.api import ContainerTestCase, isolated_client

import unittest
import json
from tempfile import TemporaryDirectory
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.models.domain import PersonaSlot
from app.services.model_provider import OpenAIModelProvider
from app.services.persona import PersonaEngine
from app.api import routes
from app.models.api import PersonaSlotAssistRequest, PersonaSettingAssistRequest
from app.services.local_store import LocalJsonStore
from app.services.harness_broad_adoption import (
    HarnessProposalRuntimeService,
)


class PersonaSlotRewriteTests(ContainerTestCase):
    def test_typed_slot_failure_uses_one_bounded_provider_repair(self):
        provider = OpenAIModelProvider(api_key="test", base_url="https://example.test/v1", plan_model="test", setting_model="test", timeout_seconds=3)
        slot = PersonaSlot(kind="teaching_method", label="Method", content="Observe.")
        def wire(payload):
            return ({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload)}}]}, 0)
        invalid = wire({"slot": {"kind": "teaching_method", "label": "Method", "content": 17}})
        valid = wire({"slot": {"kind": "teaching_method", "label": "Method", "content": "Observe and compare."}})
        for replies, succeeds in (([invalid, valid], True), ([invalid, invalid], False)):
            with patch.object(provider, "_request_openai_chat_completion", side_effect=replies) as request:
                if succeeds:
                    result = provider.assist_persona_slot(name="Mira", summary="Tutor", slot=slot, rewrite_strength=0.3)
                    self.assertEqual(result["slot"]["content"], "Observe and compare.")
                else:
                    with self.assertRaisesRegex(RuntimeError, "setting_model_invalid_payload"):
                        provider.assist_persona_slot(name="Mira", summary="Tutor", slot=slot, rewrite_strength=0.3)
                self.assertEqual(request.call_count, 2)

    def test_api_fallback_is_public_and_keeps_all_setting_slots(self):
        def fail(**kwargs):
            raise RuntimeError("setting_model_invalid_json")

        with TemporaryDirectory() as directory:
            store = LocalJsonStore(Path(directory))
            try:
                with (
                    patch.object(self.container, "model_provider", SimpleNamespace(assist_persona_slot=fail, assist_persona_setting=fail)),
                    patch.object(self.container, "persona_engine", PersonaEngine()),
                    patch.object(self.container, "harness_proposal_runtime", HarnessProposalRuntimeService.from_database(store.database)),
                ):
                    slots = [
                        PersonaSlot(kind="worldview", label="World", content="A red lamp.", locked=True),
                        PersonaSlot(kind="past_experiences", label="History", content="Observatory volunteer."),
                    ]
                    setting = routes.assist_persona_setting(PersonaSettingAssistRequest(name="Mira", summary="Tutor", slots=slots, rewrite_strength=0.3), container=self.container)
                    self.assertEqual([item.model_dump() for item in setting.slots], [item.model_dump() for item in slots])
                    slot = routes.assist_persona_slot(PersonaSlotAssistRequest(name="Mira", summary="Tutor", slot=slots[0], rewrite_strength=0.3), container=self.container)
                    for response in (setting, slot):
                        self.assertEqual(response.harness_trace.status.value, "repaired")
                        self.assertEqual(len(response.model_recoveries), 1)
                        self.assertEqual(response.model_recoveries[0].strategy, "local_fallback")
            finally:
                store.close()

    def test_repeated_local_fallback_does_not_grow_content(self):
        engine = PersonaEngine()
        for kind in ("teaching_method", "custom", "scene_description"):
            slot = PersonaSlot(kind=kind, label="Original", content="Keep the lamp red.", weight=73, sort_order=20)
            once = engine.assist_slot(name="Mira", summary="Tutor", slot=slot, rewrite_strength=0.3)
            twice = engine.assist_slot(name="Mira", summary="Tutor", slot=once, rewrite_strength=0.3)
            self.assertEqual(once, twice)
            if kind != "teaching_method":
                self.assertEqual(once, slot)

    def test_local_fallback_keeps_locked_slot(self):
        slot = PersonaSlot(kind="worldview", label="Worldview", content="Original worldview", locked=True)
        result = PersonaEngine().assist_slot(name="Mira", summary="Tutor", slot=slot, rewrite_strength=1)
        self.assertEqual(result, slot)

    def test_rewrite_preserves_user_slot_controls_when_model_omits_or_changes_them(self):
        provider = OpenAIModelProvider(
            api_key="test-key", base_url="https://example.test/v1",
            plan_model="test", setting_model="test", timeout_seconds=3,
        )
        original = PersonaSlot(
            kind="teaching_method", label="Method", content="Ask one question.",
            weight=73, locked=False, sort_order=20,
        )
        for controls in ({}, {"weight": 1.0, "locked": True, "sort_order": 0}):
            with self.subTest(controls=controls), patch.object(provider, '_request_openai_chat_completion', return_value=setting_wire_reply({'slot': {'kind': 'unexpected_kind', 'label': 'Evidence method', 'content': 'Ask one question and check the observation.', **controls}}, responses=False)):
                result = provider.assist_persona_slot(
                    name="Mira", summary="Astronomy tutor", slot=original,
                    rewrite_strength=0.3,
                )["slot"]
                self.assertEqual(result["content"], "Ask one question and check the observation.")
                self.assertEqual(result["label"], "Evidence method")
                for field in ("kind", "weight", "locked", "sort_order"):
                    self.assertEqual(result[field], getattr(original, field))
