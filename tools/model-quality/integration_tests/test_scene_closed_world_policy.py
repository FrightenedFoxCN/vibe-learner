from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import sys
import unittest

AI_SERVICE_ROOT = Path(__file__).resolve().parents[3] / "services" / "ai"
sys.path.insert(0, str(AI_SERVICE_ROOT))

from vibe_learner.scene_closed_world_policy import (
    SceneClosedWorldInputError,
    SceneClosedWorldPolicyV1,
    validate_scene_closed_world,
)

from app.models.scene import SceneTreeProposalV1  # noqa: E402


FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "persona-scene"
    / "scene-closed-world-v1.json"
)


def _apply_single_point_mutation(
    proposal: dict[str, object],
    mutation: dict[str, object],
) -> dict[str, object]:
    mutated = deepcopy(proposal)
    raw_path = mutation["path"]
    if not isinstance(raw_path, str) or not raw_path.startswith("/"):
        raise AssertionError(f"invalid fixture mutation path: {raw_path!r}")
    tokens = [
        token.replace("~1", "/").replace("~0", "~")
        for token in raw_path.removeprefix("/").split("/")
    ]
    parent: object = mutated
    for token in tokens[:-1]:
        if isinstance(parent, list):
            parent = parent[int(token)]
        elif isinstance(parent, dict):
            parent = parent[token]
        else:
            raise AssertionError(f"fixture mutation traverses scalar: {raw_path}")
    leaf = tokens[-1]
    operation = mutation["operation"]
    if operation == "add":
        value = deepcopy(mutation["value"])
        if isinstance(parent, list):
            if leaf != "-":
                raise AssertionError(f"fixture add must append: {raw_path}")
            parent.append(value)
        elif isinstance(parent, dict):
            parent[leaf] = value
        else:
            raise AssertionError(f"fixture add parent is scalar: {raw_path}")
    elif operation == "remove":
        if isinstance(parent, list):
            parent.pop(int(leaf))
        elif isinstance(parent, dict):
            del parent[leaf]
        else:
            raise AssertionError(f"fixture remove parent is scalar: {raw_path}")
    elif operation == "replace":
        value = deepcopy(mutation["value"])
        if isinstance(parent, list):
            parent[int(leaf)] = value
        elif isinstance(parent, dict):
            parent[leaf] = value
        else:
            raise AssertionError(f"fixture replace parent is scalar: {raw_path}")
    else:
        raise AssertionError(f"unsupported fixture mutation operation: {operation}")
    return mutated


def _object(name: str) -> dict[str, object]:
    return {
        "name": name,
        "description": f"{name}的静态描述",
        "interaction": "仅供观察",
        "tags": [],
        "reuse_hint": "",
        "reusable_node_ref": None,
    }


def _layer(
    title: str,
    *,
    objects: list[dict[str, object]] | None = None,
    children: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "title": title,
        "scope_label": "区域",
        "summary": f"{title}摘要",
        "atmosphere": "安静",
        "rules": "不得虚构通行权限",
        "entrance": "从已说明入口进入",
        "tags": [],
        "reuse_hint": "",
        "reusable_node_ref": None,
        "objects": objects or [],
        "children": children or [],
    }


def _valid_proposal() -> dict[str, object]:
    return {
        "schema_name": "scene-tree-proposal",
        "schema_version": "scene-tree-proposal-v1",
        "scene_name": "三格种子库",
        "scene_summary": "只有已登记的三个格区。",
        "selected_path": [0, 0],
        "scene_layers": [
            _layer(
                "种子库",
                objects=[_object("目录柜")],
                children=[
                    _layer("接收格", objects=[_object("扫码台")]),
                    _layer("干藏格", objects=[_object("纸袋架")]),
                    _layer("冷藏格", objects=[_object("低温抽屉")]),
                ],
            )
        ],
    }


def _policy() -> SceneClosedWorldPolicyV1:
    return SceneClosedWorldPolicyV1(
        root_title="种子库",
        direct_children_exact=["接收格", "干藏格", "冷藏格"],
        forbid_deeper_layers=True,
        required_root_objects=["目录柜"],
        allowed_root_objects=["目录柜"],
        required_child_objects_by_title={
            "接收格": ["扫码台"],
            "干藏格": ["纸袋架"],
            "冷藏格": ["低温抽屉"],
        },
        allowed_child_objects_by_title={
            "接收格": ["扫码台"],
            "干藏格": ["纸袋架"],
            "冷藏格": ["低温抽屉"],
        },
        allowed_entrances=["从已说明入口进入", "没有入口。"],
    )


class SceneClosedWorldPolicyTests(unittest.TestCase):
    def issue_codes(self, proposal: dict[str, object]) -> list[str]:
        return [issue.code for issue in validate_scene_closed_world(_policy(), proposal)]

    def test_valid_control_accepts_dict_and_decoded_model(self):
        proposal = _valid_proposal()
        self.assertEqual(validate_scene_closed_world(_policy(), proposal), [])
        decoded = SceneTreeProposalV1.model_validate(proposal)
        self.assertEqual(validate_scene_closed_world(_policy(), decoded), [])

    def test_extra_child_mutation(self):
        proposal = deepcopy(_valid_proposal())
        proposal["scene_layers"][0]["children"].append(_layer("第四格"))
        self.assertIn("extra_child", self.issue_codes(proposal))

    def test_missing_child_mutation(self):
        proposal = deepcopy(_valid_proposal())
        proposal["scene_layers"][0]["children"].pop()
        self.assertIn("missing_child", self.issue_codes(proposal))

    def test_extra_depth_mutation(self):
        proposal = deepcopy(_valid_proposal())
        proposal["scene_layers"][0]["children"][0]["children"].append(
            _layer("未登记缓冲间")
        )
        self.assertIn("extra_depth", self.issue_codes(proposal))

    def test_missing_object_mutation(self):
        proposal = deepcopy(_valid_proposal())
        proposal["scene_layers"][0]["children"][0]["objects"] = []
        self.assertIn("missing_object", self.issue_codes(proposal))

    def test_unsupported_object_mutation(self):
        proposal = deepcopy(_valid_proposal())
        proposal["scene_layers"][0]["children"][0]["objects"].append(
            _object("门禁卡")
        )
        self.assertIn("unsupported_object", self.issue_codes(proposal))

    def test_unsupported_entrance_mutation(self):
        proposal = deepcopy(_valid_proposal())
        proposal["scene_layers"][0]["entrance"] = "北侧入口"
        issues = validate_scene_closed_world(_policy(), proposal)
        match = next(issue for issue in issues if issue.code == "unsupported_entrance")
        self.assertEqual(match.path, "scene_layers[0].entrance")
        self.assertEqual(match.observed, "北侧入口")

    def test_wrong_root_is_a_typed_issue(self):
        proposal = deepcopy(_valid_proposal())
        proposal["scene_layers"][0]["title"] = "另一处"
        codes = self.issue_codes(proposal)
        self.assertIn("root_title_mismatch", codes)

    def test_duplicate_child_title_is_extra_and_missing(self):
        proposal = deepcopy(_valid_proposal())
        proposal["scene_layers"][0]["children"][1]["title"] = "接收格"
        codes = self.issue_codes(proposal)
        self.assertIn("extra_child", codes)
        self.assertIn("missing_child", codes)

    def test_malformed_candidate_raises_instead_of_appearing_to_pass(self):
        proposal = deepcopy(_valid_proposal())
        proposal["scene_layers"][0].pop("objects")
        proposal["selected_path"] = [99]
        proposal["unknown_field"] = "must not be ignored"
        with self.assertRaisesRegex(SceneClosedWorldInputError, "strict_decode_failed"):
            validate_scene_closed_world(_policy(), proposal)

    def test_duplicate_allowed_object_is_rejected(self):
        proposal = deepcopy(_valid_proposal())
        proposal["scene_layers"][0]["objects"].append(_object("目录柜"))
        self.assertIn("duplicate_object", self.issue_codes(proposal))

    def test_registered_negative_entrance_statement_is_not_a_false_positive(self):
        proposal = deepcopy(_valid_proposal())
        proposal["scene_layers"][0]["entrance"] = "没有入口。"
        self.assertNotIn("unsupported_entrance", self.issue_codes(proposal))

    def test_optional_root_title_does_not_indirectly_lock_root_ownership(self):
        proposal = deepcopy(_valid_proposal())
        proposal["scene_layers"][0]["title"] = "改名后的根"
        policy = _policy().model_copy(update={"root_title": None})
        self.assertEqual(validate_scene_closed_world(policy, proposal), [])

    def test_policy_rejects_ambiguous_or_self_contradictory_registration(self):
        with self.assertRaises(ValueError):
            SceneClosedWorldPolicyV1(
                direct_children_exact=["接收格", "接收格"],
                forbid_deeper_layers=True,
                required_root_objects=[],
                allowed_root_objects=[],
                required_child_objects_by_title={"接收格": ["门禁卡"]},
                allowed_child_objects_by_title={"接收格": ["扫码台"]},
                allowed_entrances=["未指定"],
            )

    def test_independently_authored_fixture_calibration_gate(self):
        fixture = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
        self.assertEqual(fixture["version"], "scene-closed-world-fixture-v1")
        cases = fixture["cases"]
        self.assertEqual(len(cases), 6)
        expected_code_by_mutation = {
            "extra_child": "extra_child",
            "extra_depth": "extra_depth",
            "unsupported_object": "unsupported_object",
            "missing_child": "missing_child",
            "missing_object": "missing_object",
            "unsupported_structured_entrance": "unsupported_entrance",
        }
        seen_case_ids: set[str] = set()
        calibrated_mutations = 0
        for case in cases:
            case_id = case["case_id"]
            with self.subTest(case=case_id, arm="valid_control"):
                self.assertNotIn(case_id, seen_case_ids)
                seen_case_ids.add(case_id)
                policy = SceneClosedWorldPolicyV1.model_validate(
                    case["scene_closed_world_policy_v1"],
                    strict=True,
                )
                valid = SceneTreeProposalV1.model_validate(
                    case["valid_minimal_scene_tree_proposal"],
                    strict=True,
                )
                self.assertEqual(validate_scene_closed_world(policy, valid), [])
            mutations = case["single_point_mutations"]
            self.assertEqual(len(mutations), 6)
            self.assertEqual(
                {mutation["mutation_id"] for mutation in mutations},
                set(expected_code_by_mutation),
            )
            for mutation in mutations:
                mutation_id = mutation["mutation_id"]
                with self.subTest(case=case_id, arm=mutation_id):
                    mutated = _apply_single_point_mutation(
                        case["valid_minimal_scene_tree_proposal"],
                        mutation,
                    )
                    decoded = SceneTreeProposalV1.model_validate(
                        mutated,
                        strict=True,
                    )
                    codes = {
                        issue.code
                        for issue in validate_scene_closed_world(policy, decoded)
                    }
                    self.assertIn(expected_code_by_mutation[mutation_id], codes)
                    calibrated_mutations += 1
        self.assertEqual(len(seen_case_ids), 6)
        self.assertEqual(calibrated_mutations, 36)


if __name__ == "__main__":
    unittest.main()
