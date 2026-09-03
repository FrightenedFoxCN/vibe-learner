"""Small, production-safe v3 context helpers for Tavern actor stages."""
from __future__ import annotations

from typing import Callable, ClassVar
import json

from app.models.harness import (
    HarnessArtifactType,
    HarnessContractRef,
    HarnessResourceRefV3,
    HarnessSnapshotRefV3,
    HarnessSafeManifest,
    HarnessStage,
    HarnessWorkflow,
    HarnessStatus,
)
from app.models.tavern import TavernRoomDetail
from app.models.harness_operation import HarnessOperationBindingV1
from app.services.harness_context import build_harness_context
from app.models.harness import HarnessCheckV2
from app.services.harness_runtime import (
    HarnessRuntimeDomainValidationError,
    HarnessRuntimeStageAdapter,
    HarnessRuntimeValidationResult,
)
from app.services.tavern_harness import TavernActorHarness, TavernHarnessViolation
from app.models.tavern import TavernActorReply, TavernParticipantRecord, TavernMessageRecord
from app.models.harness_artifact_access import (
    HarnessArtifactPermission,
    HarnessArtifactResolveRequestV1,
    HarnessArtifactResolutionStatus,
    HarnessArtifactRegistrationV1,
)
from app.persistence.harness_artifact_repository import HarnessArtifactRepository
from app.services.harness_runtime import HarnessRuntimeArtifactResolver, HarnessRuntimeResolvedArtifact


class TavernActorInputManifest(HarnessSafeManifest):
    """Trace-safe actor inputs; transcript and persona text stay protected."""

    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"mode", "room_revision", "target_ids", "anchor_present"}
    )
    mode: str
    room_revision: int
    target_ids: list[str]
    anchor_present: bool


class TavernRoomSnapshotManifest(HarnessSafeManifest):
    trace_safe_fields: ClassVar[frozenset[str]] = frozenset(
        {"room_id", "revision", "participant_ids", "context_digest"}
    )
    room_id: str
    revision: int
    participant_ids: list[str]
    context_digest: str


ACTOR_INPUT_CONTRACT = HarnessContractRef(
    name="TavernActorInputManifest", version="tavern-actor-input-manifest-v1"
)


class TavernHarnessArtifactResolver(HarnessRuntimeArtifactResolver):
    """Bridge grant based protected artifacts into shared runtime resolution."""

    def __init__(self, repository: HarnessArtifactRepository, grants: dict[str, str]):
        self.repository = repository
        self.grants = dict(grants)

    def resolve(self, *, operation_binding, context):
        resolved = []
        for ref in context.snapshot_refs:
            grant_id = self.grants.get(ref.artifact_id)
            if not grant_id:
                raise PermissionError("harness_artifact_grant_missing")
            result = self.repository.resolve(HarnessArtifactResolveRequestV1(
                grant_id=grant_id,
                harness_operation_id=operation_binding.harness_operation_id,
                artifact_id=ref.artifact_id,
                artifact_type=ref.artifact_type,
                artifact_contract=ref.contract,
                permission=HarnessArtifactPermission.READ,
            ))
            if result.status != HarnessArtifactResolutionStatus.RESOLVED:
                raise PermissionError(f"harness_artifact_resolution_{result.status.value}")
            assert result.content is not None and result.payload_digest is not None
            resolved.append(HarnessRuntimeResolvedArtifact(
                artifact_id=result.artifact_id,
                payload_digest=result.payload_digest,
                payload=result.content,
            ))
        return tuple(resolved)
TAVERN_PROTECTED_SNAPSHOT_CONTRACT = HarnessContractRef(
    name="TavernActorProtectedSnapshot",
    version="tavern-actor-protected-snapshot-v1",
)
# Compatibility alias for callers written while the protected snapshot helper
# was first introduced.
ROOM_SNAPSHOT_CONTRACT = TAVERN_PROTECTED_SNAPSHOT_CONTRACT


def serialize_tavern_protected_snapshot(
    *,
    detail: TavernRoomDetail,
    actor: TavernParticipantRecord,
    recent_messages: list[TavernMessageRecord],
    user_message: str,
    guidance: str,
) -> bytes:
    """Canonical protected replay bytes; never placed in trace-safe context."""
    payload = {
        "schema_name": "TavernActorProtectedSnapshot",
        "schema_version": "tavern-actor-protected-snapshot-v1",
        "room": detail.room.model_dump(mode="json", exclude_none=False),
        "participants": [item.model_dump(mode="json", exclude_none=False) for item in detail.participants],
        "actor_persona": actor.persona_snapshot.model_dump(mode="json", exclude_none=False),
        "recent_messages": [item.model_dump(mode="json", exclude_none=False) for item in recent_messages],
        "user_message": user_message,
        "guidance": guidance,
    }
    return json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")
    ).encode("utf-8")


def snapshot_ref_from_registration(
    registration: HarnessArtifactRegistrationV1,
) -> HarnessSnapshotRefV3:
    """Bind context to the actual opaque protected artifact registration."""
    return HarnessSnapshotRefV3(
        artifact_type=registration.artifact_type,
        artifact_id=registration.artifact_id,
        contract=registration.artifact_contract,
        payload_digest=registration.payload_digest,
    )


def build_tavern_actor_context(
    *,
    operation_binding: HarnessOperationBindingV1,
    detail: TavernRoomDetail,
    mode: str,
    target_ids: list[str],
    anchor_present: bool,
    context_digest: str,
    snapshot_ref: HarnessSnapshotRefV3,
):
    return build_harness_context(
        workflow=HarnessWorkflow.TAVERN,
        stage=HarnessStage.TAVERN_ACTOR_REPLY,
        operation_binding=operation_binding,
        input_contract=ACTOR_INPUT_CONTRACT,
        input_manifest=TavernActorInputManifest(
            mode=mode,
            room_revision=detail.room.revision,
            target_ids=sorted(target_ids),
            anchor_present=anchor_present,
        ),
        subject_refs=(
            HarnessResourceRefV3(
                resource_type="tavern_room", resource_id=detail.room.id,
                revision=detail.room.revision,
            ),
        ),
        snapshot_refs=(snapshot_ref,),
        prompt_contract=HarnessContractRef(
            name="TavernActorPrompt", version="tavern-actor-v1"
        ),
        policy_contract=HarnessContractRef(
            name="TavernHarnessPolicy", version="tavern-harness-v1"
        ),
    )


def build_tavern_actor_stage_adapter(
    *,
    actor: TavernParticipantRecord,
    participants: list[TavernParticipantRecord],
    recent_messages: list[TavernMessageRecord],
    user_message: str,
    guidance: str,
    required_target_id: str,
    allowed_target_ids: list[str],
    policy,
    generate,
    commit,
    read_back=None,
    model_recoveries: Callable[[], list] | None = None,
) -> HarnessRuntimeStageAdapter:
    """Adapt the existing Tavern semantic validator to shared runtime.

    ``generate`` is deliberately injected so the runtime owns exactly one
    provider invocation.  Commit/read-back remain injected repository
    boundaries and therefore cannot silently become a second generation path.
    """
    harness = TavernActorHarness()
    last_trace = {}

    def validate(decoded):
        if not isinstance(decoded, TavernActorReply):
            raise ValueError("tavern_actor_invalid_payload")
        try:
            reply, trace = harness.validate_and_repair(
                reply=decoded,
                actor=actor,
                participants=participants,
                recent_messages=recent_messages,
                user_message=user_message,
                guidance=guidance,
                allowed_target_ids=allowed_target_ids,
                required_target_id=required_target_id,
                policy=policy,
            )
        except TavernHarnessViolation as exc:
            checks = tuple(
                HarnessCheckV2(
                    name=item.name,
                    status=item.status,
                    code=item.code,
                    message=item.message,
                )
                for item in exc.trace.checks
            )
            raise HarnessRuntimeDomainValidationError(str(exc), checks) from exc
        if model_recoveries is not None:
            trace = harness.merge_model_recoveries(trace, model_recoveries())
        last_trace["trace"] = trace
        checks = tuple(
            HarnessCheckV2(
                name=item.name,
                status=item.status,
                code=item.code,
                message=item.message,
            )
            for item in trace.checks
        )
        return HarnessRuntimeValidationResult(
            output=reply,
            checks=checks,
            status=trace.status,
            recovery_strategy=(
                trace.recovery_strategy
                if trace.status == HarnessStatus.REPAIRED
                else "none"
            ),
        )

    def decode(raw):
        return raw if isinstance(raw, TavernActorReply) else TavernActorReply.model_validate(raw)

    return HarnessRuntimeStageAdapter(
        adapter_contract=HarnessContractRef(
            name="TavernActorWorkflowAdapter", version="tavern-actor-workflow-adapter-v1"
        ),
        trace_contract=HarnessContractRef(
            name="TavernActorReply", version="tavern-actor-reply-v2"
        ),
        generate=lambda _context, _artifacts: generate(),
        decode=decode,
        validate=validate,
        commit=commit,
        read_back=read_back,
        recovery_strategy="retry_strict_actor_reply",
    )
