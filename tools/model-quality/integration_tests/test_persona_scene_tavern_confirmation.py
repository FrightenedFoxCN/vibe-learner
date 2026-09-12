import json
import unittest

from examples.prepare_persona_scene_tavern_confirmation import (
    FIXTURE,
    _canonical_source,
    build_manifest,
)
from vibe_learner.persona_scene_tavern import _canonical_confirmation_source


class PersonaSceneTavernConfirmationTests(unittest.TestCase):
    def test_fixture_is_frozen_confirmation_with_disjoint_families(self):
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        self.assertEqual(fixture["version"], "persona-scene-tavern-confirmation-v2")
        self.assertEqual(fixture["split"], "confirmation")
        ids = [row["id"] for row in fixture["cases"]]
        self.assertEqual(len(ids), 6)
        self.assertEqual(len(set(ids)), 6)
        old_fragments = {"bookbinder", "observatory", "workshop", "teahouse"}
        self.assertTrue(all(not any(fragment in case_id for fragment in old_fragments) for case_id in ids))

    def test_manifest_exposes_complete_source_and_keeps_constraints_out_of_source(self):
        manifest = build_manifest(
            budget_document={"budget": {"token_limit": 1, "wire_limit": 1, "rpm": 1, "tpm": 1,
                "max_inflight": 1, "expires_at": 9999999999, "stop_buffer_seconds": 1}},
            transport="fake",
        )
        self.assertEqual(len(manifest["cases"]), 6)
        for case in manifest["cases"]:
            source = json.loads(case["source"])
            gold = json.loads(case["gold"])
            self.assertEqual(case["split"], "confirmation")
            self.assertEqual(case["family"], case["id"])
            self.assertEqual(set(source), {"persona_input", "scene_input", "user_message"})
            self.assertNotIn("source_fidelity_constraints", source)
            self.assertEqual(case["source"], _canonical_source(gold))
            self.assertEqual(case["source"], _canonical_confirmation_source(gold))


if __name__ == "__main__":
    unittest.main()
