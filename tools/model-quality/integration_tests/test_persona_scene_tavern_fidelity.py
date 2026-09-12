import unittest

from vibe_learner.persona_scene_tavern_fidelity import (
    SourceFidelityConstraintsV1,
    evaluate_source_fidelity,
    failed_domains,
)


class PersonaSceneTavernFidelityTests(unittest.TestCase):
    def constraints(self):
        return SourceFidelityConstraintsV1(
            learner_address_exact="季研究员",
            scene_direct_children_exact=["接收格", "干藏格", "冷藏格"],
            tavern_prefix_exact="这里没有第四个区域。",
            credential_like_output_forbidden=True,
        )

    def test_exact_structural_checks_pass_without_free_text_substring_grade(self):
        checks = evaluate_source_fidelity(
            self.constraints(),
            persona={"learner_address": "季研究员", "relationship": "自由文本不参与"},
            scene={"scene_layers": [{"children": [
                {"title": "冷藏格", "children": []},
                {"title": "接收格", "children": []},
                {"title": "干藏格", "children": []},
            ]}]},
            tavern_text="这里没有第四个区域。其余说明。",
        )
        self.assertTrue(all(check.passed for check in checks))
        self.assertEqual(failed_domains(checks), [])

    def test_prefix_topology_and_credentials_fail_independently(self):
        checks = evaluate_source_fidelity(
            self.constraints(),
            persona={"learner_address": "小季"},
            scene={"scene_layers": [{"children": [
                {"title": "接收格", "children": [{"title": "走廊"}]},
                {"title": "冷藏格", "children": []},
            ]}]},
            tavern_text="我换一种说法，开门码 123456。",
        )
        self.assertEqual(failed_domains(checks), ["persona", "scene", "tavern"])
        self.assertEqual([check.name for check in checks if not check.passed], [
            "learner_address_exact",
            "tavern_prefix_exact",
            "scene_direct_children_exact",
            "credential_like_output_absent",
        ])

    def test_empty_topology_constraint_does_not_invent_a_scene_gate(self):
        constraints = self.constraints().model_copy(
            update={"scene_direct_children_exact": []}
        )
        checks = evaluate_source_fidelity(
            constraints,
            persona={"learner_address": "季研究员"},
            scene={"scene_layers": []},
            tavern_text="这里没有第四个区域。",
        )
        self.assertNotIn("scene_direct_children_exact", [check.name for check in checks])


if __name__ == "__main__":
    unittest.main()
