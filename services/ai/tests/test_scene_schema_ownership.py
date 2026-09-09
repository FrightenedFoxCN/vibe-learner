from tests.support.scene_samples import scene_proposal_payload as _proposal_payload, scene_layer_payload as _layer_payload

from pathlib import Path
from tempfile import TemporaryDirectory
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import event

from app.models.api import SceneTreeGenerateRequest, UpsertSceneLibraryRequest
from app.models.domain import ReusableSceneNodeRecord, SceneLibraryRecord
from app.models.scene import (
    SceneCommittedSaveV1,
    decode_scene_tree_proposal,
    project_scene_tree_proposal,
)
from app.persistence.models import SceneLibraryRow
from app.services.local_store import LocalJsonStore
from app.services.model_provider import MockModelProvider
from app.services.scene_library import SceneLibraryService
from app.services.scene_setup import SceneSetupService


class SceneSchemaOwnershipTests(unittest.TestCase):
    def test_model_proposal_rejects_application_and_reuse_identity(self) -> None:
        payload = _proposal_payload()
        payload["scene_layers"][0]["id"] = "model-layer-id"

        with self.assertRaisesRegex(
            RuntimeError,
            r"scene_layers\.0\.id:extra_forbidden",
        ):
            decode_scene_tree_proposal(payload)

        payload = _proposal_payload()
        payload["scene_layers"][0]["objects"][0]["reuse_id"] = "model-reuse-id"
        with self.assertRaisesRegex(
            RuntimeError,
            r"scene_layers\.0\.objects\.0\.reuse_id:extra_forbidden",
        ):
            decode_scene_tree_proposal(payload)

    def test_model_proposal_rejects_wrong_types_and_invalid_selected_path(self) -> None:
        payload = _proposal_payload()
        payload["scene_layers"][0]["tags"] = "room,study"
        with self.assertRaisesRegex(RuntimeError, r"scene_layers\.0\.tags:list_type"):
            decode_scene_tree_proposal(payload)

        payload = _proposal_payload()
        payload["selected_path"] = [2]
        with self.assertRaisesRegex(RuntimeError, "scene_selected_path_invalid"):
            decode_scene_tree_proposal(payload)

    def test_model_proposal_enforces_depth_budget(self) -> None:
        payload = _proposal_payload()
        current = payload["scene_layers"][0]
        payload["selected_path"] = [0]
        for index in range(8):
            child = _layer_payload(title=f"Layer {index + 2}")
            current["children"] = [child]
            current = child

        with self.assertRaisesRegex(RuntimeError, "scene_depth_exceeded"):
            decode_scene_tree_proposal(payload)

    def test_projection_assigns_identity_and_fences_reusable_refs(self) -> None:
        payload = _proposal_payload()
        proposal = decode_scene_tree_proposal(payload)
        projection = project_scene_tree_proposal(proposal)

        layer = projection.scene_layers[0]
        self.assertTrue(layer.id.startswith("scene-layer-"))
        self.assertTrue(layer.reuse_id.startswith("scene-layer-reuse-"))
        self.assertTrue(layer.objects[0].id.startswith("scene-object-"))
        self.assertEqual(projection.selected_layer_id, layer.id)

        payload = _proposal_payload()
        payload["scene_layers"][0]["reusable_node_ref"] = "allowed-layer"
        proposal = decode_scene_tree_proposal(payload)
        with self.assertRaisesRegex(ValueError, "scene_reusable_node_ref_not_allowed"):
            project_scene_tree_proposal(proposal)

        reusable = ReusableSceneNodeRecord(
            node_id="allowed-layer",
            node_type="layer",
            title="Reusable room",
            reuse_id="server-owned-reuse-id",
            created_at="2026-08-24T10:00:00+00:00",
            updated_at="2026-08-24T10:00:00+00:00",
        )
        allowed_projection = project_scene_tree_proposal(
            proposal,
            allowed_reusable_nodes={reusable.node_id: reusable},
        )
        self.assertEqual(
            allowed_projection.scene_layers[0].reuse_id,
            reusable.reuse_id,
        )

    def test_public_generation_and_save_contracts_are_strict(self) -> None:
        with self.assertRaises(ValidationError):
            SceneTreeGenerateRequest(
                mode="unsupported",
                input_text="Room",
            )
        with self.assertRaises(ValidationError):
            SceneTreeGenerateRequest(
                mode="keywords",
                input_text="Room",
                layer_count=9,
            )

        result = MockModelProvider().generate_scene_tree_from_keywords(
            keywords="Room, Study",
            layer_count=1,
        )
        payload = _save_payload(result)
        payload["scene_profile"] = {"scene_id": "caller-owned"}
        with self.assertRaises(ValidationError):
            UpsertSceneLibraryRequest.model_validate(payload)

    def test_committed_save_rejects_duplicate_ids_and_missing_selection(self) -> None:
        result = MockModelProvider().generate_scene_tree_from_keywords(
            keywords="Room, Study",
            layer_count=1,
        )
        payload = _save_payload(result)
        payload["scene_layers"][0]["objects"][0]["id"] = payload[
            "scene_layers"
        ][0]["id"]
        with self.assertRaisesRegex(ValidationError, "scene_committed_id_duplicate"):
            SceneCommittedSaveV1.model_validate(payload)

        payload = _save_payload(result)
        payload["selected_layer_id"] = "missing-layer"
        with self.assertRaisesRegex(ValidationError, "scene_selected_layer_missing"):
            SceneCommittedSaveV1.model_validate(payload)

    def test_scene_library_save_uses_revision_cas_and_server_profile(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = LocalJsonStore(Path(temp_dir))
            try:
                service = SceneLibraryService(store)
                result = MockModelProvider().generate_scene_tree_from_keywords(
                    keywords="Room, Study",
                    layer_count=1,
                )
                request = UpsertSceneLibraryRequest.model_validate(
                    _save_payload(result)
                )
                created = service.upsert_scene(
                    scene_id=None,
                    scene_name=request.scene_name,
                    scene_summary=request.scene_summary,
                    scene_layers=request.to_domain_layers(),
                    selected_layer_id=request.selected_layer_id,
                    collapsed_layer_ids=request.collapsed_layer_ids,
                    expected_revision=request.expected_revision,
                )
                self.assertEqual(created.revision, 1)
                self.assertIsNotNone(created.scene_profile)
                self.assertEqual(
                    created.scene_profile.scene_id,
                    created.selected_layer_id,
                )

                updated = service.upsert_scene(
                    scene_id=created.scene_id,
                    scene_name="Updated room",
                    scene_summary=created.scene_summary,
                    scene_layers=created.scene_layers,
                    selected_layer_id=created.selected_layer_id,
                    collapsed_layer_ids=created.collapsed_layer_ids,
                    expected_revision=created.revision,
                )
                self.assertEqual(updated.revision, 2)

                with self.assertRaises(HTTPException) as context:
                    service.upsert_scene(
                        scene_id=created.scene_id,
                        scene_name="Stale overwrite",
                        scene_summary=created.scene_summary,
                        scene_layers=created.scene_layers,
                        selected_layer_id=created.selected_layer_id,
                        collapsed_layer_ids=created.collapsed_layer_ids,
                        expected_revision=created.revision,
                    )
                self.assertEqual(context.exception.status_code, 409)
                self.assertEqual(context.exception.detail, "scene_revision_conflict")
                persisted = store.load_item(
                    "scene_library",
                    created.scene_id,
                    SceneLibraryRecord,
                )
                self.assertEqual(persisted.revision, 2)
                self.assertEqual(persisted.scene_name, "Updated room")
            finally:
                store.close()

    def test_scene_library_concurrent_updates_allow_exactly_one_revision_winner(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = LocalJsonStore(Path(temp_dir))
            try:
                service = SceneLibraryService(store)
                result = MockModelProvider().generate_scene_tree_from_keywords(
                    keywords="Room, Study",
                    layer_count=1,
                )
                request = UpsertSceneLibraryRequest.model_validate(
                    _save_payload(result)
                )
                created = service.upsert_scene(
                    scene_id=None,
                    scene_name=request.scene_name,
                    scene_summary=request.scene_summary,
                    scene_layers=request.to_domain_layers(),
                    selected_layer_id=request.selected_layer_id,
                    collapsed_layer_ids=request.collapsed_layer_ids,
                    expected_revision=request.expected_revision,
                )

                update_barrier = Barrier(2)

                def synchronize_scene_updates(
                    _connection,
                    _cursor,
                    statement,
                    _parameters,
                    _context,
                    _executemany,
                ) -> None:
                    if not statement.lstrip().upper().startswith("UPDATE"):
                        return
                    if "scene_library_entries" not in statement:
                        return
                    update_barrier.wait(timeout=5)

                event.listen(
                    store.database.engine,
                    "before_cursor_execute",
                    synchronize_scene_updates,
                )

                candidates = [
                    ("Concurrent winner A", "Summary committed by A."),
                    ("Concurrent winner B", "Summary committed by B."),
                ]

                def update_scene(candidate: tuple[str, str]):
                    scene_name, scene_summary = candidate
                    try:
                        return service.upsert_scene(
                            scene_id=created.scene_id,
                            scene_name=scene_name,
                            scene_summary=scene_summary,
                            scene_layers=created.scene_layers,
                            selected_layer_id=created.selected_layer_id,
                            collapsed_layer_ids=created.collapsed_layer_ids,
                            expected_revision=created.revision,
                        )
                    except HTTPException as exc:
                        return exc

                try:
                    with ThreadPoolExecutor(max_workers=2) as executor:
                        outcomes = list(
                            executor.map(
                                update_scene,
                                candidates,
                            )
                        )
                finally:
                    event.remove(
                        store.database.engine,
                        "before_cursor_execute",
                        synchronize_scene_updates,
                    )

                successes = [
                    outcome
                    for outcome in outcomes
                    if isinstance(outcome, SceneLibraryRecord)
                ]
                conflicts = [
                    outcome
                    for outcome in outcomes
                    if isinstance(outcome, HTTPException)
                    and outcome.status_code == 409
                    and outcome.detail == "scene_revision_conflict"
                ]
                self.assertEqual(len(successes), 1)
                self.assertEqual(len(conflicts), 1)
                self.assertEqual(successes[0].revision, created.revision + 1)
                winning_candidate = next(
                    candidate
                    for candidate, outcome in zip(candidates, outcomes, strict=True)
                    if isinstance(outcome, SceneLibraryRecord)
                )
                losing_candidate = next(
                    candidate
                    for candidate, outcome in zip(candidates, outcomes, strict=True)
                    if isinstance(outcome, HTTPException)
                )
                persisted = service.require_scene(created.scene_id)
                self.assertEqual(persisted.revision, created.revision + 1)
                self.assertEqual(
                    (persisted.scene_name, persisted.scene_summary),
                    winning_candidate,
                )
                self.assertNotEqual(
                    (persisted.scene_name, persisted.scene_summary),
                    losing_candidate,
                )
                with store.database.session() as session:
                    row = session.get(SceneLibraryRow, created.scene_id)
                    self.assertIsNotNone(row)
                    assert row is not None
                    self.assertEqual(row.revision, persisted.revision)
                    self.assertEqual(row.scene_name, persisted.scene_name)
                    self.assertEqual(row.payload["revision"], persisted.revision)
                    self.assertEqual(
                        (row.payload["scene_name"], row.payload["scene_summary"]),
                        winning_candidate,
                    )
            finally:
                store.close()

    def test_scene_library_cas_rolls_back_after_statement_failure(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = LocalJsonStore(Path(temp_dir))
            try:
                service = SceneLibraryService(store)
                result = MockModelProvider().generate_scene_tree_from_keywords(
                    keywords="Room, Study",
                    layer_count=1,
                )
                request = UpsertSceneLibraryRequest.model_validate(
                    _save_payload(result)
                )
                created = service.upsert_scene(
                    scene_id=None,
                    scene_name=request.scene_name,
                    scene_summary=request.scene_summary,
                    scene_layers=request.to_domain_layers(),
                    selected_layer_id=request.selected_layer_id,
                    collapsed_layer_ids=request.collapsed_layer_ids,
                    expected_revision=request.expected_revision,
                )

                def fail_after_scene_update(
                    _connection,
                    _cursor,
                    statement,
                    _parameters,
                    _context,
                    _executemany,
                ) -> None:
                    if not statement.lstrip().upper().startswith("UPDATE"):
                        return
                    if "scene_library_entries" in statement:
                        raise RuntimeError("scene_cas_injected_failure")

                event.listen(
                    store.database.engine,
                    "after_cursor_execute",
                    fail_after_scene_update,
                )
                try:
                    with self.assertRaisesRegex(
                        RuntimeError,
                        "scene_cas_injected_failure",
                    ):
                        service.upsert_scene(
                            scene_id=created.scene_id,
                            scene_name="Must roll back",
                            scene_summary="This payload must not be partially visible.",
                            scene_layers=created.scene_layers,
                            selected_layer_id=created.selected_layer_id,
                            collapsed_layer_ids=created.collapsed_layer_ids,
                            expected_revision=created.revision,
                        )
                finally:
                    event.remove(
                        store.database.engine,
                        "after_cursor_execute",
                        fail_after_scene_update,
                    )

                persisted = service.require_scene(created.scene_id)
                self.assertEqual(persisted.revision, created.revision)
                self.assertEqual(persisted.scene_name, created.scene_name)
                self.assertEqual(persisted.scene_summary, created.scene_summary)
                with store.database.session() as session:
                    row = session.get(SceneLibraryRow, created.scene_id)
                    self.assertIsNotNone(row)
                    assert row is not None
                    self.assertEqual(row.revision, created.revision)
                    self.assertEqual(row.scene_name, created.scene_name)
                    self.assertEqual(row.payload["revision"], created.revision)
                    self.assertEqual(row.payload["scene_name"], created.scene_name)
            finally:
                store.close()

    def test_scene_setup_save_uses_revision_cas(self) -> None:
        with TemporaryDirectory() as temp_dir:
            store = LocalJsonStore(Path(temp_dir))
            try:
                service = SceneSetupService(store)
                result = MockModelProvider().generate_scene_tree_from_keywords(
                    keywords="Room, Study",
                    layer_count=1,
                )
                request = SceneCommittedSaveV1.model_validate(_save_payload(result))
                created = service.upsert_state(
                    scene_name=request.scene_name,
                    scene_summary=request.scene_summary,
                    scene_layers=request.to_domain_layers(),
                    selected_layer_id=request.selected_layer_id,
                    collapsed_layer_ids=request.collapsed_layer_ids,
                    expected_revision=request.expected_revision,
                )
                self.assertEqual(created.revision, 1)

                with self.assertRaises(HTTPException) as context:
                    service.upsert_state(
                        scene_name=request.scene_name,
                        scene_summary=request.scene_summary,
                        scene_layers=request.to_domain_layers(),
                        selected_layer_id=request.selected_layer_id,
                        collapsed_layer_ids=request.collapsed_layer_ids,
                        expected_revision=0,
                    )
                self.assertEqual(context.exception.status_code, 409)
                self.assertEqual(service.get_state().revision, 1)
            finally:
                store.close()






def _save_payload(result: dict[str, object]) -> dict[str, object]:
    return {
        "contract_version": "scene-committed-save-v1",
        "expected_revision": 0,
        "scene_name": result["scene_name"],
        "scene_summary": result["scene_summary"],
        "scene_layers": deepcopy(result["scene_layers"]),
        "selected_layer_id": result["selected_layer_id"],
        "collapsed_layer_ids": [],
    }


if __name__ == "__main__":
    unittest.main()
