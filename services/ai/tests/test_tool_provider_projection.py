from __future__ import annotations

import json
import unittest

from app.models.harness import HarnessStage, HarnessWorkflow
from app.models.tool_manifest import (
    TOOL_MANIFEST_ENTRIES,
    TOOL_MANIFEST_REGISTRY,
    ToolDependency,
    ToolManifestEntryV1,
    ToolManifestRegistryV1,
    ToolProviderCapability,
)
from app.services.tool_provider_projection import (
    ProviderToolCallDecodeError,
    ToolArgumentDecodeError,
    ToolResultValidationError,
    adapt_tool_runtime_result,
    decode_provider_tool_call,
    decode_tool_arguments,
    project_provider_tools,
    project_validated_tool_result,
    provider_function_for_entry,
    validate_tool_runtime_result,
)


class ToolProviderProjectionTests(unittest.TestCase):
    def test_scene_provider_keeps_addressable_members_but_public_trace_does_not(self):
        entry = TOOL_MANIFEST_ENTRIES['study_chat:study_chat_reply:read_scene_overview']
        result = adapt_tool_runtime_result(entry, {
            'ok': True, 'scene_instance_id': 'instance-1', 'selected_scene_id': 'room-2',
            'selected_scene_title': 'Corner', 'selected_scene_path': ['Room', 'Corner'],
            'scene_tree': [{'id': 'room-1', 'title': 'Room', 'objects': [], 'children': [
                {'id': 'room-2', 'title': 'Corner', 'objects': [{'id': 'board-1', 'name': 'Board', 'description': 'Equation'}]}]}]})
        provider = project_validated_tool_result(entry, result, audience='provider')
        self.assertEqual(provider['selected_scene_id'], 'room-2')
        self.assertEqual(provider['scenes'][1]['parent_scene_id'], 'room-1')
        self.assertEqual(provider['objects'], [{'object_id': 'board-1', 'scene_id': 'room-2', 'name': 'Board', 'description': 'Equation'}])
        for audience in ('trace', 'public'):
            projection = json.dumps(project_validated_tool_result(entry, result, audience=audience))
            for protected in ('room-1', 'room-2', 'board-1', 'Equation'):
                self.assertNotIn(protected, projection)

    def test_prepared_scene_provider_returns_followup_target_ids(self):
        for tool, field, target in [('add_scene', 'added_scene_id', 'new-room'), ('add_object', 'object_id', 'new-card'),
                                    ('update_object_description', 'object_id', 'board'), ('delete_object', 'object_id', 'card')]:
            entry = TOOL_MANIFEST_ENTRIES[f'study_chat:study_chat_reply:{tool}']
            result = adapt_tool_runtime_result(entry, {'ok': True, 'scene_instance_id': 'instance-1',
                'effect_state': 'prepared', 'committed': False, 'prepared_effect_id': 'effect-1',
                'scene_profile': {'scene_id': 'room-1'}, field: target})
            provider = project_validated_tool_result(entry, result, audience='provider')
            self.assertEqual(provider[field], target)
            self.assertEqual(provider['selected_scene_id'], 'room-1')
            self.assertFalse(provider['committed'])
            self.assertNotIn(target, json.dumps(project_validated_tool_result(entry, result, audience='public')))

    def test_scene_identity_inventory_reports_truncation(self):
        entry = TOOL_MANIFEST_ENTRIES['study_chat:study_chat_reply:read_scene_overview']
        result = adapt_tool_runtime_result(entry, {'ok': True, 'scene_instance_id': 'instance-1',
            'scene_tree': [{'id': f'room-{i}', 'title': 'Room', 'objects': []} for i in range(129)]})
        provider = project_validated_tool_result(entry, result, audience='provider')
        self.assertEqual(len(provider['scenes']), 128)
        self.assertTrue(provider['truncated'])

    def test_all_available_context_projects_six_planning_and_thirty_one_study_tools(self) -> None:
        dependencies = set(ToolDependency)
        capabilities = set(ToolProviderCapability)
        planning = project_provider_tools(
            workflow=HarnessWorkflow.PLANNING,
            offered_in_stage=HarnessStage.PLAN_GENERATION,
            available_dependencies=dependencies,
            provider_capabilities=capabilities,
        )
        study = project_provider_tools(
            workflow=HarnessWorkflow.STUDY_CHAT,
            offered_in_stage=HarnessStage.STUDY_CHAT_REPLY,
            available_dependencies=dependencies,
            provider_capabilities=capabilities,
        )
        self.assertEqual(len(planning), 6)
        self.assertEqual(len(study), 31)
        self.assertEqual(len({item.function.name for item in planning}), 6)
        self.assertEqual(len({item.function.name for item in study}), 31)
        self.assertTrue(all(item.function.strict for item in (*planning, *study)))

    def test_projection_filters_missing_dependencies_and_capabilities(self) -> None:
        capabilities = {ToolProviderCapability.FUNCTION_CALLING}
        planning = project_provider_tools(
            workflow=HarnessWorkflow.PLANNING,
            offered_in_stage=HarnessStage.PLAN_GENERATION,
            available_dependencies=set(ToolDependency),
            provider_capabilities=capabilities,
        )
        self.assertNotIn(
            "read_page_range_images",
            {item.function.name for item in planning},
        )
        study_without_session = project_provider_tools(
            workflow=HarnessWorkflow.STUDY_CHAT,
            offered_in_stage=HarnessStage.STUDY_CHAT_REPLY,
            available_dependencies=set(ToolDependency) - {ToolDependency.STUDY_SESSION},
            provider_capabilities=set(ToolProviderCapability),
        )
        self.assertNotIn(
            "write_session_memory",
            {item.function.name for item in study_without_session},
        )
        self.assertNotIn(
            "generate_projected_image",
            {item.function.name for item in study_without_session},
        )

    def test_provider_parameters_are_closed_and_derived_from_input_dto(self) -> None:
        entry = TOOL_MANIFEST_ENTRIES[
            "study_chat:study_chat_reply:add_scene"
        ]
        projection = provider_function_for_entry(entry)
        self.assertEqual(projection.function.name, entry.canonical_name)
        self.assertEqual(
            projection.function.parameters["additionalProperties"],
            False,
        )
        self.assertIn("title", projection.function.parameters["properties"])
        self._assert_closed_objects(projection.function.parameters)

    def test_argument_decode_rejects_extra_coercion_nonfinite_duplicate_and_nonobject(self) -> None:
        entry = TOOL_MANIFEST_ENTRIES[
            "planning:planning_tool_execution:read_page_range_content"
        ]
        decoded = decode_tool_arguments(
            entry,
            '{"page_start":1,"page_end":2,"max_chars":1200}',
        )
        self.assertEqual(decoded.page_start, 1)
        invalid_cases = (
            ('{"page_start":1,"page_end":2,"extra":true}', "tool_arguments_contract_invalid"),
            ('{"page_start":"1","page_end":2}', "tool_arguments_contract_invalid"),
            ('{"page_start":NaN,"page_end":2}', "tool_arguments_nonfinite"),
            ('{"page_start":1e999,"page_end":2}', "tool_arguments_nonfinite"),
            ('{"page_start":1,"page_start":2,"page_end":2}', "tool_arguments_duplicate_key"),
            ('[1,2]', "tool_arguments_object_required"),
        )
        for raw, code in invalid_cases:
            with self.subTest(raw=raw):
                with self.assertRaises(ToolArgumentDecodeError) as caught:
                    decode_tool_arguments(entry, raw)
                self.assertEqual(caught.exception.code, code)

    def test_runtime_result_is_exact_and_rejects_extra_coercion_and_nonfinite(self) -> None:
        content_entry = TOOL_MANIFEST_ENTRIES[
            "planning:planning_tool_execution:read_page_range_content"
        ]
        valid = {
            "schema_name": "planning-tool-result",
            "schema_version": "planning-tool-result-v1",
            "ok": True,
            "tool_name": "read_page_range_content",
            "page_start": 1,
            "page_end": 2,
            "chunk_count": 1,
            "content": "chapter text",
        }
        self.assertEqual(
            validate_tool_runtime_result(content_entry, valid).tool_name,
            "read_page_range_content",
        )
        for mutation in (
            {"extra": True},
            {"page_start": "1"},
            {"tool_name": "read_page_range_images"},
        ):
            candidate = {**valid, **mutation}
            with self.subTest(mutation=mutation):
                with self.assertRaises(ToolResultValidationError):
                    validate_tool_runtime_result(content_entry, candidate)

        progress_entry = TOOL_MANIFEST_ENTRIES[
            "study_chat:study_chat_reply:read_learning_plan_progress"
        ]
        nonfinite = {
            "schema_name": "study-chat-tool-result",
            "schema_version": "study-chat-tool-result-v1",
            "ok": True,
            "summary": "",
            "tool_name": "read_learning_plan_progress",
            "course_title": "Course",
            "completion_percent": float("nan"),
            "schedule": [],
        }
        with self.assertRaisesRegex(ToolResultValidationError, "tool_result_nonfinite"):
            validate_tool_runtime_result(progress_entry, nonfinite)

    def test_error_result_is_also_strict_and_canonical(self) -> None:
        entry = TOOL_MANIFEST_ENTRIES[
            "study_chat:study_chat_reply:read_system_time"
        ]
        valid_error = {
            "schema_name": "study-chat-tool-result",
            "schema_version": "study-chat-tool-result-v1",
            "ok": False,
            "tool_name": "read_system_time",
            "error": "runtime_failed",
            "path": [],
            "detail": "",
        }
        result = validate_tool_runtime_result(entry, valid_error)
        self.assertFalse(result.ok)
        with self.assertRaises(ToolResultValidationError):
            validate_tool_runtime_result(entry, {**valid_error, "extra": "no"})

    def test_planning_provider_receives_content_but_observability_does_not(self) -> None:
        entry = TOOL_MANIFEST_ENTRIES[
            "planning:planning_tool_execution:read_page_range_content"
        ]
        protected_text = "protected planning context: extensionality"
        result = adapt_tool_runtime_result(
            entry,
            {
                "ok": True,
                "page_start": 1,
                "page_end": 2,
                "chunk_count": 1,
                "content": protected_text,
            },
        )

        provider = project_validated_tool_result(entry, result, audience="provider")
        trace = project_validated_tool_result(entry, result, audience="trace")
        public = project_validated_tool_result(entry, result, audience="public")

        self.assertEqual(provider["content"], protected_text)
        self.assertNotIn(protected_text, json.dumps(trace))
        self.assertNotIn(protected_text, json.dumps(public))
        self.assertTrue(trace["content_free"])
        self.assertTrue(public["redacted"])

    def test_transport_alias_decodes_to_canonical_and_id_is_only_correlation(self) -> None:
        original = TOOL_MANIFEST_ENTRIES[
            "planning:planning_tool_execution:get_study_unit_detail"
        ]
        payload = original.model_dump(mode="python")
        payload["aliases"] = ("legacy_study_unit_detail",)
        aliased = ToolManifestEntryV1.model_validate(payload)
        registry = ToolManifestRegistryV1(
            tools=tuple(
                sorted(
                    (
                        aliased if entry.key == original.key else entry
                        for entry in TOOL_MANIFEST_REGISTRY.tools
                    ),
                    key=lambda entry: entry.key,
                )
            )
        )
        decoded = decode_provider_tool_call(
            {
                "id": "provider-call-99",
                "type": "function",
                "function": {
                    "name": "legacy_study_unit_detail",
                    "arguments": json.dumps(
                        {"study_unit_id": "unit-1", "focus": "proof"}
                    ),
                },
            },
            workflow=HarnessWorkflow.PLANNING,
            offered_in_stage=HarnessStage.PLAN_GENERATION,
            registry=registry,
        )
        self.assertEqual(decoded.transport_correlation_id, "provider-call-99")
        self.assertEqual(decoded.canonical_name, "get_study_unit_detail")
        self.assertEqual(decoded.manifest_key, original.key)
        self.assertNotIn("provider-call-99", decoded.manifest_key)

    def test_tool_call_decode_rejects_unknown_and_transport_extra_fields(self) -> None:
        base = {
            "id": "call-1",
            "type": "function",
            "function": {"name": "unknown_tool", "arguments": "{}"},
        }
        with self.assertRaises(ProviderToolCallDecodeError):
            decode_provider_tool_call(
                base,
                workflow=HarnessWorkflow.STUDY_CHAT,
                offered_in_stage=HarnessStage.STUDY_CHAT_REPLY,
            )
        with self.assertRaisesRegex(
            ProviderToolCallDecodeError,
            "provider_tool_call_shape_invalid",
        ):
            decode_provider_tool_call(
                {**base, "operation_id": "must-not-derive-from-tool-call-id"},
                workflow=HarnessWorkflow.STUDY_CHAT,
                offered_in_stage=HarnessStage.STUDY_CHAT_REPLY,
            )

    def _assert_closed_objects(self, value: object) -> None:
        if isinstance(value, list):
            for item in value:
                self._assert_closed_objects(item)
            return
        if not isinstance(value, dict):
            return
        if value.get("type") == "object":
            self.assertIs(value.get("additionalProperties"), False)
        for child in value.values():
            self._assert_closed_objects(child)


if __name__ == "__main__":
    unittest.main()
