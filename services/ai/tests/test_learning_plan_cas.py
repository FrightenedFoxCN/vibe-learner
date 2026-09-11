"""Plan CAS regressions independent of the revision-preview workflow."""
from pathlib import Path
from tempfile import TemporaryDirectory
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
import unittest
from fastapi import HTTPException
from app.models.domain import VersionedLearningPlanRecord
from app.persistence.learning_plan_repository import LearningPlanRepository
from app.services.local_store import LocalJsonStore


class LearningPlanCasTests(unittest.TestCase):
    def setUp(self):
        self.temp = TemporaryDirectory()
        self.store = LocalJsonStore(Path(self.temp.name))
        self.repo = LearningPlanRepository(self.store.database)
        self.plan = VersionedLearningPlanRecord(id='cas-plan', document_id='', persona_id='mentor',
            creation_mode='goal_only', course_title='Original', objective='Learn', overview='Overview', today_tasks=['Read'],
            created_at='2026-09-11T00:00:00Z')
        self.repo.import_legacy([self.plan])

    def tearDown(self):
        self.store.close()
        self.temp.cleanup()

    def test_same_base_concurrent_writers_have_one_winner(self):
        barrier = Barrier(2)
        def write(title):
            def mutation(plan):
                barrier.wait(timeout=5)
                plan.course_title = title
                return plan
            try:
                return self.repo.mutate(self.plan.id, mutation, expected_revision=0).revision
            except HTTPException as error:
                return error.status_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            result = list(pool.map(write, ['First', 'Second']))
        self.assertEqual(sorted(result), [1, 409])
        self.assertEqual(self.repo.require(self.plan.id).revision, 1)

    def test_old_import_cannot_replace_new_revision(self):
        self.repo.mutate(self.plan.id, lambda p: p.model_copy(update={'course_title': 'Edited'}))
        with self.assertRaises(ValueError):
            self.repo.import_legacy([self.plan])
        self.assertEqual(self.repo.require(self.plan.id).course_title, 'Edited')

    def test_delete_tombstone_prevents_legacy_resurrection(self):
        self.repo.mutate(self.plan.id, lambda p: p, expected_revision=0, deleted=True)
        with self.assertRaises(ValueError):
            self.repo.import_legacy([self.plan])
        self.assertEqual(self.repo.list(), [])
