from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.api.dependencies import get_container
from app.api.routers import study as study_router
from app.core.bootstrap import Container
from app.core.settings import Settings
from app.models.domain import SceneProfileRecord
from app.persistence.models import SessionSceneRow


def scene(name):
    return {
        "scene_id": "fixture-layer",
        "scene_name": name,
        "title": name,
        "summary": f"{name} summary",
        "scene_tree": [
            {
                "id": "fixture-layer",
                "title": name,
                "scope_label": "local fixture",
                "summary": "",
                "atmosphere": "",
                "rules": "",
                "entrance": "",
            }
        ],
    }


class StudySessionSceneTransactionTests(TestCase):
    def setUp(self):
        tmp = self.enterContext(TemporaryDirectory())
        self.container = Container(
            Settings(
                database_url=f"sqlite:///{tmp}/study.db",
                storage_root=str(Path(tmp) / "storage"),
                plan_provider="mock",
                auto_migrate_local_data=False,
                ocr_engine="disabled",
            )
        )
        self.addCleanup(self.container.close)
        self.service = self.container.study_session_service
        self.repo = self.service.repository
        self.persona_id = self.container.persona_engine.list_personas()[0].id
        app = FastAPI()
        app.include_router(study_router.router)
        app.dependency_overrides[get_container] = lambda: self.container
        self.client = self.enterContext(TestClient(app, raise_server_exceptions=False))

    def create(self, profile=None):
        return self.client.post(
            "/study-sessions",
            json={
                "document_id": "",
                "persona_id": self.persona_id,
                "study_unit_id": "unit-initial",
                "scene_profile": profile,
            },
        )

    def created(self, profile=None):
        response = self.create(profile)
        self.assertEqual(response.status_code, 200, response.text)
        return response.json()

    def patch_session(self, session_id, payload):
        return self.client.patch(f"/study-sessions/{session_id}", json=payload)

    def seed_legacy_profile(self, profile):
        initial = self.created()

        def legacy_shape(record):
            record.scene_profile = SceneProfileRecord.model_validate(profile)

        return self.repo.mutate(session_id=initial["id"], mutation=legacy_shape)

    def stored_scene_ids(self):
        with self.repo.database.session() as db:
            return db.scalars(select(SessionSceneRow.scene_instance_id)).all()

    def fail_scene_insert(self):
        # Fail the second write during flush, after Session insert / CAS issued.
        with self.repo.database.engine.begin() as connection:
            connection.exec_driver_sql("""
                CREATE TRIGGER fixture_abort_scene_insert BEFORE INSERT ON session_scenes
                BEGIN SELECT RAISE(ABORT, 'fixture scene insert failure'); END
            """)

    def fail_session_write(self, operation):
        statement = {
            "create": "CREATE TRIGGER fixture_abort_session_write BEFORE INSERT ON study_sessions",
            "update": "CREATE TRIGGER fixture_abort_session_write BEFORE UPDATE ON study_sessions",
        }[operation]
        with self.repo.database.engine.begin() as connection:
            connection.exec_driver_sql(
                statement
                + " BEGIN SELECT RAISE(ABORT, 'fixture session write failure'); END"
            )

    def assert_scene_matches_session(self, projection):
        saved = self.repo.require(projection["id"])
        bound = self.container.session_scene_service.require_scene(
            saved.scene_instance_id
        )
        self.assertEqual(bound.session_id, saved.id)
        self.assertEqual(bound.document_id, saved.document_id)
        self.assertEqual(bound.persona_id, saved.persona_id)
        self.assertEqual(bound.scene_instance_id, projection["scene_instance_id"])
        self.assertEqual(bound.scene_profile, saved.scene_profile)
        self.assertEqual(
            bound.scene_profile.model_dump(mode="json"), projection["scene_profile"]
        )
        return bound

    def test_create_commits_both_rows_and_returns_committed_profile(self):
        saved = self.created(scene("Creation context"))
        self.assertEqual(saved["revision"], 0)
        bound = self.assert_scene_matches_session(saved)
        self.assertEqual(self.stored_scene_ids(), [bound.scene_instance_id])
        self.assertIn("Creation context summary", saved["session_system_prompt"])

    def test_create_rolls_back_session_if_scene_insert_fails(self):
        self.fail_scene_insert()
        response = self.create(scene("Not committed"))
        self.assertEqual(response.status_code, 500, response.text)
        self.assertEqual(self.repo.list(), [])
        self.assertEqual(self.stored_scene_ids(), [])

    def test_rejected_session_insert_does_not_publish_a_scene(self):
        self.fail_session_write("create")
        response = self.create(scene("Rejected create"))
        self.assertNotEqual(response.status_code, 200, response.text)
        self.assertEqual(self.repo.list(), [])
        self.assertEqual(self.stored_scene_ids(), [])

    def test_rejected_session_update_does_not_publish_a_scene(self):
        initial = self.created()
        before = self.repo.require(initial["id"])
        self.fail_session_write("update")
        response = self.patch_session(
            initial["id"], {"scene_profile": scene("Rejected update")}
        )
        self.assertNotEqual(response.status_code, 200, response.text)
        self.assertEqual(self.repo.require(initial["id"]), before)
        self.assertEqual(self.stored_scene_ids(), [])

    def test_patch_rolls_back_context_and_scene_if_scene_insert_fails(self):
        initial = self.created(scene("Committed context"))
        follow_up = self.service.schedule_follow_up(
            session_id=initial["id"],
            delay_seconds=10,
            hidden_message="Continue fixture",
        )
        before = self.repo.require(initial["id"])
        before_ids = self.stored_scene_ids()
        self.fail_scene_insert()
        response = self.patch_session(
            initial["id"],
            {
                "study_unit_id": "not-committed",
                "scene_profile": scene("Not committed"),
            },
        )
        self.assertEqual(response.status_code, 500, response.text)
        saved = self.repo.require(initial["id"])
        self.assertEqual(saved, before)
        self.assertEqual(saved.pending_follow_ups[0].id, follow_up.id)
        self.assertEqual(saved.pending_follow_ups[0].status, "pending")
        self.assertEqual(self.stored_scene_ids(), before_ids)

    def test_legacy_scene_binding_uses_only_one_revision_and_is_not_duplicated(self):
        legacy = self.seed_legacy_profile(scene("Legacy context"))
        first = self.patch_session(legacy.id, {"study_unit_id": "unit-next"})
        self.assertEqual(first.status_code, 200, first.text)
        bound = first.json()
        self.assertEqual(bound["revision"], legacy.revision + 1)
        self.assertEqual(bound["study_unit_title"], "unit-next")
        self.assertIn("Legacy context summary", bound["session_system_prompt"])
        self.assert_scene_matches_session(bound)
        second = self.patch_session(legacy.id, {"study_unit_id": "unit-later"})
        self.assertEqual(second.status_code, 200, second.text)
        self.assertEqual(second.json()["scene_instance_id"], bound["scene_instance_id"])
        self.assertEqual(self.stored_scene_ids(), [bound["scene_instance_id"]])

    def test_explicit_clear_does_not_create_a_legacy_scene_or_remove_historical_rows(
        self,
    ):
        legacy = self.seed_legacy_profile(scene("Legacy cleared"))
        active = self.created(scene("Existing cleared"))
        for session_id, revision in (
            (legacy.id, legacy.revision),
            (active["id"], active["revision"]),
        ):
            with self.subTest(session_id=session_id):
                response = self.patch_session(session_id, {"scene_profile": None})
                self.assertEqual(response.status_code, 200, response.text)
                saved = self.repo.require(session_id)
                self.assertEqual(saved.revision, revision + 1)
                self.assertEqual(saved.scene_instance_id, "")
                self.assertIsNone(saved.scene_profile)
                self.assertNotIn("cleared summary", saved.session_system_prompt)
                self.assertEqual(self.stored_scene_ids(), [active["scene_instance_id"]])

    def test_cas_retry_discards_legacy_clone_when_concurrent_request_binds_scene(self):
        legacy = self.seed_legacy_profile(scene("Old scene"))
        real_prompt = study_router.build_study_session_system_prompt
        attempts = []
        concurrent = []

        def interleave(**kwargs):
            if kwargs["study_unit_id"] == "unit-next":
                attempts.append(kwargs["scene_profile"].scene_name)
                if len(attempts) == 1:
                    # Independent API request commits after the first read, before CAS.
                    response = self.patch_session(
                        legacy.id, {"scene_profile": scene("Winning scene")}
                    )
                    self.assertEqual(response.status_code, 200, response.text)
                    concurrent.append(response.json())
            return real_prompt(**kwargs)

        with patch.object(
            study_router, "build_study_session_system_prompt", side_effect=interleave
        ):
            result = self.patch_session(legacy.id, {"study_unit_id": "unit-next"})
        self.assertEqual(result.status_code, 200, result.text)
        final = result.json()
        self.assertEqual(attempts, ["Old scene", "Winning scene"])
        self.assertEqual(final["revision"], legacy.revision + 2)
        self.assertEqual(final["study_unit_id"], "unit-next")
        self.assertEqual(final["scene_instance_id"], concurrent[0]["scene_instance_id"])
        self.assertIn("Winning scene summary", final["session_system_prompt"])
        self.assertNotIn("Old scene summary", final["session_system_prompt"])
        self.assert_scene_matches_session(final)
        self.assertEqual(self.stored_scene_ids(), [final["scene_instance_id"]])

    def test_scene_only_retry_derives_prompt_from_winning_unit_patch(self):
        initial = self.created()
        real_prompt = study_router.build_study_session_system_prompt
        attempts = []

        def interleave(**kwargs):
            if kwargs["scene_profile"] is not None:
                attempts.append(kwargs["study_unit_id"])
                if len(attempts) == 1:
                    response = self.patch_session(
                        initial["id"], {"study_unit_id": "unit-winner"}
                    )
                    self.assertEqual(response.status_code, 200, response.text)
            return real_prompt(**kwargs)

        with patch.object(
            study_router, "build_study_session_system_prompt", side_effect=interleave
        ):
            result = self.patch_session(
                initial["id"], {"scene_profile": scene("New scene")}
            )
        self.assertEqual(result.status_code, 200, result.text)
        final = result.json()
        self.assertEqual(attempts, ["unit-initial", "unit-winner"])
        self.assertEqual(final["revision"], initial["revision"] + 2)
        self.assertEqual(final["study_unit_id"], "unit-winner")
        self.assertEqual(final["study_unit_title"], "unit-winner")
        self.assertIn("unit-winner", final["session_system_prompt"])
        self.assertIn("New scene summary", final["session_system_prompt"])
        self.assert_scene_matches_session(final)
        self.assertEqual(self.stored_scene_ids(), [final["scene_instance_id"]])
