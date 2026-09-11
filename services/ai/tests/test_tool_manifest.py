from __future__ import annotations

import json
import unittest
from pathlib import Path

from pydantic import ValidationError

from app.models.harness import HarnessStage, HarnessWorkflow
from app.models.tool_manifest import (
    GENERATED_IMAGE_EFFECTS,
    TOOL_INPUT_MODELS,
    TOOL_MANIFEST_ENTRIES,
    TOOL_MANIFEST_REGISTRY,
    TOOL_RESULT_MODELS,
    ToolEffectBoundaryKind,
    ToolLifecycleStatus,
    ToolManifestEntryV1,
    ToolManifestRegistryV1,
    provider_parameters_digest,
    resolve_tool_manifest_entry,
    resolve_tool_manifest_reference,
)
from app.services.tool_provider_projection import tool_manifest_golden_snapshot


REPO_ROOT = Path(__file__).resolve().parents[3]
GOLDEN_PATH = REPO_ROOT / "packages/shared/fixtures/harness/tool-manifest-v1.json"


class ToolManifestTests(unittest.TestCase):
    def test_detail_batch_budget_preserves_total_ceiling_and_other_tool_limits(self):
        from app.services.tool_provider_projection import ToolExecutionBudgetTracker, ToolContractViolation
        detail = next(entry for entry in TOOL_MANIFEST_ENTRIES.values()
            if entry.workflow == HarnessWorkflow.PLANNING and entry.canonical_name == "get_study_unit_detail")
        self.assertEqual(detail.budget.max_calls_per_round, 3)
        self.assertEqual(detail.budget.max_calls_per_operation, 4)
        self.assertEqual(detail.parallel.runtime_mode, "serial")
        tracker = ToolExecutionBudgetTracker()
        for _ in range(3):
            tracker.admit(detail)
        with self.assertRaisesRegex(ToolContractViolation, "tool_round_budget_exceeded"):
            tracker.admit(detail)
        tracker.begin_round()
        tracker.admit(detail)
        with self.assertRaisesRegex(ToolContractViolation, "tool_operation_budget_exceeded"):
            tracker.admit(detail)
        for entry in TOOL_MANIFEST_ENTRIES.values():
            if entry.key != detail.key:
                self.assertEqual(entry.budget.max_calls_per_round, 1)

    def test_production_chat_projection_assembles_all_registered_tools(self) -> None:
        from app.services.model_provider import _chat_tools
        from app.services.model_tool_config import TOOL_CATALOG, CHAT_STAGE

        class FullRuntime:
            def available_tool_names(self):
                return list(TOOL_CATALOG[CHAT_STAGE])

        tools = _chat_tools(
            tools_enabled=True, memory_tool_enabled=True, memory_hits=[],
            multimodal_enabled=False, debug_report=None, document_path=None,
            session_tool_runtime=FullRuntime(),
        )
        self.assertEqual(len(tools), 31)
        self.assertEqual({tool["function"]["name"] for tool in tools}, set(TOOL_CATALOG[CHAT_STAGE]))

    def test_catalog_is_complete_stage_qualified_and_strict(self) -> None:
        entries = TOOL_MANIFEST_REGISTRY.tools
        self.assertEqual(len(entries), 37)
        self.assertEqual(len({entry.key for entry in entries}), 37)
        self.assertEqual(
            sum(entry.workflow == HarnessWorkflow.PLANNING for entry in entries),
            6,
        )
        self.assertEqual(
            sum(entry.workflow == HarnessWorkflow.STUDY_CHAT for entry in entries),
            31,
        )
        self.assertEqual(set(TOOL_MANIFEST_ENTRIES), set(TOOL_INPUT_MODELS))
        self.assertEqual(set(TOOL_MANIFEST_ENTRIES), set(TOOL_RESULT_MODELS))
        self.assertEqual(len(set(TOOL_INPUT_MODELS.values())), 37)
        self.assertEqual(len(set(TOOL_RESULT_MODELS.values())), 37)
        for entry in entries:
            self.assertEqual(
                entry.key,
                f"{entry.workflow.value}:{entry.execution_stage.value}:{entry.canonical_name}",
            )
            self.assertEqual(entry.status, ToolLifecycleStatus.ACTIVE)
            self.assertFalse(entry.parallel.parallel_safe)
            self.assertEqual(entry.parallel.runtime_mode.value, "serial")
            input_model = TOOL_INPUT_MODELS[entry.key]
            result_model = TOOL_RESULT_MODELS[entry.key]
            self.assertEqual(input_model.model_config.get("extra"), "forbid")
            self.assertTrue(input_model.model_config.get("strict"))
            self.assertEqual(result_model.model_config.get("extra"), "forbid")
            self.assertTrue(result_model.model_config.get("strict"))
            self.assertEqual(
                entry.provider_parameters_digest,
                provider_parameters_digest(input_model),
            )

    def test_same_transport_names_remain_stage_qualified(self) -> None:
        for name in ("read_page_range_content", "read_page_range_images"):
            planning_key = f"planning:planning_tool_execution:{name}"
            study_key = f"study_chat:study_chat_reply:{name}"
            self.assertIn(planning_key, TOOL_MANIFEST_ENTRIES)
            self.assertIn(study_key, TOOL_MANIFEST_ENTRIES)
            self.assertNotEqual(
                TOOL_INPUT_MODELS[planning_key],
                TOOL_INPUT_MODELS[study_key],
            )

    def test_generated_image_has_ordered_external_then_database_effects(self) -> None:
        entry = TOOL_MANIFEST_ENTRIES[
            "study_chat:study_chat_reply:generate_projected_image"
        ]
        self.assertEqual(entry.effect_steps, GENERATED_IMAGE_EFFECTS)
        self.assertEqual(
            [step.boundary_kind for step in entry.effect_steps],
            [
                ToolEffectBoundaryKind.EXTERNAL_CALL,
                ToolEffectBoundaryKind.DATABASE_WRITE,
            ],
        )
        self.assertEqual(
            [step.adapter.name for step in entry.effect_steps if step.adapter],
            ["study_provider_execution", "study_projection_mutation"],
        )

    def test_alias_resolves_to_canonical_name_for_execution(self) -> None:
        original = TOOL_MANIFEST_ENTRIES[
            "planning:planning_tool_execution:get_study_unit_detail"
        ]
        payload = original.model_dump(mode="python")
        payload["aliases"] = ("legacy_study_unit_detail",)
        aliased = ToolManifestEntryV1.model_validate(payload)
        registry = self._registry_replacing(original.key, aliased)
        resolved = resolve_tool_manifest_entry(
            workflow=HarnessWorkflow.PLANNING,
            offered_in_stage=HarnessStage.PLAN_GENERATION,
            transport_name="legacy_study_unit_detail",
            registry=registry,
        )
        self.assertEqual(resolved.canonical_name, "get_study_unit_detail")

    def test_retired_entry_is_readable_but_not_executable(self) -> None:
        original = TOOL_MANIFEST_ENTRIES[
            "planning:planning_tool_execution:get_study_unit_detail"
        ]
        replacement = TOOL_MANIFEST_ENTRIES[
            "planning:planning_tool_execution:estimate_plan_completion"
        ]
        payload = original.model_dump(mode="python")
        payload["status"] = ToolLifecycleStatus.RETIRED
        payload["replacement_key"] = replacement.key
        retired = ToolManifestEntryV1.model_validate(payload)
        registry = self._registry_replacing(original.key, retired)
        historical = resolve_tool_manifest_reference(
            workflow=HarnessWorkflow.PLANNING,
            offered_in_stage=HarnessStage.PLAN_GENERATION,
            transport_name=original.canonical_name,
            registry=registry,
        )
        self.assertEqual(historical.status, ToolLifecycleStatus.RETIRED)
        with self.assertRaisesRegex(ValueError, "tool_manifest_tool_retired"):
            resolve_tool_manifest_entry(
                workflow=HarnessWorkflow.PLANNING,
                offered_in_stage=HarnessStage.PLAN_GENERATION,
                transport_name=original.canonical_name,
                registry=registry,
            )

    def test_retired_replacement_must_be_active_and_stage_compatible(self) -> None:
        first = TOOL_MANIFEST_ENTRIES[
            "planning:planning_tool_execution:get_study_unit_detail"
        ]
        second = TOOL_MANIFEST_ENTRIES[
            "planning:planning_tool_execution:estimate_plan_completion"
        ]
        first_payload = first.model_dump(mode="python")
        first_payload.update(
            status=ToolLifecycleStatus.RETIRED,
            replacement_key=second.key,
        )
        second_payload = second.model_dump(mode="python")
        second_payload.update(
            status=ToolLifecycleStatus.RETIRED,
            replacement_key=first.key,
        )
        retired_first = ToolManifestEntryV1.model_validate(first_payload)
        retired_second = ToolManifestEntryV1.model_validate(second_payload)
        replacements = {
            first.key: retired_first,
            second.key: retired_second,
        }
        tools = tuple(
            sorted(
                (replacements.get(entry.key, entry) for entry in TOOL_MANIFEST_REGISTRY.tools),
                key=lambda entry: entry.key,
            )
        )
        with self.assertRaisesRegex(ValidationError, "tool_manifest_replacement_not_active"):
            ToolManifestRegistryV1(tools=tools)

    def test_python_registry_and_provider_schemas_match_golden(self) -> None:
        expected = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
        self.assertEqual(tool_manifest_golden_snapshot(), expected)

    def test_placeholder_contracts_and_wrong_stage_routes_fail_closed(self) -> None:
        original = TOOL_MANIFEST_ENTRIES[
            "planning:planning_tool_execution:get_study_unit_detail"
        ]
        placeholder = original.model_dump(mode="python")
        placeholder["runtime_adapter"] = {
            "name": "plan_tool_runtime.get_study_unit_detail",
            "version": "latest",
        }
        with self.assertRaisesRegex(ValidationError, "version_not_adopted"):
            ToolManifestEntryV1.model_validate(placeholder)

        wrong_stage = original.model_dump(mode="python")
        wrong_stage["offered_in_stage"] = HarnessStage.STUDY_CHAT_REPLY
        with self.assertRaisesRegex(ValidationError, "workflow_stage_mismatch"):
            ToolManifestEntryV1.model_validate(wrong_stage)

    @staticmethod
    def _registry_replacing(
        key: str,
        replacement: ToolManifestEntryV1,
    ) -> ToolManifestRegistryV1:
        return ToolManifestRegistryV1(
            tools=tuple(
                sorted(
                    (
                        replacement if entry.key == key else entry
                        for entry in TOOL_MANIFEST_REGISTRY.tools
                    ),
                    key=lambda entry: entry.key,
                )
            )
        )


if __name__ == "__main__":
    unittest.main()
