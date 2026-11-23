from fastapi import FastAPI

from app.api.routers.persona_scene import router
from tests.support.api import ContainerTestCase, isolated_client


class SceneLibraryRevisionTests(ContainerTestCase):
    def test_delete_requires_confirmed_revision_and_preserves_concurrent_save(self):
        app = FastAPI()
        app.include_router(router)
        payload = {
            "expected_revision": 0,
            "scene_name": "Original",
            "scene_summary": "A synthetic room.",
            "selected_layer_id": "root",
            "scene_layers": [
                {
                    "id": "root",
                    "title": "Room",
                    "scope_label": "Room",
                    "summary": "Quiet.",
                    "atmosphere": "Calm.",
                    "rules": "Read.",
                    "entrance": "Door.",
                    "reuse_id": "root-reuse",
                }
            ],
        }
        with isolated_client(app, self.container) as client:
            created = client.post("/scene-library", json=payload)
            self.assertEqual(created.status_code, 200, created.text)
            path = f"/scene-library/{created.json()['scene_id']}"
            seen = client.get(path).json()
            updated = client.put(
                path,
                json={
                    **payload,
                    "expected_revision": seen["revision"],
                    "scene_name": "Updated",
                },
            )
            self.assertEqual(updated.status_code, 200, updated.text)
            self.assertEqual(client.delete(path).status_code, 422)
            rejected = client.delete(
                path, params={"expected_revision": seen["revision"]}
            )
            self.assertEqual(rejected.status_code, 409)
            self.assertEqual(client.get(path).json(), updated.json())
            deleted = client.delete(
                path, params={"expected_revision": updated.json()["revision"]}
            )
            self.assertEqual(deleted.status_code, 200, deleted.text)
            self.assertEqual(client.get(path).status_code, 404)
            self.assertEqual(client.get("/scene-library").json()["items"], [])
