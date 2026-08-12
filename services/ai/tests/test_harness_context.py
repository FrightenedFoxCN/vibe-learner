from __future__ import annotations

import json
from pathlib import Path
import unittest

from pydantic import BaseModel, ConfigDict

from app.models.harness import HarnessResourceRef, HarnessWorkflow
from app.services.harness_context import (
    HARNESS_CONTEXT_SCHEMA_NAME,
    HARNESS_CONTEXT_SCHEMA_VERSION,
    HarnessSnapshotMaterial,
    build_harness_context,
)


FIXTURE_ROOT = Path(__file__).parent / "fixtures" / "harness"


class _NestedInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    label: str
    optional_note: str | None


class _ExampleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    document_id: str
    score: float
    nested: _NestedInput


class _LooseInput(BaseModel):
    value: str


def _build(
    *,
    operation_id: str = "operation-ctx-1",
    typed_input: BaseModel | None = None,
    subject_refs: list[HarnessResourceRef] | None = None,
    component_versions: dict[str, str] | None = None,
    snapshot_materials: list[HarnessSnapshotMaterial] | None = None,
    policy_version: str | None = "planning-policy-v2",
    prompt_version: str | None = "planning-prompt-v3",
):
    return build_harness_context(
        workflow=HarnessWorkflow.PLANNING,
        operation_id=operation_id,
        schema_name=HARNESS_CONTEXT_SCHEMA_NAME,
        schema_version=HARNESS_CONTEXT_SCHEMA_VERSION,
        typed_input=typed_input
        if typed_input is not None
        else _ExampleInput(
            document_id="文档-1",
            score=0.5,
            nested=_NestedInput(label="你好", optional_note=None),
        ),
        subject_refs=subject_refs
        if subject_refs is not None
        else [
            HarnessResourceRef(
                resource_type="persona",
                resource_id="persona-2",
                revision=3,
            ),
            HarnessResourceRef(
                resource_type="document",
                resource_id="document-1",
                revision=None,
            ),
        ],
        component_versions=component_versions
        if component_versions is not None
        else {"toolset": "planning-tools-v2", "decoder": "plan-decoder-v1"},
        snapshot_materials=snapshot_materials
        if snapshot_materials is not None
        else [
            HarnessSnapshotMaterial(
                artifact_type="outline",
                artifact_id="outline-1",
                schema_version="outline-v2",
                payload={"units": [2, 1], "summary": "章节"},
            ),
            HarnessSnapshotMaterial(
                artifact_type="persona",
                artifact_id="persona-2",
                schema_version="persona-runtime-v1",
                payload={"name": "老师", "note": None},
            ),
        ],
        policy_version=policy_version,
        prompt_version=prompt_version,
    )


def _all_keys(value: object) -> set[str]:
    if isinstance(value, dict):
        return set(value).union(*(_all_keys(item) for item in value.values()))
    if isinstance(value, list):
        return set().union(*(_all_keys(item) for item in value), set())
    return set()


class HarnessContextTests(unittest.TestCase):
    def test_golden_context_is_stable_and_contains_no_source_payload(self) -> None:
        expected = json.loads(
            (FIXTURE_ROOT / "context_foundation_v1.json").read_text(encoding="utf-8")
        )

        wire = _build().model_dump(mode="json", exclude_none=False)

        self.assertEqual(wire, expected)
        self.assertNotIn("payload", _all_keys(wire))
        self.assertNotIn("章节", json.dumps(wire, ensure_ascii=False))
        self.assertNotIn("老师", json.dumps(wire, ensure_ascii=False))
        self.assertEqual(len(wire["input_digest"]), 64)
        self.assertEqual(len(wire["context_digest"]), 64)

    def test_order_and_exact_duplicates_are_canonicalized(self) -> None:
        baseline = _build()
        reversed_context = _build(
            operation_id="operation-ctx-2",
            subject_refs=[
                HarnessResourceRef(
                    resource_type="document",
                    resource_id="document-1",
                    revision=None,
                ),
                HarnessResourceRef(
                    resource_type="persona",
                    resource_id="persona-2",
                    revision=3,
                ),
                HarnessResourceRef(
                    resource_type="document",
                    resource_id="document-1",
                    revision=None,
                ),
            ],
            component_versions={
                "decoder": "plan-decoder-v1",
                "toolset": "planning-tools-v2",
            },
            snapshot_materials=list(
                reversed(
                    [
                        HarnessSnapshotMaterial(
                            artifact_type="outline",
                            artifact_id="outline-1",
                            schema_version="outline-v2",
                            payload={"summary": "章节", "units": [2, 1]},
                        ),
                        HarnessSnapshotMaterial(
                            artifact_type="persona",
                            artifact_id="persona-2",
                            schema_version="persona-runtime-v1",
                            payload={"note": None, "name": "老师"},
                        ),
                    ]
                )
            ),
        )

        self.assertEqual(baseline.input_digest, reversed_context.input_digest)
        self.assertEqual(baseline.context_digest, reversed_context.context_digest)
        self.assertEqual(baseline.subject_refs, reversed_context.subject_refs)
        self.assertNotEqual(baseline.operation_id, reversed_context.operation_id)

    def test_input_snapshot_component_policy_and_prompt_drift_change_digests(self) -> None:
        baseline = _build()
        input_changed = _build(
            typed_input=_ExampleInput(
                document_id="文档-2",
                score=0.5,
                nested=_NestedInput(label="你好", optional_note=None),
            )
        )
        snapshot_changed = _build(
            snapshot_materials=[
                HarnessSnapshotMaterial(
                    artifact_type="outline",
                    artifact_id="outline-1",
                    schema_version="outline-v2",
                    payload={"units": [1, 2], "summary": "章节"},
                )
            ]
        )
        component_changed = _build(
            component_versions={"toolset": "planning-tools-v3"}
        )

        self.assertNotEqual(baseline.input_digest, input_changed.input_digest)
        self.assertNotEqual(baseline.context_digest, input_changed.context_digest)
        for changed in (
            snapshot_changed,
            component_changed,
            _build(policy_version="planning-policy-v3"),
            _build(prompt_version="planning-prompt-v4"),
        ):
            self.assertEqual(baseline.input_digest, changed.input_digest)
            self.assertNotEqual(baseline.context_digest, changed.context_digest)

    def test_conflicting_duplicate_references_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "harness_context_subject_ref_conflict"):
            _build(
                subject_refs=[
                    HarnessResourceRef(
                        resource_type="document",
                        resource_id="document-1",
                        revision=1,
                    ),
                    HarnessResourceRef(
                        resource_type="document",
                        resource_id="document-1",
                        revision=2,
                    ),
                ]
            )

        material = HarnessSnapshotMaterial(
            artifact_type="outline",
            artifact_id="outline-1",
            schema_version="outline-v2",
            payload={"units": [1]},
        )
        conflicting_material = HarnessSnapshotMaterial(
            artifact_type="outline",
            artifact_id="outline-1",
            schema_version="outline-v2",
            payload={"units": [2]},
        )
        with self.assertRaisesRegex(ValueError, "harness_context_snapshot_ref_conflict"):
            _build(snapshot_materials=[material, conflicting_material])

    def test_loose_input_and_non_finite_values_are_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "harness_context_input_extra_forbid_required"):
            _build(typed_input=_LooseInput(value="unsafe"))

        with self.assertRaises(ValueError):
            _build(
                typed_input=_ExampleInput(
                    document_id="document-1",
                    score=float("nan"),
                    nested=_NestedInput(label="test", optional_note=None),
                )
            )


if __name__ == "__main__":
    unittest.main()
