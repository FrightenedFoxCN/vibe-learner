import tempfile
import unittest
from pathlib import Path

from app.models.api import CreateReusableSceneNodeRequest
from app.models.domain import SceneLayerStateRecord, SceneObjectStateRecord
from app.services.local_store import LocalJsonStore
from app.services.reusable_scene_nodes import ReusableSceneNodeLibraryService


class ReusableSceneNodeLibraryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        store = LocalJsonStore(Path(self.temp_dir.name))
        self.service = ReusableSceneNodeLibraryService(store)

    def test_create_and_list_layer_node(self) -> None:
        created = self.service.create_node(
            CreateReusableSceneNodeRequest(
                node_type="layer",
                title="实验教室模板",
                summary="适合挂接实验装置和讲台说明。",
                tags=["实验", "教室"],
                reuse_id="scene-layer-reuse-lab",
                reuse_hint="保留实验台、规则和进入方式即可复用。",
                source_scene_name="力学教室",
                layer_node=SceneLayerStateRecord(
                    id="layer-a",
                    title="实验教室",
                    scope_label="微观教室",
                    summary="实验课主场景。",
                    atmosphere="安静但紧张。",
                    rules="进入前要整理器材。",
                    entrance="从走廊推门进入。",
                    tags="实验,教室",
                    reuse_id="scene-layer-reuse-lab",
                    reuse_hint="保留实验台、规则和进入方式即可复用。",
                    objects=[],
                    children=[],
                ),
            )
        )

        items = self.service.list_nodes()
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].node_id, created.node_id)
        self.assertEqual(items[0].node_type, "layer")
        self.assertEqual(items[0].layer_node.title, "实验教室")

    def test_create_and_delete_object_node(self) -> None:
        created = self.service.create_node(
            CreateReusableSceneNodeRequest(
                node_type="object",
                title="黑板模板",
                summary="标准板书物体。",
                tags=["板书", "课堂"],
                reuse_id="scene-object-reuse-board",
                reuse_hint="适合插入几乎所有课堂场景。",
                object_node=SceneObjectStateRecord(
                    id="obj-a",
                    name="黑板",
                    description="可书写公式和图示。",
                    interaction="用于指向与板书演示。",
                    tags="板书,课堂",
                    reuse_id="scene-object-reuse-board",
                    reuse_hint="适合插入几乎所有课堂场景。",
                ),
            )
        )

        self.service.delete_node(created.node_id)
        self.assertEqual(self.service.list_nodes(), [])


if __name__ == "__main__":
    unittest.main()
