from __future__ import annotations

from datetime import UTC, datetime, timedelta
import json
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, ConfigDict

from app.models.domain import StudyChatResult
from app.models.harness import (
    HarnessArtifactType,
    HarnessCheckStatus,
    HarnessCheckV2,
    HarnessContractRef,
    HarnessResourceRefV3,
    HarnessResourceType,
    HarnessSafeManifest,
    HarnessSnapshotRefV3,
    HarnessStage,
    HarnessStatus,
    HarnessWorkflow,
)
from app.models.harness_artifact_access import (
    HarnessArtifactGrantScopeV1,
    HarnessArtifactPermission,
    HarnessArtifactResolutionStatus,
    HarnessArtifactResolveRequestV1,
)
from app.models.harness_operation import HarnessOperationBindingV1
from app.persistence.harness_artifact_repository import HarnessArtifactRepository
from app.services.harness_runtime import (
    HarnessRuntimeArtifactResolver,
    HarnessRuntimeResolvedArtifact,
    HarnessRuntimeValidationResult,
)


STUDY_SNAPSHOT_CONTRACT = HarnessContractRef(
    name="StudyChatProtectedSnapshot", version="study-chat-protected-snapshot-v1"
)
STUDY_INPUT_CONTRACT = HarnessContractRef(
    name="StudyChatInputManifest", version="study-chat-input-manifest-v1"
)
STUDY_PROMPT_CONTRACT = HarnessContractRef(
    name="StudyChatPrompt", version="study-chat-prompt-v1"
)
STUDY_POLICY_CONTRACT = HarnessContractRef(
    name="StudyChatHarnessPolicy", version="study-chat-harness-v1"
)


class StudyChatInputManifest(HarnessSafeManifest):
    """Content-free identity for one admitted Study Chat request."""

    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {
            "session_id",
            "document_id",
            "plan_id",
            "scene_id",
            "session_revision",
            "attachment_count",
        }
    )

    session_id: str
    document_id: str | None = None
    plan_id: str | None = None
    scene_id: str | None = None
    session_revision: int
    attachment_count: int = 0


class StudyChatRuntimeOutputV1(BaseModel):
    """Strict wrapper around the complete application-owned reply projection."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_name: Literal["StudyChatRuntimeOutput"] = "StudyChatRuntimeOutput"
    schema_version: Literal["study-chat-runtime-output-v1"] = (
        "study-chat-runtime-output-v1"
    )
    result: StudyChatResult


def build_study_context(
    *,
    operation_binding: HarnessOperationBindingV1,
    manifest: StudyChatInputManifest,
    snapshots: tuple[HarnessSnapshotRefV3, ...] = (),
):
    from app.services.harness_context import build_harness_context

    subjects = [
        HarnessResourceRefV3(
            resource_type=HarnessResourceType.STUDY_SESSION,
            resource_id=manifest.session_id,
            revision=manifest.session_revision,
        )
    ]
    return build_harness_context(
        workflow=HarnessWorkflow.STUDY_CHAT,
        stage=HarnessStage.STUDY_CHAT_REPLY,
        operation_binding=operation_binding,
        input_contract=STUDY_INPUT_CONTRACT,
        input_manifest=manifest,
        subject_refs=subjects,
        snapshot_refs=snapshots,
        prompt_contract=STUDY_PROMPT_CONTRACT,
        policy_contract=STUDY_POLICY_CONTRACT,
    )


def canonical_study_snapshot(payload: dict[str, Any]) -> bytes:
    """Canonical protected bytes; content never enters trace-visible evidence."""

    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def decode_study_snapshot(payload: object) -> dict[str, Any]:
    """Validate the resolved artifact envelope before any provider call."""

    if not isinstance(payload, bytes):
        raise ValueError("study_snapshot_bytes_required")
    try:
        decoded = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("study_snapshot_payload_invalid") from exc
    if not isinstance(decoded, dict):
        raise ValueError("study_snapshot_object_required")
    if decoded.get("schema_name") != "StudyChatProtectedSnapshot":
        raise ValueError("study_snapshot_schema_name_invalid")
    if decoded.get("schema_version") != STUDY_SNAPSHOT_CONTRACT.version:
        raise ValueError("study_snapshot_schema_version_invalid")
    dependencies = decoded.get("dependencies")
    if not isinstance(dependencies, dict):
        raise ValueError("study_snapshot_dependencies_required")
    required = {
        "input",
        "session",
        "persona",
        "bound_plan",
        "active_plan",
        "document",
        "document_debug",
        "memory_sessions",
        "session_prompt",
        "model_message",
        "active_plan_context",
        "attachment_context",
        "learner_multimodal_parts",
        "session_state_context",
        "active_scene_summary",
        "active_scene_context",
        "learner_attachments",
    }
    if set(dependencies) != required:
        raise ValueError("study_snapshot_dependency_set_mismatch")
    return decoded


class StudyHarnessArtifactResolver(HarnessRuntimeArtifactResolver):
    """Resolve exactly the operation-scoped Study snapshot before generation."""

    def __init__(
        self,
        repository: HarnessArtifactRepository,
        grants: dict[str, str],
    ) -> None:
        self.repository = repository
        self.grants = dict(grants)

    def resolve(self, *, operation_binding, context):
        resolved: list[HarnessRuntimeResolvedArtifact] = []
        requests: list[HarnessArtifactResolveRequestV1] = []
        for ref in context.snapshot_refs:
            grant_id = self.grants.get(ref.artifact_id)
            if not grant_id:
                raise PermissionError("harness_artifact_grant_missing")
            requests.append(
                HarnessArtifactResolveRequestV1(
                    grant_id=grant_id,
                    harness_operation_id=operation_binding.harness_operation_id,
                    artifact_id=ref.artifact_id,
                    artifact_type=ref.artifact_type,
                    artifact_contract=ref.contract,
                    permission=HarnessArtifactPermission.READ,
                )
            )
        if not requests:
            return ()
        for result in self.repository.resolve_batch(requests).results:
            if result.status != HarnessArtifactResolutionStatus.RESOLVED:
                raise PermissionError(
                    f"harness_artifact_resolution_{result.status.value}"
                )
            if result.content is None or result.payload_digest is None:
                raise ValueError("harness_artifact_resolved_payload_missing")
            decode_study_snapshot(result.content)
            resolved.append(
                HarnessRuntimeResolvedArtifact(
                    artifact_id=result.artifact_id,
                    payload_digest=result.payload_digest,
                    payload=result.content,
                )
            )
        return tuple(resolved)


class StudyV3SnapshotService:
    def __init__(self, artifacts: HarnessArtifactRepository) -> None:
        self.artifacts = artifacts

    def register_session_snapshot(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        payload: dict[str, Any],
    ) -> tuple[HarnessSnapshotRefV3, str]:
        content = canonical_study_snapshot(payload)
        registration = self.artifacts.register_artifact(
            artifact_type=HarnessArtifactType.STUDY_SESSION_SNAPSHOT,
            artifact_contract=STUDY_SNAPSHOT_CONTRACT,
            content=content,
        )
        grant = self.artifacts.issue_grant(
            harness_operation_id=operation_binding.harness_operation_id,
            scopes=(
                HarnessArtifactGrantScopeV1(
                    artifact_id=registration.artifact_id,
                    artifact_type=HarnessArtifactType.STUDY_SESSION_SNAPSHOT,
                    artifact_contract=STUDY_SNAPSHOT_CONTRACT,
                    permission=HarnessArtifactPermission.READ,
                ),
            ),
            expires_at=datetime.now(UTC) + timedelta(minutes=15),
        )
        return (
            HarnessSnapshotRefV3(
                artifact_type=HarnessArtifactType.STUDY_SESSION_SNAPSHOT,
                artifact_id=registration.artifact_id,
                contract=STUDY_SNAPSHOT_CONTRACT,
                payload_digest=registration.payload_digest,
            ),
            grant.grant_id,
        )

    def resolve_snapshot(
        self,
        *,
        operation_binding: HarnessOperationBindingV1,
        snapshot: HarnessSnapshotRefV3,
        grant_id: str,
    ) -> bytes:
        resolver = StudyHarnessArtifactResolver(
            self.artifacts,
            {snapshot.artifact_id: grant_id},
        )
        context = type(
            "StudySnapshotResolutionContext",
            (),
            {"snapshot_refs": (snapshot,)},
        )()
        return resolver.resolve(
            operation_binding=operation_binding,
            context=context,
        )[0].payload


class StudyV3ReplyAdapter:
    """Strict application boundary for the complete Study Chat result."""

    def decode(self, raw: object) -> StudyChatRuntimeOutputV1:
        if isinstance(raw, StudyChatRuntimeOutputV1):
            output = StudyChatRuntimeOutputV1.model_validate(
                raw.model_dump(mode="python", exclude_none=False),
                strict=True,
            )
        elif isinstance(raw, StudyChatResult):
            output = StudyChatRuntimeOutputV1(result=raw)
        elif isinstance(raw, dict):
            candidate = raw if "result" in raw else {"result": raw}
            unknown_wrapper = set(candidate) - set(StudyChatRuntimeOutputV1.model_fields)
            if unknown_wrapper:
                raise ValueError("study_v3_reply_wrapper_extra_forbidden")
            result_payload = candidate.get("result")
            if isinstance(result_payload, dict):
                unknown_result = set(result_payload) - set(StudyChatResult.model_fields)
                if unknown_result:
                    raise ValueError("study_v3_reply_extra_forbidden")
            output = StudyChatRuntimeOutputV1.model_validate(candidate, strict=True)
        else:
            raise ValueError("study_v3_reply_object_required")
        result = output.result
        if not result.reply.strip():
            raise ValueError("study_v3_reply_text_required")
        if any(
            not item.source_kind.strip()
            or not item.title.strip()
            or item.page_end < item.page_start
            for item in result.citations
        ):
            raise ValueError("study_v3_citation_source_required")
        for event in result.character_events:
            if not event.emotion.strip() or not event.action.strip():
                raise ValueError("study_v3_character_event_shape_invalid")
        for call in result.tool_calls:
            if (
                not call.tool_call_id.strip()
                or not call.tool_name.strip()
                or not call.argument_contract_version.strip()
                or not call.result_contract_version.strip()
                or not call.result_json.strip()
            ):
                raise ValueError("study_v3_nested_tool_result_invalid")
            try:
                arguments = json.loads(call.arguments_json)
                result_payload = json.loads(call.result_json)
            except json.JSONDecodeError as exc:
                raise ValueError("study_v3_nested_tool_json_invalid") from exc
            if not isinstance(arguments, dict) or not isinstance(result_payload, dict):
                raise ValueError("study_v3_nested_tool_object_required")
        return output

    def checks(self, output: StudyChatRuntimeOutputV1) -> tuple[HarnessCheckV2, ...]:
        result = self.decode(output).result
        return (
            HarnessCheckV2(
                name="study_chat_reply_schema",
                status=HarnessCheckStatus.PASSED,
                code="",
                message="",
            ),
            HarnessCheckV2(
                name="study_chat_citation_sources",
                status=HarnessCheckStatus.PASSED,
                code="",
                message=str(len(result.citations)),
            ),
            HarnessCheckV2(
                name="study_chat_character_events",
                status=HarnessCheckStatus.PASSED,
                code="",
                message=str(len(result.character_events)),
            ),
            HarnessCheckV2(
                name="study_chat_nested_tools",
                status=HarnessCheckStatus.PASSED,
                code="",
                message=str(len(result.tool_calls)),
            ),
        )

    def validate(
        self,
        output: StudyChatRuntimeOutputV1,
    ) -> HarnessRuntimeValidationResult:
        decoded = self.decode(output)
        checks = list(self.checks(decoded))
        recoveries = decoded.result.model_recoveries
        if not recoveries:
            return HarnessRuntimeValidationResult(
                output=decoded,
                checks=tuple(checks),
            )
        strategies = "+".join(
            dict.fromkeys(item.strategy for item in recoveries if item.strategy)
        )[:320]
        checks.append(
            HarnessCheckV2(
                name="study_chat_model_recovery",
                status=HarnessCheckStatus.WARNING,
                code=":".join(
                    [recoveries[-1].category, recoveries[-1].reason]
                )[:160],
                message=strategies,
            )
        )
        return HarnessRuntimeValidationResult(
            output=decoded,
            checks=tuple(checks),
            status=HarnessStatus.REPAIRED,
            recovery_strategy=strategies or "provider_bounded_recovery",
        )
