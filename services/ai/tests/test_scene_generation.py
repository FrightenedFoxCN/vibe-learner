import unittest

from app.models.api import SceneTreeGenerateRequest, SceneTreeGenerateResponse
from app.services.model_provider import MockModelProvider, _normalize_generated_scene_result
from app.services.prompt_loader import load_prompt_template


def _walk_layers(layers):
    for layer in layers:
        yield layer
        yield from _walk_layers(layer.children)


class SceneGenerationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.provider = MockModelProvider()

    def test_mock_keywords_scene_tree_includes_reusable_metadata(self) -> None:
        result = self.provider.generate_scene_tree_from_keywords(
            keywords="赛博校园, 物理实验, 夜间自习",
            layer_count=5,
        )
        payload = SceneTreeGenerateResponse(
            mode="keywords",
            used_model=str(result.get("used_model") or ""),
            used_web_search=bool(result.get("used_web_search")),
            scene_name=str(result.get("scene_name") or ""),
            scene_summary=str(result.get("scene_summary") or ""),
            selected_layer_id=str(result.get("selected_layer_id") or ""),
            scene_layers=result.get("scene_layers") or [],
        )

        self.assertTrue(payload.scene_name)
        self.assertEqual(len(payload.scene_layers), 1)
        flattened = list(_walk_layers(payload.scene_layers))
        self.assertGreaterEqual(len(flattened), 5)
        self.assertIn(payload.selected_layer_id, {layer.id for layer in flattened})
        for layer in flattened:
            self.assertTrue(layer.tags)
            self.assertTrue(layer.reuse_id)
            self.assertTrue(layer.reuse_hint)
            self.assertGreaterEqual(len(layer.objects), 1)
            for obj in layer.objects:
                self.assertTrue(obj.tags)
                self.assertTrue(obj.reuse_id)
                self.assertTrue(obj.reuse_hint)

    def test_mock_text_scene_tree_includes_reusable_metadata(self) -> None:
        result = self.provider.generate_scene_tree_from_text(
            text=(
                "这个场景从一座以钟楼和实验楼著称的学院展开。"
                "学生先穿过夜间开放的街区，再进入主教学楼。"
                "最后在实验桌前围绕力学装置进行讲解和互动。"
            ),
            layer_count=4,
        )
        payload = SceneTreeGenerateResponse(
            mode="long_text",
            used_model=str(result.get("used_model") or ""),
            used_web_search=bool(result.get("used_web_search")),
            scene_name=str(result.get("scene_name") or ""),
            scene_summary=str(result.get("scene_summary") or ""),
            selected_layer_id=str(result.get("selected_layer_id") or ""),
            scene_layers=result.get("scene_layers") or [],
        )

        flattened = list(_walk_layers(payload.scene_layers))
        self.assertGreaterEqual(len(flattened), 4)
        deepest = flattened[-1]
        self.assertEqual(payload.selected_layer_id, deepest.id)
        self.assertTrue(deepest.reuse_hint)
        self.assertTrue(deepest.objects[0].reuse_hint)

    def test_scene_generation_request_allows_missing_layer_count(self) -> None:
        request = SceneTreeGenerateRequest(mode="keywords", input_text="虚拟校园, 研讨舱")
        self.assertIsNone(request.layer_count)

    def test_mock_keywords_scene_tree_no_longer_clamps_layer_count_to_minimum(self) -> None:
        result = self.provider.generate_scene_tree_from_keywords(
            keywords="单层空间, 观察点",
            layer_count=1,
        )
        payload = SceneTreeGenerateResponse(
            mode="keywords",
            used_model=str(result.get("used_model") or ""),
            used_web_search=bool(result.get("used_web_search")),
            scene_name=str(result.get("scene_name") or ""),
            scene_summary=str(result.get("scene_summary") or ""),
            selected_layer_id=str(result.get("selected_layer_id") or ""),
            scene_layers=result.get("scene_layers") or [],
        )

        flattened = list(_walk_layers(payload.scene_layers))
        self.assertEqual(len(flattened), 1)
        self.assertEqual(payload.selected_layer_id, payload.scene_layers[0].id)

    def test_parallel_roots_fall_back_to_deepest_valid_leaf(self) -> None:
        result = _normalize_generated_scene_result(
            {
                "scene_name": "并行场景",
                "scene_summary": "测试并行根节点回退逻辑。",
                "selected_layer_id": "",
                "scene_layers": [
                    {
                        "id": "root-a",
                        "title": "入口广场",
                        "scope_label": "外部入口",
                        "summary": "用于分流访客的入口区域。",
                        "atmosphere": "开阔明亮",
                        "rules": "所有人都可通行",
                        "entrance": "从主干道直接进入",
                        "tags": "入口,广场",
                        "reuse_id": "reuse-root-a",
                        "reuse_hint": "可复用于大型园区入口。",
                        "objects": [],
                        "children": [],
                    },
                    {
                        "id": "root-b",
                        "title": "实验楼",
                        "scope_label": "建筑层",
                        "summary": "用于组织多间实验空间的建筑。",
                        "atmosphere": "安静克制",
                        "rules": "需凭权限进入",
                        "entrance": "穿过门禁大厅进入",
                        "tags": "实验楼,门禁",
                        "reuse_id": "reuse-root-b",
                        "reuse_hint": "可复用于教学建筑。",
                        "objects": [],
                        "children": [
                            {
                                "id": "leaf-b1",
                                "title": "显微观察室",
                                "scope_label": "房间层",
                                "summary": "用于单人或双人观察的封闭房间。",
                                "atmosphere": "低噪、聚焦",
                                "rules": "进入前需更换实验服",
                                "entrance": "沿走廊进入隔音门后抵达",
                                "tags": "观察室,隔音",
                                "reuse_id": "reuse-leaf-b1",
                                "reuse_hint": "可复用于精密观察空间。",
                                "objects": [],
                                "children": [],
                            }
                        ],
                    },
                ],
            },
            used_model="test-model",
            used_web_search=False,
        )

        self.assertEqual(result["selected_layer_id"], "leaf-b1")

    def test_scene_prompt_mentions_parallel_layers_and_soft_layer_count(self) -> None:
        template = load_prompt_template("openai_setting_prompt.txt")
        keywords_system = template.require("generate_scene_keywords_system")
        keywords_user = template.require("generate_scene_keywords_user")
        long_text_system = template.require("generate_scene_long_text_system")

        self.assertIn("只是深度偏好", keywords_system)
        self.assertIn("允许生成平行兄弟层级", keywords_system)
        self.assertIn("layer_count_hint", keywords_user)
        self.assertIn("平行兄弟层级", keywords_user)
        self.assertIn("不要求整棵树必须是单链结构", long_text_system)


if __name__ == "__main__":
    unittest.main()
