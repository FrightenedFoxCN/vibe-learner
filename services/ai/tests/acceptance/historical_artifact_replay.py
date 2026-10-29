"""Replay real protected artifacts emitted by the archived application."""

from __future__ import annotations

import argparse
import base64
from datetime import datetime, timedelta
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile
from tempfile import TemporaryDirectory
from unittest.mock import patch

from alembic import command
from sqlalchemy import select

from app.models.document_processing import (
    DocumentProcessInputManifest,
    DocumentProcessRuntimeOutputV1,
)
from app.models.harness import (
    HarnessArtifactType,
    HarnessContractRef,
    HarnessStage,
    HarnessWorkflow,
)
from app.models.harness_artifact_access import (
    HarnessArtifactGrantScopeV1,
    HarnessArtifactPermission,
    HarnessArtifactResolutionStatus,
    HarnessArtifactResolveRequestV1,
)
from app.models.harness_operation import HarnessDomainOperationKind
from app.models.persona_generation import (
    PERSONA_ADAPTER_CONTRACT,
    PERSONA_INPUT_CONTRACT,
    PERSONA_POLICY_CONTRACT,
    PERSONA_PROMPT_CONTRACT,
    PERSONA_SNAPSHOT_CONTRACT,
    PERSONA_TRACE_CONTRACT,
    PersonaGenerationInputManifest,
    PersonaGenerationProposalV1,
)
from app.models.planning_runtime import (
    LearningPlanInputManifest,
    LearningPlanRuntimeOutputV2,
)
from app.models.scene_generation import (
    SCENE_ADAPTER_CONTRACT,
    SCENE_INPUT_CONTRACT,
    SCENE_POLICY_CONTRACT,
    SCENE_PROMPT_CONTRACT,
    SCENE_SNAPSHOT_CONTRACT,
    SCENE_TRACE_CONTRACT,
    SceneGenerationInputManifest,
    SceneGenerationProposalV1,
)
from app.persistence.database import Database
from app.persistence.document_repository import DocumentRepository
from app.persistence.document_process_operation_repository import (
    DocumentProcessOperationRepository,
)
from app.persistence.harness_artifact_repository import HarnessArtifactRepository
from app.persistence.learning_plan_operation_repository import (
    LearningPlanOperationRepository,
)
from app.persistence.models import (
    HarnessArtifactGrantRow,
    HarnessArtifactGrantScopeRow,
    HarnessArtifactRow,
)
from app.services.harness_broad_adoption import (
    HarnessProposalRuntimeService,
    _decode_protected_json,
)
from app.services.model_provider import MockModelProvider
from tests.support.migrations import alembic_config

REPO = Path(__file__).resolve().parents[4]
SERVICE = REPO / "services/ai"
OLD_REVISION = "e3a03a9"


def _old_source(root: Path) -> Path:
    tree = root / "old-source"
    archive = subprocess.check_output(
        [
            "git",
            "archive",
            OLD_REVISION,
            "services/ai/app",
            "services/ai/alembic",
            "services/ai/alembic.ini",
            "packages/shared/fixtures",
        ],
        cwd=REPO,
    )
    with tarfile.open(fileobj=io.BytesIO(archive)) as package:
        package.extractall(tree, filter="data")
    return tree


def _seed_old_application(source_tree: Path, root: Path) -> Path:
    source_url = f"sqlite:///{root / 'unused-target.db'}"
    result = subprocess.run(
        [
            sys.executable,
            str(SERVICE / "tests/acceptance/postgres_legacy_seed.py"),
            "--source-tree",
            str(source_tree),
            "--root",
            str(root),
            "--export-only",
        ],
        cwd=source_tree / "services/ai",
        env={**os.environ, "DATABASE_URL": source_url},
        capture_output=True,
        text=True,
        timeout=90,
    )
    (root / "old-seed.log").write_text(result.stdout + result.stderr)
    if result.returncode:
        raise RuntimeError(f"old seed failed; inspect {root / 'old-seed.log'}")
    return root / "historical-source.db"


def _upgrade_current(source_db: Path) -> str:
    source_url = f"sqlite:///{source_db}"
    config = alembic_config(source_url)
    with patch.dict(os.environ, {"DATABASE_URL": source_url}):
        command.upgrade(config, "head")
    return source_url


def _artifact_request(database: Database, artifact_id: str):
    with database.session() as session:
        artifact = session.get(HarnessArtifactRow, artifact_id)
        if artifact is None:
            raise AssertionError(f"historical artifact missing: {artifact_id}")
        scope = session.scalar(
            select(HarnessArtifactGrantScopeRow)
            .where(HarnessArtifactGrantScopeRow.artifact_id == artifact_id)
            .order_by(HarnessArtifactGrantScopeRow.grant_id)
        )
        if scope is None:
            raise AssertionError(f"historical artifact grant missing: {artifact_id}")
        grant = session.get(HarnessArtifactGrantRow, scope.grant_id)
        if grant is None:
            raise AssertionError(f"historical grant row missing: {scope.grant_id}")
        contract = HarnessContractRef(
            name=artifact.contract_name,
            version=artifact.contract_version,
        )
        request = HarnessArtifactResolveRequestV1(
            grant_id=grant.grant_id,
            harness_operation_id=grant.harness_operation_id,
            artifact_id=artifact.artifact_id,
            artifact_type=HarnessArtifactType(artifact.artifact_type),
            artifact_contract=contract,
            permission=HarnessArtifactPermission.READ,
        )
        return artifact, scope, grant, request, contract


def _reauthorize(
    repository: HarnessArtifactRepository,
    database: Database,
    artifact_id: str,
    expected_digest: str,
    expected_payload: bytes,
):
    artifact, old_scope, old_grant, old_request, contract = _artifact_request(
        database, artifact_id
    )
    expires = datetime.fromisoformat(old_grant.expires_at.removesuffix("Z") + "+00:00")
    expired = repository.resolve(old_request, now=expires + timedelta(seconds=1))
    assert expired.status == HarnessArtifactResolutionStatus.EXPIRED, expired
    now = expires + timedelta(seconds=2)
    scope = HarnessArtifactGrantScopeV1(
        artifact_type=HarnessArtifactType(old_scope.artifact_type),
        artifact_id=old_scope.artifact_id,
        artifact_contract=contract,
        permission=HarnessArtifactPermission.READ,
    )
    renewed = repository.issue_grant(
        harness_operation_id=old_grant.harness_operation_id,
        scopes=(scope,),
        expires_at=now + timedelta(hours=1),
        now=now,
    )
    request = old_request.model_copy(update={"grant_id": renewed.grant_id})
    resolved = repository.resolve(request, now=now + timedelta(seconds=1))
    assert resolved.status == HarnessArtifactResolutionStatus.RESOLVED, resolved
    assert resolved.payload_digest == expected_digest == artifact.payload_digest
    assert resolved.content == expected_payload
    return resolved.content, contract, old_grant.harness_operation_id


def _replay_domains(database: Database, artifacts: dict[str, dict[str, object]]):
    document = DocumentRepository(database)
    doc_input = _decode_protected_json(
        artifacts["document"]["payload"],
        HarnessContractRef(**artifacts["document"]["contract"]),
    )
    document_id = doc_input["document"]["id"]
    saved_document, debug = document.get_with_debug(document_id)
    assert saved_document is not None and debug is not None
    document_output = DocumentProcessRuntimeOutputV1(
        debug_report=debug,
        study_units=saved_document.study_units,
    )
    plan_operations = LearningPlanOperationRepository(database)
    plan_operation = plan_operations.get_by_client_request_id(
        client_request_id="historical-plan-request", validate_current=True
    )
    assert (
        plan_operation is not None and plan_operation.committed_projection is not None
    )
    plan_projection = plan_operation.committed_projection
    plan_output = LearningPlanRuntimeOutputV2(
        plan=plan_projection.plan,
        document=plan_projection.document,
        debug_report=plan_projection.debug_report,
        trace=plan_projection.trace,
    )
    runtime = HarnessProposalRuntimeService.from_database(database)
    mock = MockModelProvider()
    results = {}

    doc_manifest = DocumentProcessInputManifest(
        document_id=document_id,
        force_ocr=bool(doc_input.get("force_ocr", False)),
    )
    document_operation, _ = DocumentProcessOperationRepository(database).admit(
        document_id=document_id,
        force_ocr=doc_manifest.force_ocr,
    )
    document_binding = DocumentProcessOperationRepository(
        database
    ).require_harness_operation(document_operation.operation_id)
    prepared_document, _ = runtime.prepare_document(
        operation_binding=document_binding,
        manifest=doc_manifest,
        protected_input=doc_input,
        generate=lambda _protected: document_output,
    )
    results["document"] = {
        "trace_id": prepared_document.execution.trace_id,
        "status": prepared_document.status.value,
    }

    plan_input = _decode_protected_json(
        artifacts["planning"]["payload"],
        HarnessContractRef(**artifacts["planning"]["contract"]),
    )
    plan_manifest = LearningPlanInputManifest(
        client_request_id="historical-replay-plan",
        document_id=plan_projection.document_id,
        persona_id=plan_projection.plan.persona_id,
        creation_mode="document",
    )
    replay_request = plan_operation.request_payload.model_copy(
        update={
            "client_request_id": "historical-replay-plan",
            "expected_document_updated_at": document.get(document_id).updated_at,
        }
    )
    replay_operation, _ = plan_operations.admit(request=replay_request)
    plan_binding = plan_operations.require_harness_operation(
        replay_operation.operation_id
    )
    prepared_plan, _ = runtime.prepare_plan(
        operation_binding=plan_binding,
        manifest=plan_manifest,
        protected_input=plan_input,
        generate=lambda _protected: plan_output,
    )
    results["planning"] = {
        "trace_id": prepared_plan.execution.trace_id,
        "status": prepared_plan.status.value,
    }

    persona_input = _decode_protected_json(
        artifacts["persona"]["payload"],
        HarnessContractRef(**artifacts["persona"]["contract"]),
    )

    def persona_generate(protected):
        raw = mock.generate_persona_cards_from_keywords(
            keywords=str(protected["input_text"]), count=protected.get("count")
        )
        return PersonaGenerationProposalV1.model_validate(
            {
                "request_kind": "card_batch",
                "used_model": raw.get("used_model", ""),
                "used_web_search": raw.get("used_web_search", False),
                "summary": raw.get("summary", ""),
                "relationship": raw.get("relationship", ""),
                "learner_address": raw.get("learner_address", ""),
                "cards": raw["cards"],
            },
            strict=True,
        )

    _, persona_trace = runtime.run_proposal(
        kind=HarnessDomainOperationKind.PERSONA_GENERATION,
        workflow=HarnessWorkflow.PERSONA,
        stage=HarnessStage.PERSONA_GENERATION,
        manifest=PersonaGenerationInputManifest(
            request_kind="card_batch",
            mode=str(persona_input["mode"]),
            requested_count=int(persona_input["count"]),
            input_char_count=len(str(persona_input["input_text"])),
        ),
        input_contract=PERSONA_INPUT_CONTRACT,
        artifact_type=HarnessArtifactType.PERSONA_SNAPSHOT,
        artifact_contract=PERSONA_SNAPSHOT_CONTRACT,
        prompt_contract=PERSONA_PROMPT_CONTRACT,
        policy_contract=PERSONA_POLICY_CONTRACT,
        adapter_contract=PERSONA_ADAPTER_CONTRACT,
        trace_contract=PERSONA_TRACE_CONTRACT,
        protected_input=persona_input,
        generate=persona_generate,
        output_type=PersonaGenerationProposalV1,
    )
    results["persona"] = persona_trace

    scene_input = _decode_protected_json(
        artifacts["scene"]["payload"],
        HarnessContractRef(**artifacts["scene"]["contract"]),
    )

    def scene_generate(protected):
        raw = mock.generate_scene_tree_from_keywords(
            keywords=str(protected["input_text"]),
            layer_count=protected.get("layer_count"),
        )
        return SceneGenerationProposalV1.model_validate(
            {
                "used_model": raw.get("used_model", ""),
                "used_web_search": raw.get("used_web_search", False),
                "proposal": raw["proposal"],
            },
            strict=True,
        )

    _, scene_trace = runtime.run_proposal(
        kind=HarnessDomainOperationKind.SCENE_GENERATION,
        workflow=HarnessWorkflow.SCENE,
        stage=HarnessStage.SCENE_GENERATION,
        manifest=SceneGenerationInputManifest(
            mode=str(scene_input["mode"]),
            requested_layer_count=int(scene_input["layer_count"]),
            input_char_count=len(str(scene_input["input_text"])),
        ),
        input_contract=SCENE_INPUT_CONTRACT,
        artifact_type=HarnessArtifactType.SCENE_SNAPSHOT,
        artifact_contract=SCENE_SNAPSHOT_CONTRACT,
        prompt_contract=SCENE_PROMPT_CONTRACT,
        policy_contract=SCENE_POLICY_CONTRACT,
        adapter_contract=SCENE_ADAPTER_CONTRACT,
        trace_contract=SCENE_TRACE_CONTRACT,
        protected_input=scene_input,
        generate=scene_generate,
        output_type=SceneGenerationProposalV1,
    )
    results["scene"] = scene_trace
    return results


def run(output: Path | None = None) -> dict[str, object]:
    with TemporaryDirectory(prefix="vibe-historical-replay-") as folder:
        root = Path(folder)
        source_tree = _old_source(root)
        source_db = _seed_old_application(source_tree, root)
        url = _upgrade_current(source_db)
        database = Database(url)
        repository = HarnessArtifactRepository(database)
        identities = json.loads((root / "historical-identities.json").read_text())
        manifest = identities["historical_artifacts"]
        selected: dict[str, dict[str, object]] = {}
        selectors = {
            "document": "DocumentProcessProtectedInput",
            "planning": "LearningPlanProtectedInput",
            "persona": "PersonaGenerationProtectedInput",
            "scene": "SceneGenerationProtectedInput",
        }
        report: dict[str, object] = {
            "contract": "historical-artifact-replay-v1",
            "source_revision": OLD_REVISION,
            "seed_provenance": "unmodified archived application generated SQLite artifacts",
            "domains": {},
        }
        for domain, contract_name in selectors.items():
            item = next(
                artifact
                for artifact in manifest
                if artifact["contract_name"] == contract_name
            )
            payload = base64.b64decode(item["payload_base64"])
            content, contract, operation_id = _reauthorize(
                repository,
                database,
                item["artifact_id"],
                item["payload_digest"],
                payload,
            )
            selected[domain] = {
                "payload": content,
                "contract": {"name": contract.name, "version": contract.version},
                "artifact_id": item["artifact_id"],
            }
            report["domains"][domain] = {
                "artifact_id": item["artifact_id"],
                "artifact_type": item["artifact_type"],
                "contract": {"name": contract.name, "version": contract.version},
                "payload_digest": item["payload_digest"],
                "expired_grant_rejected": True,
                "renewed_grant_resolved": True,
                "source_operation_id": operation_id,
            }
        traces = _replay_domains(database, selected)
        for domain, trace in traces.items():
            if isinstance(trace, dict):
                report["domains"][domain].update(
                    replay_trace_id=trace["trace_id"],
                    replay_status=trace["status"],
                )
            else:
                report["domains"][domain].update(
                    replay_trace_id=trace.trace_id,
                    replay_status=trace.status.value,
                )
        database.dispose()
        if output is not None:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    report = run(args.output)
    assert all(
        item["replay_status"] in {"passed", "repaired"}
        for item in report["domains"].values()
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
