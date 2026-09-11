"""Historical data migration and PostgreSQL checks using disposable databases only."""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from alembic import command
from sqlalchemy import MetaData, Table, select, create_engine
from tests.support.migrations import alembic_config
from tests import test_learning_plan_operation as creation_fixtures
from app.persistence.database import Database
from app.persistence.learning_plan_repository import LearningPlanRepository
from app.persistence.plan_revision_repository import PlanRevisionRepository
from app.models.plan_revision import PlanRevisionRequestV1
from app.persistence.learning_plan_operation_repository import LearningPlanOperationRepository


class IndependentMigrationTests(unittest.TestCase):
    def test_0019_historical_creation_receipt_survives_upgrade_and_edit(self):
        source=creation_fixtures.LearningPlanOperationTests(); source.setUp(); self.addCleanup(source.tearDown)
        source.test_success_commits_all_projections_and_duplicate_reuses_snapshot()
        with TemporaryDirectory() as temp:
            url=os.environ.get('VIBE_INDEPENDENT_MIGRATION_URL') or f'sqlite:///{Path(temp)/"old.db"}'
            engine=create_engine(url); self.addCleanup(engine.dispose)
            config=alembic_config(url)
            with patch.dict(os.environ,{'DATABASE_URL':url}): command.upgrade(config,'20260909_0019')
            tables=['documents','document_debug_records','planning_traces','learning_plans','harness_operation_bindings','learning_plan_operations']
            metadata=MetaData()
            with source.store.database.engine.connect() as src, engine.begin() as target:
                for name in tables:
                    old=Table(name,metadata,autoload_with=target)
                    current=Table(name,MetaData(),autoload_with=src)
                    rows=[dict(row) for row in src.execute(select(current)).mappings()]
                    for row in rows:
                        payload={key:value for key,value in row.items() if key in old.c}
                        if name=='learning_plans': self.assertNotIn('revision',payload['payload'])
                        target.execute(old.insert().values(**payload))
                before=list(target.execute(select(metadata.tables['learning_plan_operations'].c.committed_projection_digest,metadata.tables['learning_plan_operations'].c.committed_projection_payload)).all())
            with patch.dict(os.environ,{'DATABASE_URL':url}): command.upgrade(config,'head')
            migrated=Database(url); self.addCleanup(migrated.dispose)
            operations=LearningPlanOperationRepository(migrated)
            receipt=operations.get_by_client_request_id(client_request_id='plan-request-success',validate_current=True)
            self.assertEqual(receipt.committed_projection_digest,before[0][0])
            plans=LearningPlanRepository(migrated)
            plan=plans.require(receipt.plan_id); self.assertEqual(plan.revision,0)
            revision,_=PlanRevisionRepository(migrated).admit(plan.id,PlanRevisionRequestV1(client_request_id='migration-preview',base_revision=0,instruction='Review old plan'))
            self.assertEqual(operations.require(operation_id=receipt.operation_id,validate_current=True),receipt)
            self.assertEqual(plans.require(plan.id),plan)
            plans.mutate(plan.id,lambda p:p.model_copy(update={'course_title':'Edited after migration'}),expected_revision=0)
            restored=operations.require(operation_id=receipt.operation_id,validate_current=True)
            self.assertEqual(restored,receipt)
            self.assertEqual(plans.require(plan.id).revision,1)


if __name__=='__main__': unittest.main(defaultTest='IndependentMigrationTests')
