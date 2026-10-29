"""Reviewed persisted context profiles do not authorize new runtime execution."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from pydantic import ValidationError
from sqlalchemy import select

from app.core.harness_context_history import HISTORICAL_HARNESS_CONTEXT_PROFILES
from app.models.harness import (
    HarnessContextEnvelopeV3,
    HarnessContractRef,
    HarnessStage,
    canonical_harness_context_digest,
    validate_harness_trace,
)
from app.models.planning import LearningPlanOperationRequestV1
from app.models.planning_runtime import LearningPlanInputManifest
from app.models.harness_manifest import require_executable_workflow_manifest_entry
from app.persistence.harness_runtime_repository import (
    HarnessRuntimeRepository,
    HarnessRuntimeError,
)
from app.persistence.learning_plan_operation_repository import (
    LearningPlanOperationRepository,
)
from app.persistence.models import HarnessRuntimeExecutionRow
from app.services.harness_context import build_harness_context
from app.models.harness_runtime import expected_harness_runtime_trace_id
from app.services.local_store import LocalJsonStore

ROOT = Path(__file__).parents[3] / "packages/shared/fixtures/harness"


def contract(value):
    if value is None:
        return None
    name, version = value.split("@")
    return {"name": name, "version": version}


def historical_context(
    profile, operation_id="harness-operation-0123456789abcdef0123456789abcdef"
):
    raw = dict(
        context_contract={
            "name": "HarnessContextEnvelopeV3",
            "version": "harness-context-v3",
        },
        workflow=profile["workflow"],
        stage=profile["stage"],
        operation_id=operation_id,
        input_contract=contract(profile["input_contract"]),
        prompt_contract=contract(profile["prompt_contract"]),
        policy_contract=contract(profile["policy_contract"]),
        component_versions=[contract(value) for value in profile["component_versions"]],
        subject_refs=[],
        snapshot_refs=[],
        digest_algorithm="sha256",
        digest_contract={
            "name": "HarnessContextManifestDigest",
            "version": "harness-context-manifest-digest-v1",
        },
        input_digest="1" * 64,
        context_digest="0" * 64,
    )
    raw["context_digest"] = canonical_harness_context_digest(raw)
    return HarnessContextEnvelopeV3.model_validate(raw)


class HistoricalContextTests(unittest.TestCase):
    def test_golden_profiles_and_archived_application_traces_decode_without_rewrite(
        self,
    ):
        expected = json.loads((ROOT / "context-history-v1.json").read_text())[
            "profiles"
        ]
        actual = [
            {**profile, "component_versions": list(profile["component_versions"])}
            for profile in HISTORICAL_HARNESS_CONTEXT_PROFILES
        ]
        self.assertEqual(actual, expected)
        for profile in HISTORICAL_HARNESS_CONTEXT_PROFILES:
            self.assertTrue(historical_context(profile).matches_historical_profile())
        for raw in json.loads((ROOT / "context-history-traces-v1.json").read_text())[
            "traces"
        ]:
            with self.subTest(stage=raw["stage"]):
                decoded = validate_harness_trace(raw)
                self.assertEqual(
                    decoded.model_dump(mode="json", exclude_none=False), raw
                )

    def test_unknown_versions_and_mixed_historical_profiles_still_fail_closed(self):
        profile = next(
            profile
            for profile in HISTORICAL_HARNESS_CONTEXT_PROFILES
            if profile["workflow"] == "study_chat"
        )
        baseline = historical_context(profile).model_dump(mode="json")
        for field in ["component_versions", "prompt_contract", "input_contract"]:
            raw = json.loads(json.dumps(baseline))
            if field == "component_versions":
                raw[field][0]["version"] = "study-chat-prompt-v999"
            else:
                raw[field]["version"] += "-mixed"
            raw["context_digest"] = canonical_harness_context_digest(raw)
            with self.subTest(field=field), self.assertRaises(ValidationError):
                HarnessContextEnvelopeV3.model_validate(raw)

    def test_history_cannot_create_an_execution_or_claim_a_restored_nonterminal_execution(
        self,
    ):
        with TemporaryDirectory() as folder:
            store = LocalJsonStore(Path(folder))
            self.addCleanup(store.close)
            operations = LearningPlanOperationRepository(store.database)
            operation, _ = operations.admit(
                request=LearningPlanOperationRequestV1(
                    client_request_id="history-runtime-rejection",
                    persona_id="mentor",
                    objective="Synthetic version check",
                )
            )
            binding = operations.require_harness_operation(operation.operation_id)
            entry = require_executable_workflow_manifest_entry(
                binding.workflow, HarnessStage.PLAN_GENERATION
            )
            profile = next(
                profile
                for profile in HISTORICAL_HARNESS_CONTEXT_PROFILES
                if profile["stage"] == "plan_generation"
            )
            archived = historical_context(profile, binding.harness_operation_id)
            repository = HarnessRuntimeRepository(store.database)
            args = dict(
                operation_binding=binding,
                stage=HarnessStage.PLAN_GENERATION,
                trace_slot=0,
                adapter_contract=entry.owner_adapter.contract.to_harness_ref(),
                trace_contract=HarnessContractRef(
                    name="LearningPlanRuntimeOutput",
                    version="learning-plan-runtime-output-v2",
                ),
            )
            with self.assertRaisesRegex(HarnessRuntimeError, "context_manifest_drift"):
                repository.prepare(**args, context=archived)
            self.assertEqual(
                repository.list_operation_traces(binding.harness_operation_id), ()
            )
            current = build_harness_context(
                workflow=binding.workflow,
                stage=HarnessStage.PLAN_GENERATION,
                operation_binding=binding,
                input_contract=entry.input_contract.contract.to_harness_ref(),
                input_manifest=LearningPlanInputManifest(
                    client_request_id="history-runtime-rejection",
                    document_id="",
                    persona_id="mentor",
                    creation_mode="goal_only",
                ),
                subject_refs=[],
                prompt_contract=entry.prompt_contract.contract.to_harness_ref(),
                policy_contract=entry.policy_contract.contract.to_harness_ref(),
            )
            prepared = repository.prepare(**args, context=current)
            with store.database.engine.connect() as connection:
                source = dict(
                    connection.execute(
                        select(HarnessRuntimeExecutionRow.__table__).where(
                            HarnessRuntimeExecutionRow.trace_id == prepared.trace_id
                        )
                    )
                    .mappings()
                    .one()
                )
            source.update(
                trace_id=expected_harness_runtime_trace_id(
                    harness_operation_id=binding.harness_operation_id,
                    stage=HarnessStage.PLAN_GENERATION,
                    trace_slot=1,
                ),
                trace_slot=1,
                context_payload=archived.model_dump(mode="json"),
                context_digest=archived.context_digest,
            )
            with store.database.session() as session:
                session.add(HarnessRuntimeExecutionRow(**source))
            with self.assertRaisesRegex(HarnessRuntimeError, "context_manifest_drift"):
                repository.claim(trace_id=source["trace_id"], claim_owner="new-worker")
            self.assertEqual(repository.get(source["trace_id"]).claim_count, 0)
