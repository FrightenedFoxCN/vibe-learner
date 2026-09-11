import unittest, json
from datetime import datetime, UTC, timedelta
from types import SimpleNamespace
from sqlalchemy import text
from tests.test_harness_broad_commit_binding import HarnessBroadCommitBindingTests
from app.models.harness import HarnessArtifactType, HarnessContractRef
from app.models.harness_operation import HarnessDomainOperationKind
from app.models.document_processing import DOCUMENT_SNAPSHOT_CONTRACT
from app.models.planning_runtime import PLAN_SNAPSHOT_CONTRACT
from app.models.persona_generation import PERSONA_SNAPSHOT_CONTRACT
from app.models.scene_generation import SCENE_SNAPSHOT_CONTRACT
from app.models.harness_artifact_access import HarnessArtifactResolveRequestV1, HarnessArtifactPermission, HarnessArtifactGrantScopeV1
from app.persistence.harness_artifact_repository import HarnessArtifactRepository
from app.persistence.database import Database
from app.services.harness_broad_adoption import HarnessProposalRuntimeService, AuthorizedJsonArtifactResolver, _decode_protected_json

class IndependentReplay(unittest.TestCase):
 def test_domain_matrix(self):
  fixture=HarnessBroadCommitBindingTests(); fixture.setUp()
  self.addCleanup(fixture.tearDown)
  service=fixture.documents.harness_service
  doc=fixture._prepare_document('independent-replay')[0]
  plan=fixture._prepare_plan('independent-replay')[0]
  bindings=[fixture.documents.process_repository.require_harness_operation(doc.operation_id),fixture.plans.operation_repository.require_harness_operation(plan.operation_id)]
  bindings += [service.workflow_operations.admit(kind=k,request_manifest={}) for k in [HarnessDomainOperationKind.PERSONA_GENERATION,HarnessDomainOperationKind.SCENE_GENERATION]]
  specs=list(zip(bindings,[HarnessArtifactType.DOCUMENT_UPLOAD,HarnessArtifactType.PLANNING_CONTEXT,HarnessArtifactType.PERSONA_SNAPSHOT,HarnessArtifactType.SCENE_SNAPSHOT],[DOCUMENT_SNAPSHOT_CONTRACT,PLAN_SNAPSHOT_CONTRACT,PERSONA_SNAPSHOT_CONTRACT,SCENE_SNAPSHOT_CONTRACT]))
  for binding,atype,contract in specs:
   with self.subTest(domain=binding.workflow):
    expected={'source':'独立验收 '+binding.workflow.value,'nested':{'version':1}}
    ref,gid=service._register_snapshot(binding=binding,artifact_type=atype,artifact_contract=contract,protected_input=expected)
    req=HarnessArtifactResolveRequestV1(grant_id=gid,harness_operation_id=binding.harness_operation_id,artifact_id=ref.artifact_id,artifact_type=atype,artifact_contract=contract,permission=HarnessArtifactPermission.READ)
    fresh=Database(str(fixture.store.database.engine.url)); repo=HarnessArtifactRepository(fresh)
    self.addCleanup(fresh.dispose)
    result=repo.resolve(req); self.assertEqual(result.status.value,'resolved'); self.assertEqual(_decode_protected_json(result.content,contract),expected)
    self.assertEqual(repo.resolve(req.model_copy(update={'harness_operation_id':bindings[(bindings.index(binding)+1)%4].harness_operation_id})).status.value,'forbidden')
    self.assertEqual(repo.resolve(req.model_copy(update={'artifact_contract':HarnessContractRef(name=contract.name,version='unsupported-v999')})).status.value,'forbidden')
    with self.assertRaisesRegex(PermissionError,'grant_missing'):
     AuthorizedJsonArtifactResolver(repo,{}).resolve(operation_binding=binding,context=SimpleNamespace(snapshot_refs=(ref,)))
    for version in ('legacy-v0','future-v999'):
     payload=json.dumps({'schema_name':contract.name,'schema_version':version,'input':expected}).encode()
     with self.assertRaisesRegex(ValueError,'contract_mismatch'): _decode_protected_json(payload,contract)
    self.assertEqual(repo.resolve(req,now=datetime.now(UTC)+timedelta(minutes=16)).status.value,'expired')
    with fresh.engine.begin() as conn:
     conn.exec_driver_sql('DROP TRIGGER IF EXISTS trg_harness_artifacts_immutable_update')
     conn.execute(text('UPDATE harness_artifacts SET payload = :p WHERE artifact_id = :id'),{'p':b'corrupt','id':ref.artifact_id})
    self.assertEqual(repo.resolve(req).status.value,'digest_mismatch')
    repo.delete_artifact(artifact_id=ref.artifact_id)
    self.assertEqual(repo.resolve(req).status.value,'not_found')
    print(binding.workflow.value+': restart, exact content, scope, contract, missing grant, old/future envelope, expiry, corruption, deletion PASS')
if __name__=='__main__': unittest.main(defaultTest="IndependentReplay")
