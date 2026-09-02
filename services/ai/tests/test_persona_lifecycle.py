from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException
from pydantic import ValidationError

from app.models.api import CreatePersonaRequest, UpdatePersonaRequest
from app.models.domain import PersonaProfile
from app.services.local_store import LocalJsonStore
from app.services.persona import PersonaEngine


def create_request(name: str = "Mentor") -> CreatePersonaRequest:
    return CreatePersonaRequest(
        name=name,
        summary="Structured mentor",
        relationship="teacher",
        learner_address="learner",
        system_prompt="Stay grounded",
        reference_hints=["source"],
        slots=[{
            "kind": "teaching_method",
            "label": "Method",
            "content": "Socratic",
            "weight": 50,
            "locked": False,
            "sort_order": 0,
        }],
        available_emotions=["calm"],
        available_actions=["idle"],
        default_speech_style="warm",
    )


def update_request(persona: PersonaProfile, *, summary: str) -> UpdatePersonaRequest:
    return UpdatePersonaRequest(
        expected_revision=persona.revision,
        name=persona.name,
        summary=summary,
        relationship=persona.relationship,
        learner_address=persona.learner_address,
        system_prompt=persona.system_prompt,
        reference_hints=persona.reference_hints,
        slots=persona.slots,
        available_emotions=persona.available_emotions,
        available_actions=persona.available_actions,
        default_speech_style=persona.default_speech_style,
    )


class PersonaLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.temp_dir.name) / "store"
        self.store = LocalJsonStore(self.root)
        self.engine = PersonaEngine(self.store)

    def tearDown(self) -> None:
        self.store.close()
        self.temp_dir.cleanup()

    def test_create_reload_update_reload_delete_reload(self) -> None:
        created = self.engine.create_persona(create_request("完整生命周期 / ?#% 🧭"))
        self.assertRegex(created.id, r"^persona-[0-9a-f]{32}$")
        self.assertEqual(created.revision, 0)

        reloaded = PersonaEngine(self.store).require_persona(created.id)
        self.assertEqual(reloaded.summary, "Structured mentor")

        updated = self.engine.update_persona(
            created.id,
            update_request(created, summary="Updated safely"),
        )
        self.assertEqual(updated.id, created.id)
        self.assertEqual(updated.revision, 1)
        self.assertEqual(PersonaEngine(self.store).require_persona(created.id).summary, "Updated safely")

        self.engine.delete_persona(created.id, expected_revision=updated.revision)
        with self.assertRaises(HTTPException) as context:
            PersonaEngine(self.store).require_persona(created.id)
        self.assertEqual(context.exception.status_code, 404)

    def test_names_never_control_persona_identity_or_legacy_paths(self) -> None:
        names = ["A/B ?#%", "../../outside", "/tmp/absolute", "同名人格", "同名人格"]
        created = [self.engine.create_persona(create_request(name)) for name in names]
        ids = [persona.id for persona in created]
        self.assertEqual(len(ids), len(set(ids)))
        for persona_id in ids:
            self.assertRegex(persona_id, r"^persona-[0-9a-f]{32}$")
            self.assertTrue((self.root / "personas" / f"{persona_id}.json").is_file())
        self.assertFalse((Path(self.temp_dir.name) / "outside.json").exists())

    def test_stale_update_and_delete_fail_without_overwriting(self) -> None:
        created = self.engine.create_persona(create_request())
        first = self.engine.update_persona(
            created.id,
            update_request(created, summary="First writer"),
        )
        with self.assertRaises(HTTPException) as update_context:
            self.engine.update_persona(
                created.id,
                update_request(created, summary="Stale writer"),
            )
        self.assertEqual(update_context.exception.status_code, 409)
        self.assertEqual(update_context.exception.detail["code"], "persona_revision_conflict")
        self.assertEqual(self.engine.require_persona(created.id).summary, "First writer")

        with self.assertRaises(HTTPException) as delete_context:
            self.engine.delete_persona(created.id, expected_revision=created.revision)
        self.assertEqual(delete_context.exception.status_code, 409)
        self.engine.delete_persona(created.id, expected_revision=first.revision)

    def test_write_contract_rejects_coercion_unknown_fields_and_invalid_slots(self) -> None:
        base = create_request().model_dump(mode="python")
        invalid_payloads = [
            {**base, "name": "   "},
            {**base, "unknown_field": "ignored-no-longer"},
            {**base, "slots": [{"kind": "custom", "label": "", "content": "", "weight": -1}]},
            {**base, "slots": [{"kind": "custom", "label": "", "content": "", "weight": 101}]},
            {**base, "slots": [{"kind": "custom", "label": "", "content": "", "weight": float("nan")}]},
            {**base, "slots": [{"kind": "custom", "label": "", "content": "", "locked": 1}]},
            {**base, "slots": [{"kind": "custom", "label": "", "content": "", "sort_order": -1}]},
        ]
        for payload in invalid_payloads:
            with self.subTest(payload=payload):
                with self.assertRaises(ValidationError):
                    CreatePersonaRequest.model_validate(payload)

        for boundary in (0, 100):
            payload = {
                **base,
                "slots": [{
                    "kind": "custom",
                    "label": "",
                    "content": "",
                    "weight": boundary,
                    "locked": False,
                    "sort_order": 0,
                }],
            }
            self.assertEqual(CreatePersonaRequest.model_validate(payload).slots[0].weight, boundary)

    def test_unsafe_legacy_item_id_is_rejected_before_database_write(self) -> None:
        persona = self.engine.create_persona(create_request())
        with self.assertRaisesRegex(ValueError, "local_store_item_id_unsafe"):
            self.store.save_item("personas", "../../escape", persona)
        self.assertFalse((Path(self.temp_dir.name) / "escape.json").exists())

    def test_legacy_mirror_failure_does_not_turn_a_committed_create_into_an_error(self) -> None:
        with patch.object(self.store._legacy, "save_item", side_effect=OSError("disk full")):
            created = self.engine.create_persona(create_request("Mirror failure"))
        self.assertEqual(PersonaEngine(self.store).require_persona(created.id).name, "Mirror failure")


if __name__ == "__main__":
    unittest.main()
