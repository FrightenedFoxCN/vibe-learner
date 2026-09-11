"""Independent adversarial checks, separate from the implementation tests."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, local
from tempfile import TemporaryDirectory
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
from copy import deepcopy
from datetime import datetime, timezone, timedelta
import unittest
import os
from tests.support.database import isolated_database
from fastapi import HTTPException
from sqlalchemy import select, update, event
from app.persistence.database import Database
from app.persistence.learning_plan_repository import LearningPlanRepository
from app.persistence.plan_revision_repository import PlanRevisionRepository
from app.persistence.study_session_repository import StudySessionRepository
from app.persistence.models import HarnessRuntimeExecutionRow, PlanRevisionOperationRow, LearningPlanRow, LearningPlanRevisionRow
from app.models.domain import StudySessionRecord, SessionPlanConfirmationRecord
from app.models.plan_revision import PlanRevisionRequestV1, proposal_from_plan
from app.services.plan_revision import PlanRevisionService
from app.services.plans import LearningPlanService
from app.services.study_arrangement import StudyArrangementService
from app.services.harness_broad_adoption import HarnessProposalRuntimeService
from app.services.model_provider import MockModelProvider
from tests.test_plan_revision import fixture_plan

class IndependentPlanRevisionTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        if os.environ.get('VIBE_TEST_POSTGRES_URL'):
            self.db=isolated_database(self)
        else:
            self.db=Database(f'sqlite:///{self.tmp.name}/audit.db'); self.db.create_schema(); self.addCleanup(self.db.dispose)
        self.plans=LearningPlanRepository(self.db); self.plans.import_legacy([fixture_plan()])
        self.ops=PlanRevisionRepository(self.db)
        self.provider=MockModelProvider()
        self.service=PlanRevisionService(self.ops,HarnessProposalRuntimeService.from_database(self.db),self.provider)

    def request(self,key='independent',base=0):
        return PlanRevisionRequestV1(client_request_id=key,base_revision=base,instruction='Use concrete examples')

    def test_forced_concurrent_explicit_cas_has_one_winner(self):
        gate=Barrier(2); state=local()
        def writer(title):
            def mutate(plan):
                if not getattr(state,'entered',False): state.entered=True; gate.wait(timeout=10)
                plan.course_title=title; return plan
            try: return self.plans.mutate('plan-cas',mutate,expected_revision=0).revision
            except HTTPException as e: return e.status_code
        with ThreadPoolExecutor(2) as pool: outcomes=list(pool.map(writer,['A','B']))
        self.assertEqual(sorted(outcomes),[1,409]); self.assertEqual(self.plans.require('plan-cas').revision,1)

    def test_concurrent_duplicate_confirmation_is_one_atomic_decision(self):
        sessions=StudySessionRepository(self.db)
        sessions.create(StudySessionRecord(id='session-confirm',document_id='',persona_id='mentor',plan_id='plan-cas',study_unit_id='unit-1',status='active',turns=[],created_at='2026-09-11T00:00:00Z',updated_at='2026-09-11T00:00:00Z',plan_confirmations=[SessionPlanConfirmationRecord(id='confirm',tool_name='update_plan',action_type='update_plan',plan_id='plan-cas',title='Rename',created_at='2026-09-11T00:00:00Z')]))
        gate=Barrier(2); state=local()
        def run(_):
            def apply(plan,confirmation):
                if not getattr(state,'entered',False): state.entered=True; gate.wait(timeout=10)
                plan.course_title='Confirmed'; return plan
            return self.plans.resolve_confirmation('session-confirm','confirm','approve','','2026-09-11T00:01:00Z',apply)
        with ThreadPoolExecutor(2) as pool: list(pool.map(run,range(2)))
        self.assertEqual(self.plans.require('plan-cas').revision,1)
        current=sessions.require('session-confirm'); self.assertEqual(current.revision,1); self.assertEqual(current.plan_confirmations[0].status,'approved')

    def test_accept_conflict_and_lost_response_query_no_second_provider(self):
        with patch.object(self.provider,'generate_plan_revision',wraps=self.provider.generate_plan_revision) as generate:
            ready=self.service.create('plan-cas',self.request())
            self.assertEqual(ready.status,'ready')
            self.plans.mutate('plan-cas',lambda p:p.model_copy(update={'course_title':'Concurrent'}))
            result=self.service.decide('plan-cas','independent','accept')
            self.assertEqual(result.status,'conflict')
            fresh=Database(self.db.url)
            fresh.engine=fresh.engine.execution_options(**dict(self.db.engine.get_execution_options()))
            fresh._session_factory.configure(bind=fresh.engine)
            reopened=PlanRevisionRepository(fresh); self.addCleanup(reopened.database.dispose)
            self.assertEqual(reopened.get('plan-cas','independent'),result)
            self.assertEqual(self.service.create('plan-cas',self.request()),result)
            self.assertEqual(generate.call_count,1)
            self.assertEqual(self.plans.require('plan-cas').course_title,'Concurrent')

    def test_accept_receipt_and_terminal_trace_commit_together(self):
        ready=self.service.create('plan-cas',self.request())
        original=self.service._prepare
        def prepare(*args,**kwargs):
            prepared,runtime=original(*args,**kwargs)
            def explode(*a,**k): raise RuntimeError('injected before terminal trace write')
            runtime.finalize_prepared_in_session=explode
            return prepared,runtime
        with patch.object(self.service,'_prepare',side_effect=prepare): result=self.service.decide('plan-cas','independent','accept')
        self.assertEqual(result.status,'failed')
        self.assertEqual(self.plans.require('plan-cas').revision,0)
        with self.db.session() as session:
            row=session.get(PlanRevisionOperationRow,ready.operation_id)
            self.assertIsNone(row.decision_receipt)
            traces=list(session.scalars(select(HarnessRuntimeExecutionRow).where(HarnessRuntimeExecutionRow.harness_operation_id==row.harness_operation_id)))
            self.assertEqual(len(traces),2)
            for trace in traces:
                self.assertEqual(trace.state,'terminal')
            self.assertEqual(traces[1].terminal_trace['commit_evidence']['status'],'not_committed')

    def test_cross_operation_prepared_output_is_zero_write(self):
        first,binding1=self.ops.admit('plan-cas',self.request('first'))
        second,binding2=self.ops.admit('plan-cas',self.request('second'))
        prepared,runtime=self.service._prepare(second,binding2,'preview',{'plan':second.base_plan.model_dump(mode='json')},lambda _:proposal_from_plan(second.base_plan,'Independent'))
        with self.assertRaisesRegex(ValueError,'binding_mismatch'):
            self.ops.commit(first,proposal=prepared.output,action='preview',prepared=prepared,runtime=runtime)
        self.assertEqual(self.ops.get('plan-cas','first').status,'generating')
        self.assertEqual(self.ops.get('plan-cas','second').status,'generating')
        self.assertEqual(self.plans.require('plan-cas').revision,0)

    def test_accept_and_rollback_preserve_schedule_identity_and_current_progress(self):
        ready=self.service.create('plan-cas',self.request())
        accepted=self.service.decide('plan-cas','independent','accept')
        self.assertEqual(accepted.status,'accepted')
        self.assertEqual(self.ops.get('plan-cas','independent'),accepted)
        self.assertEqual(self.service.decide('plan-cas','independent','accept'),accepted)
        def progress(plan):
            plan.schedule[0].status='completed'
            return plan
        self.plans.mutate('plan-cas',progress)
        rollback=PlanRevisionRequestV1(client_request_id='rollback',base_revision=2,rollback_revision=0)
        self.assertEqual(self.service.create('plan-cas',rollback).status,'ready')
        restored=self.service.decide('plan-cas','rollback','accept')
        self.assertEqual(restored.result.revision,3)
        self.assertEqual(restored.result.schedule[0].status,'completed')
        self.assertEqual([s.id for s in restored.result.schedule],['schedule-a','schedule-b'])
        self.assertEqual(self.ops.history('plan-cas'),[3,2,1,0])
        with self.db.session() as session:
            row=session.get(PlanRevisionOperationRow,accepted.operation_id)
            traces=list(session.scalars(select(HarnessRuntimeExecutionRow).where(HarnessRuntimeExecutionRow.harness_operation_id==row.harness_operation_id)))
            self.assertEqual(len(traces),2)
            for trace in traces:
                self.assertEqual(trace.state,'terminal')
                self.assertEqual(trace.terminal_trace['commit_evidence']['status'],'committed')

    def test_confirmation_session_write_failure_rolls_back_plan_and_history(self):
        sessions=StudySessionRepository(self.db)
        sessions.create(StudySessionRecord(id='session-fault',document_id='',persona_id='mentor',plan_id='plan-cas',study_unit_id='unit-1',status='active',turns=[],created_at='2026-09-11T00:00:00Z',updated_at='2026-09-11T00:00:00Z',plan_confirmations=[SessionPlanConfirmationRecord(id='confirm',tool_name='update_plan',action_type='update_plan',plan_id='plan-cas',title='Rename',created_at='2026-09-11T00:00:00Z')]))
        def fail_session_write(conn,cursor,statement,parameters,context,many):
            if statement.lstrip().upper().startswith('UPDATE') and 'study_sessions SET' in statement:
                raise RuntimeError('injected session confirmation write failure')
        event.listen(self.db.engine,'before_cursor_execute',fail_session_write)
        try:
            with self.assertRaisesRegex(RuntimeError,'injected session'):
                self.plans.resolve_confirmation('session-fault','confirm','approve','','2026-09-11T00:01:00Z',lambda p,c:p.model_copy(update={'course_title':'Must rollback'}))
        finally: event.remove(self.db.engine,'before_cursor_execute',fail_session_write)
        self.assertEqual(self.plans.require('plan-cas').revision,0)
        self.assertEqual(self.ops.history('plan-cas'),[0])
        restored=sessions.require('session-fault')
        self.assertEqual(restored.revision,0)
        self.assertEqual(restored.plan_confirmations[0].status,'pending')

    def test_persisted_plan_readback_rejects_injected_delete_before_finalizer(self):
        if not self.db.url.startswith('sqlite'):
            self.skipTest('SQLite trigger fault injection')
        ready=self.service.create('plan-cas',self.request())
        with self.db.engine.begin() as connection:
            connection.exec_driver_sql("CREATE TRIGGER independent_plan_readback_fault AFTER UPDATE ON learning_plans WHEN NEW.revision = 1 BEGIN UPDATE learning_plans SET deleted = 1 WHERE id = NEW.id; END")
        result=self.service.decide('plan-cas','independent','accept')
        self.assertEqual(result.status,'failed')
        self.assertEqual(self.plans.require('plan-cas').revision,0)
        with self.db.session() as session:
            self.assertIsNone(session.get(PlanRevisionOperationRow,ready.operation_id).decision_receipt)

    def test_legacy_preview_normalizes_progress_without_rewriting_plan_or_history(self):
        with self.db.session() as session:
            original=deepcopy(session.get(LearningPlanRow,'plan-cas').payload)
            history=deepcopy(session.get(LearningPlanRevisionRow,('plan-cas',0)).payload)
        self.assertEqual(original['progress_summary']['total_schedule_count'],0)
        ready=self.service.create('plan-cas',self.request())
        self.assertEqual(ready.status,'ready')
        self.assertEqual(ready.base_plan.progress_summary.total_schedule_count,2)
        self.assertEqual(ready.base_plan.study_unit_progress[0].schedule_ids,['schedule-a','schedule-b'])
        with self.db.session() as session:
            self.assertEqual(session.get(LearningPlanRow,'plan-cas').payload,original)
            self.assertEqual(session.get(LearningPlanRevisionRow,('plan-cas',0)).payload,history)
            self.assertEqual(session.get(LearningPlanRow,'plan-cas').revision,0)

    def test_reordered_accept_and_rollback_equal_normal_get_progress_projection(self):
        reader=LearningPlanService(SimpleNamespace(database=self.db),StudyArrangementService(),self.provider)
        def generate(*,plan,instruction):
            proposal=proposal_from_plan(plan,'Move practice first')
            proposal.schedule.reverse()
            proposal.schedule[0].focus='Independent new focus'
            return proposal
        with patch.object(self.provider,'generate_plan_revision',side_effect=generate):
            ready=self.service.create('plan-cas',self.request())
        self.assertEqual(ready.base_plan,reader.require_plan('plan-cas'))
        accepted=self.service.decide('plan-cas','independent','accept')
        self.assertEqual(accepted.status,'accepted')
        self.assertEqual(accepted.result,reader.require_plan('plan-cas'))
        unit=accepted.result.study_unit_progress[0]
        self.assertEqual(unit.schedule_ids,['schedule-b','schedule-a'])
        self.assertEqual(unit.objective_fragment,'Independent new focus')
        def progress(plan):
            plan.schedule[0].status='completed'
            return plan
        self.plans.mutate('plan-cas',progress)
        request=PlanRevisionRequestV1(client_request_id='rollback-progress',base_revision=2,rollback_revision=0)
        preview=self.service.create('plan-cas',request)
        self.assertEqual(preview.base_plan,reader.require_plan('plan-cas'))
        restored=self.service.decide('plan-cas','rollback-progress','accept')
        self.assertEqual(restored.status,'accepted')
        self.assertEqual(restored.result,reader.require_plan('plan-cas'))
        unit=restored.result.study_unit_progress[0]
        self.assertEqual(unit.schedule_ids,['schedule-a','schedule-b'])
        self.assertEqual(unit.objective_fragment,'Read loops')
        self.assertEqual(unit.completed_schedule_count,1)
        self.assertEqual(restored.result.progress_summary.completion_percent,50)

    def test_readback_rejects_receipt_from_another_operation(self):
        first=self.service.create('plan-cas',self.request('first'))
        second=self.service.create('plan-cas',self.request('second'))
        with self.db.session() as session:
            other=session.get(PlanRevisionOperationRow,second.operation_id)
            session.execute(update(PlanRevisionOperationRow).where(PlanRevisionOperationRow.operation_id==first.operation_id).values(preview_receipt=other.preview_receipt))
        with self.assertRaises(ValueError): self.ops.get('plan-cas','first')

    def test_expired_query_recovery_terminalizes_runtime(self):
        record,binding=self.ops.admit('plan-cas',self.request())
        prepared,runtime=self.service._prepare(record,binding,'preview',{'plan':record.base_plan.model_dump(mode='json')},lambda _:proposal_from_plan(record.base_plan,'Independent'))
        with self.db.session() as session:
            session.execute(update(PlanRevisionOperationRow).where(PlanRevisionOperationRow.operation_id==record.operation_id).values(created_at=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()))
        result=self.ops.get('plan-cas','independent')
        self.assertEqual(result.status,'uncertain')
        with self.assertRaises(HTTPException):
            self.ops.commit(record,proposal=prepared.output,action='preview',prepared=prepared,runtime=runtime)
        with self.db.session() as session:
            trace=session.get(HarnessRuntimeExecutionRow,prepared.claim.trace_id)
            self.assertEqual(trace.state,'terminal','terminal domain recovery must settle its durable trace')

    def test_recovery_trace_failure_rolls_back_domain_fence(self):
        record,binding=self.ops.admit('plan-cas',self.request())
        prepared,runtime=self.service._prepare(record,binding,'preview',{'plan':record.base_plan.model_dump(mode='json')},lambda _:proposal_from_plan(record.base_plan,'Independent'))
        with self.db.session() as session:
            session.execute(update(PlanRevisionOperationRow).where(PlanRevisionOperationRow.operation_id==record.operation_id).values(created_at=(datetime.now(timezone.utc)-timedelta(minutes=5)).isoformat()))
        with patch('app.models.harness_runtime.harness_runtime_terminal_trace_digest',side_effect=RuntimeError('injected recovery write failure')):
            with self.assertRaises(RuntimeError): self.ops.get('plan-cas','independent')
        with self.db.session() as session:
            self.assertEqual(session.get(PlanRevisionOperationRow,record.operation_id).status,'generating')
            self.assertEqual(session.get(HarnessRuntimeExecutionRow,prepared.claim.trace_id).state,'claimed')

if __name__=='__main__': unittest.main()
