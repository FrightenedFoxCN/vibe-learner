import unittest

from app.models.api import SceneTreeGenerateResponse
from app.services.model_provider import MockModelProvider


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


if __name__ == "__main__":
    unittest.main()
