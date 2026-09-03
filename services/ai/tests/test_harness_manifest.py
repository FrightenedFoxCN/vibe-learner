from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from app.models.harness import (
    HARNESS_OPERATION_STAGE_REGISTRATIONS,
    HarnessArtifactType,
    HarnessContractRef,
    HarnessStage,
    HarnessWorkflow,
)
from app.models.harness_eval import HARNESS_EVAL_CASE_SCHEMA_VERSION
from app.models.harness_manifest import (
    HARNESS_WORKFLOW_MANIFEST,
    HARNESS_WORKFLOW_MANIFEST_ENTRIES,
    HARNESS_WORKFLOW_MANIFEST_EVAL_CASE_VERSION,
    PLANNING_TOOL_EVAL_SUITE,
    TAVERN_IDENTITY_EVAL_SUITE,
    HarnessManifestRegisteredContractListSlotV1,
    HarnessManifestRegisteredContractSlotV1,
    HarnessManifestSlotStatus,
    HarnessWorkflowManifestV1,
    harness_workflow_manifest_snapshot,
    require_executable_workflow_manifest_entry,
    validate_harness_context_manifest_inputs,
)
from app.models.tool_manifest import TOOL_MANIFEST_SCHEMA_VERSION


FIXTURE = (
    Path(__file__).parents[3]
    / "packages"
    / "shared"
    / "fixtures"
    / "harness"
    / "workflow-manifest-v1.json"
)


class HarnessWorkflowManifestTests(unittest.TestCase):
    def test_python_registry_matches_strict_shared_golden(self) -> None:
        fixture_text = FIXTURE.read_text(encoding="utf-8")
        parsed = HarnessWorkflowManifestV1.model_validate_json(fixture_text)
        expected = json.loads(fixture_text)

        self.assertEqual(parsed.model_dump(mode="json"), expected)
        self.assertEqual(harness_workflow_manifest_snapshot(), expected)
        self.assertEqual(parsed, HARNESS_WORKFLOW_MANIFEST)
        self.assertEqual(len(parsed.stages), len(HarnessStage))
        self.assertEqual(
            {entry.key for entry in parsed.stages},
            {
                f"{workflow.value}:{stage.value}"
                for workflow, stage in HARNESS_OPERATION_STAGE_REGISTRATIONS
            },
        )

    def test_slots_are_explicit_canonical_and_have_no_placeholder_versions(self) -> None:
        payload = harness_workflow_manifest_snapshot()
        statuses = {
            value
            for value in _values_for_key(payload, "status")
            if isinstance(value, str)
        }
        self.assertEqual(
            statuses,
            {item.value for item in HarnessManifestSlotStatus},
        )
        serialized = json.dumps(payload, sort_keys=True).lower()
        for placeholder in ('"pending-', '"latest"', '"unknown"'):
            self.assertNotIn(placeholder, serialized)
        for entry in payload["stages"]:
            components = [
                item["component_name"] for item in entry["component_contracts"]
            ]
            self.assertEqual(components, sorted(set(components)))
            artifacts = entry["allowed_artifact_types"]
            if artifacts["status"] == "registered":
                self.assertEqual(
                    artifacts["artifact_types"],
                    sorted(set(artifacts["artifact_types"])),
                )

    def test_unregistered_domains_fail_closed_but_tavern_foundation_is_executable(self) -> None:
        tavern = require_executable_workflow_manifest_entry(
            HarnessWorkflow.TAVERN,
            HarnessStage.TAVERN_ACTOR_REPLY,
        )
        self.assertIsInstance(
            tavern.registration,
            HarnessManifestRegisteredContractSlotV1,
        )
        self.assertIsInstance(
            tavern.eval_suites,
            HarnessManifestRegisteredContractListSlotV1,
        )
        assert isinstance(
            tavern.eval_suites,
            HarnessManifestRegisteredContractListSlotV1,
        )
        self.assertEqual(
            tuple(item.to_harness_ref() for item in tavern.eval_suites.contracts),
            (TAVERN_IDENTITY_EVAL_SUITE,),
        )
        for workflow, stage in HARNESS_OPERATION_STAGE_REGISTRATIONS:
            if (workflow, stage) == (
                HarnessWorkflow.TAVERN,
                HarnessStage.TAVERN_ACTOR_REPLY,
            ):
                continue
            with self.subTest(workflow=workflow.value, stage=stage.value):
                with self.assertRaisesRegex(ValueError, "stage_unregistered"):
                    require_executable_workflow_manifest_entry(workflow, stage)

    def test_planning_tool_execution_references_the_tool_manifest(self) -> None:
        entry = HARNESS_WORKFLOW_MANIFEST_ENTRIES[
            "planning:planning_tool_execution"
        ]
        self.assertIsInstance(
            entry.toolset_contract,
            HarnessManifestRegisteredContractSlotV1,
        )
        assert isinstance(
            entry.toolset_contract,
            HarnessManifestRegisteredContractSlotV1,
        )
        self.assertEqual(entry.toolset_contract.contract.name, "ToolManifestRegistry")
        self.assertEqual(
            entry.toolset_contract.contract.version,
            TOOL_MANIFEST_SCHEMA_VERSION,
        )
        self.assertEqual(
            HARNESS_WORKFLOW_MANIFEST_EVAL_CASE_VERSION,
            HARNESS_EVAL_CASE_SCHEMA_VERSION,
        )
        self.assertIsInstance(
            entry.eval_suites,
            HarnessManifestRegisteredContractListSlotV1,
        )
        assert isinstance(
            entry.eval_suites,
            HarnessManifestRegisteredContractListSlotV1,
        )
        self.assertEqual(
            tuple(item.to_harness_ref() for item in entry.eval_suites.contracts),
            (PLANNING_TOOL_EVAL_SUITE,),
        )

    def test_manifest_rejects_extra_fields_bad_discriminators_order_and_drift(self) -> None:
        baseline = harness_workflow_manifest_snapshot()

        extra = deepcopy(baseline)
        extra["sensitive_payload"] = "forbidden"
        with self.assertRaises(ValidationError):
            HarnessWorkflowManifestV1.model_validate_json(json.dumps(extra))

        bad_slot = deepcopy(baseline)
        bad_slot["stages"][-1]["eval_suites"]["status"] = "pending"
        with self.assertRaises(ValidationError):
            HarnessWorkflowManifestV1.model_validate_json(json.dumps(bad_slot))

        reordered = deepcopy(baseline)
        reordered["stages"][0], reordered["stages"][1] = (
            reordered["stages"][1],
            reordered["stages"][0],
        )
        with self.assertRaisesRegex(ValidationError, "stage_set_invalid"):
            HarnessWorkflowManifestV1.model_validate_json(json.dumps(reordered))

        duplicate_artifact = deepcopy(baseline)
        duplicate_artifact["stages"][-1]["allowed_artifact_types"][
            "artifact_types"
        ].append("tavern_room_snapshot")
        with self.assertRaisesRegex(ValidationError, "artifacts_not_canonical"):
            HarnessWorkflowManifestV1.model_validate_json(
                json.dumps(duplicate_artifact)
            )

        placeholder = deepcopy(baseline)
        placeholder["stages"][-1]["input_contract"]["contract"][
            "version"
        ] = "latest"
        with self.assertRaisesRegex(ValidationError, "version_not_adopted"):
            HarnessWorkflowManifestV1.model_validate_json(json.dumps(placeholder))

    def test_context_inputs_are_checked_against_exact_manifest_contracts(self) -> None:
        entry = require_executable_workflow_manifest_entry(
            HarnessWorkflow.TAVERN,
            HarnessStage.TAVERN_ACTOR_REPLY,
        )
        components = tuple(
            item.contract.contract.to_harness_ref()
            for item in entry.component_contracts
            if isinstance(
                item.contract,
                HarnessManifestRegisteredContractSlotV1,
            )
        )
        validate_harness_context_manifest_inputs(
            entry=entry,
            input_contract=HarnessContractRef(
                name="TavernActorInputManifest",
                version="tavern-actor-input-manifest-v1",
            ),
            prompt_contract=HarnessContractRef(
                name="TavernActorPrompt",
                version="tavern-actor-v1",
            ),
            policy_contract=HarnessContractRef(
                name="TavernHarnessPolicy",
                version="tavern-harness-v1",
            ),
            component_contracts=components,
            artifact_types=(HarnessArtifactType.TAVERN_ROOM_SNAPSHOT,),
        )
        with self.assertRaisesRegex(ValueError, "input_contract_drift"):
            validate_harness_context_manifest_inputs(
                entry=entry,
                input_contract=HarnessContractRef(
                    name="TavernActorInputManifest",
                    version="tavern-actor-input-manifest-v2",
                ),
                prompt_contract=HarnessContractRef(
                    name="TavernActorPrompt",
                    version="tavern-actor-v1",
                ),
                policy_contract=HarnessContractRef(
                    name="TavernHarnessPolicy",
                    version="tavern-harness-v1",
                ),
                component_contracts=components,
                artifact_types=(HarnessArtifactType.TAVERN_ROOM_SNAPSHOT,),
            )
        with self.assertRaisesRegex(ValueError, "component_contract_drift"):
            validate_harness_context_manifest_inputs(
                entry=entry,
                input_contract=HarnessContractRef(
                    name="TavernActorInputManifest",
                    version="tavern-actor-input-manifest-v1",
                ),
                prompt_contract=HarnessContractRef(
                    name="TavernActorPrompt",
                    version="tavern-actor-v1",
                ),
                policy_contract=HarnessContractRef(
                    name="TavernHarnessPolicy",
                    version="tavern-harness-v1",
                ),
                component_contracts=components[:-1],
                artifact_types=(HarnessArtifactType.TAVERN_ROOM_SNAPSHOT,),
            )
        with self.assertRaisesRegex(ValueError, "artifact_not_allowed"):
            validate_harness_context_manifest_inputs(
                entry=entry,
                input_contract=HarnessContractRef(
                    name="TavernActorInputManifest",
                    version="tavern-actor-input-manifest-v1",
                ),
                prompt_contract=HarnessContractRef(
                    name="TavernActorPrompt",
                    version="tavern-actor-v1",
                ),
                policy_contract=HarnessContractRef(
                    name="TavernHarnessPolicy",
                    version="tavern-harness-v1",
                ),
                component_contracts=components,
                artifact_types=(HarnessArtifactType.FRONTEND_RESPONSE_FIXTURE,),
            )

    def test_schema_has_no_open_maps_and_fixture_has_no_sensitive_fields(self) -> None:
        schema = HarnessWorkflowManifestV1.model_json_schema()
        for object_schema in _object_schemas(schema):
            self.assertIs(object_schema.get("additionalProperties"), False)
        forbidden = {
            "raw_prompt",
            "prompt_content",
            "system_prompt",
            "guidance",
            "document_content",
            "transcript_content",
            "secret",
            "token",
            "file_path",
            "raw_payload",
        }
        self.assertTrue(forbidden.isdisjoint(_keys(harness_workflow_manifest_snapshot())))


def _values_for_key(value: object, target: str) -> list[object]:
    if isinstance(value, dict):
        found = [value[target]] if target in value else []
        for child in value.values():
            found.extend(_values_for_key(child, target))
        return found
    if isinstance(value, list):
        return [item for child in value for item in _values_for_key(child, target)]
    return []


def _keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_keys(item) for item in value.values()), set())
    if isinstance(value, list):
        return set().union(*(_keys(item) for item in value), set())
    return set()


def _object_schemas(value: object) -> list[dict[str, object]]:
    if isinstance(value, dict):
        found = [value] if value.get("type") == "object" else []
        for child in value.values():
            found.extend(_object_schemas(child))
        return found
    if isinstance(value, list):
        return [item for child in value for item in _object_schemas(child)]
    return []


if __name__ == "__main__":
    unittest.main()
