"""Small, production-safe v3 context helpers for Tavern actor stages."""
from __future__ import annotations

from typing import Callable, ClassVar, Literal
import json

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.models.harness import (
    HarnessArtifactType,
    HarnessContractRef,
    HarnessResourceRefV3,
    HarnessSnapshotRefV3,
    HarnessSafeManifest,
    HarnessStage,
    HarnessWorkflow,
    HarnessStatus,
    HarnessCheckStatus,
)
from app.models.tavern import (
    TavernRoomDetail,
    TavernRoomRecord,
    TavernRunStatus,
    TavernSpeakerStepRecord,
    TavernSpeakerStepStatus,
)
from app.models.tavern_integrity import persona_prompt_hash
from app.models.harness_operation import HarnessOperationBindingV1
from app.services.harness_context import build_harness_context
from app.models.harness import HarnessCheckV2
from app.services.harness_runtime import (
    HarnessRuntimeDomainValidationError,
    HarnessRuntimeStageAdapter,
    HarnessRuntimeValidationResult,
)
from app.services.tavern_harness import TavernActorHarness, TavernHarnessViolation
from app.services.tavern_prompt import TavernPromptBudgetReport
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


class TavernActorProtectedSnapshotV2(BaseModel):
    """Strict decoded form of the operation-authorized Tavern actor input."""

    model_config = ConfigDict(extra="forbid", strict=True)

    schema_name: Literal["TavernActorProtectedSnapshot"]
    schema_version: Literal["tavern-actor-protected-snapshot-v2"]
    run_id: str = Field(min_length=1)
    run_context_digest: str = Field(pattern=r"^[0-9a-f]{16}$")
    scheduled_participant_ids: list[str] = Field(min_length=1, max_length=4)
    step_index: int = Field(ge=0, le=3)
    room: TavernRoomRecord
    participants: list[TavernParticipantRecord] = Field(min_length=1, max_length=6)
    actor: TavernParticipantRecord
    recent_messages: list[TavernMessageRecord]
    transcript_last_sequence: int = Field(ge=0)
    user_message: str
    guidance: str
    turn_kind: Literal["user_message", "continue", "retry"]
    required_target_id: str
    reply_anchor: TavernMessageRecord

    @model_validator(mode="after")
    def validate_snapshot_integrity(self) -> "TavernActorProtectedSnapshotV2":
        participant_ids = [item.persona_id for item in self.participants]
        display_orders = [item.display_order for item in self.participants]
        if len(participant_ids) != len(set(participant_ids)):
            raise ValueError("tavern_snapshot_participant_duplicate")
        if len(self.scheduled_participant_ids) != len(
            set(self.scheduled_participant_ids)
        ):
            raise ValueError("tavern_snapshot_schedule_duplicate")
        if len(display_orders) != len(set(display_orders)):
            raise ValueError("tavern_snapshot_display_order_duplicate")
        if display_orders != sorted(display_orders):
            raise ValueError("tavern_snapshot_participants_not_ordered")
        participant_order = {
            item.persona_id: item.display_order for item in self.participants
        }
        if any(
            item not in participant_order for item in self.scheduled_participant_ids
        ):
            raise ValueError("tavern_snapshot_scheduled_participant_missing")
        if self.scheduled_participant_ids != sorted(
            self.scheduled_participant_ids,
            key=participant_order.__getitem__,
        ):
            raise ValueError("tavern_snapshot_schedule_not_roster_ordered")
        for participant in self.participants:
            if participant.room_id != self.room.id:
                raise ValueError("tavern_snapshot_participant_room_mismatch")
            if participant.persona_snapshot.id != participant.persona_id:
                raise ValueError("tavern_snapshot_participant_persona_id_mismatch")
            if participant.display_name != participant.persona_snapshot.name:
                raise ValueError("tavern_snapshot_participant_display_name_mismatch")
            expected_hash = persona_prompt_hash(
                participant.persona_snapshot.model_dump(mode="json")
            )
            if participant.prompt_hash != expected_hash:
                raise ValueError("tavern_snapshot_participant_prompt_hash_mismatch")

        message_ids = [item.id for item in self.recent_messages]
        sequences = [item.sequence for item in self.recent_messages]
        if len(message_ids) != len(set(message_ids)):
            raise ValueError("tavern_snapshot_message_duplicate")
        if len(sequences) != len(set(sequences)):
            raise ValueError("tavern_snapshot_message_sequence_duplicate")
        if sequences != sorted(sequences):
            raise ValueError("tavern_snapshot_messages_not_ordered")
        if self.transcript_last_sequence != self.room.last_sequence:
            raise ValueError("tavern_snapshot_transcript_sequence_mismatch")
        if any(item.room_id != self.room.id for item in self.recent_messages):
            raise ValueError("tavern_snapshot_message_room_or_sequence_mismatch")
        if sequences and sequences[-1] > self.transcript_last_sequence:
            raise ValueError("tavern_snapshot_message_room_or_sequence_mismatch")

        if self.actor not in self.participants:
            raise ValueError("tavern_snapshot_actor_participant_mismatch")
        if self.actor.persona_id not in self.scheduled_participant_ids:
            raise ValueError("tavern_snapshot_actor_not_scheduled")
        if self.step_index >= len(self.scheduled_participant_ids):
            raise ValueError("tavern_snapshot_step_schedule_mismatch")
        if self.scheduled_participant_ids[self.step_index] != self.actor.persona_id:
            raise ValueError("tavern_snapshot_step_schedule_mismatch")

        if self.reply_anchor.room_id != self.room.id:
            raise ValueError("tavern_snapshot_reply_anchor_room_mismatch")
        if self.reply_anchor.sequence > self.transcript_last_sequence:
            raise ValueError("tavern_snapshot_reply_anchor_sequence_mismatch")
        if self.reply_anchor.author_kind.value == "persona":
            anchor_participant = next(
                (
                    item
                    for item in self.participants
                    if item.persona_id == self.reply_anchor.persona_id
                ),
                None,
            )
            if (
                anchor_participant is None
                or self.reply_anchor.persona_name != anchor_participant.display_name
            ):
                raise ValueError("tavern_snapshot_reply_anchor_persona_mismatch")
            if self.reply_anchor not in self.recent_messages:
                raise ValueError("tavern_snapshot_persona_anchor_missing_from_transcript")
            derived_target_id = (
                self.reply_anchor.persona_id
                if self.reply_anchor.persona_id != self.actor.persona_id
                else ""
            )
        else:
            derived_target_id = ""
        if self.required_target_id != derived_target_id:
            raise ValueError("tavern_snapshot_required_target_binding_mismatch")
        if (
            self.required_target_id
            and self.required_target_id not in participant_ids
        ):
            raise ValueError("tavern_snapshot_required_target_missing")
        if self.turn_kind == "user_message" and self.step_index == 0:
            if (
                self.reply_anchor.author_kind.value != "user"
                or self.reply_anchor.content != self.user_message
                or self.reply_anchor.sequence != self.transcript_last_sequence
            ):
                raise ValueError("tavern_snapshot_user_anchor_mismatch")
        if self.turn_kind == "continue" and self.user_message:
            raise ValueError("tavern_snapshot_continue_user_message_present")
        return self


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
        requests = []
        for ref in context.snapshot_refs:
            grant_id = self.grants.get(ref.artifact_id)
            if not grant_id:
                raise PermissionError("harness_artifact_grant_missing")
            requests.append(HarnessArtifactResolveRequestV1(
                grant_id=grant_id,
                harness_operation_id=operation_binding.harness_operation_id,
                artifact_id=ref.artifact_id,
                artifact_type=ref.artifact_type,
                artifact_contract=ref.contract,
                permission=HarnessArtifactPermission.READ,
            ))
        if not requests:
            return ()
        for result in self.repository.resolve_batch(requests).results:
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
    version="tavern-actor-protected-snapshot-v2",
)
# Compatibility alias for callers written while the protected snapshot helper
# was first introduced.
ROOM_SNAPSHOT_CONTRACT = TAVERN_PROTECTED_SNAPSHOT_CONTRACT


def serialize_tavern_protected_snapshot(
    snapshot: TavernActorProtectedSnapshotV2,
) -> bytes:
    """Canonical protected replay bytes; never placed in trace-safe context."""
    return json.dumps(
        snapshot.model_dump(mode="json", exclude_none=False),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def decode_tavern_protected_snapshot(payload: object) -> TavernActorProtectedSnapshotV2:
    """Fail closed before provider work unless the resolved bytes are canonical v2."""

    if not isinstance(payload, bytes):
        raise ValueError("tavern_snapshot_bytes_required")
    try:
        decoded = json.loads(payload.decode("utf-8"))
        snapshot = TavernActorProtectedSnapshotV2.model_validate(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError, ValidationError) as exc:
        raise ValueError("tavern_snapshot_payload_invalid") from exc
    canonical = json.dumps(
        snapshot.model_dump(mode="json", exclude_none=False),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    if canonical != payload:
        raise ValueError("tavern_snapshot_noncanonical_payload")
    return snapshot


def require_authorized_message_suffix(
    *,
    authorized_messages: list[TavernMessageRecord],
    candidate_messages: object,
) -> list[TavernMessageRecord]:
    """Allow prompt budgeting to drop only the oldest authorized messages."""

    if not isinstance(candidate_messages, list) or any(
        not isinstance(item, TavernMessageRecord) for item in candidate_messages
    ):
        raise ValueError("tavern_snapshot_validation_messages_invalid")
    if candidate_messages and candidate_messages != authorized_messages[-len(candidate_messages):]:
        raise ValueError("tavern_snapshot_validation_messages_not_suffix")
    return list(candidate_messages)


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
    snapshot_artifact_id: str,
    expected_snapshot: TavernActorProtectedSnapshotV2,
    authoritative_context_digest: str,
    expected_run_status: TavernRunStatus,
    claimed_step: TavernSpeakerStepRecord,
    expected_claim_count: int,
    expected_step_prompt_hash: str,
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
    authorized: dict[str, object] = {}

    def generate_from_resolved_snapshot(context, artifacts):
        if set(artifacts) != {snapshot_artifact_id}:
            raise ValueError("tavern_snapshot_artifact_set_mismatch")
        snapshot = decode_tavern_protected_snapshot(artifacts[snapshot_artifact_id])
        if snapshot.model_dump(
            mode="json", exclude_none=False
        ) != expected_snapshot.model_dump(mode="json", exclude_none=False):
            raise ValueError("tavern_snapshot_authoritative_projection_mismatch")
        if snapshot.run_context_digest != authoritative_context_digest:
            raise ValueError("tavern_snapshot_run_context_digest_mismatch")
        if expected_run_status != TavernRunStatus.PENDING:
            raise ValueError("tavern_snapshot_run_not_pending")
        if (
            claimed_step.run_id != snapshot.run_id
            or claimed_step.status != TavernSpeakerStepStatus.GENERATING
            or claimed_step.claim_count != expected_claim_count
            or claimed_step.step_index != snapshot.step_index
            or claimed_step.persona_id != snapshot.actor.persona_id
        ):
            raise ValueError("tavern_snapshot_step_identity_mismatch")
        if claimed_step.reply_to_message_id != snapshot.reply_anchor.id:
            raise ValueError("tavern_snapshot_step_reply_anchor_mismatch")
        if snapshot.reply_anchor.sequence != snapshot.transcript_last_sequence:
            raise ValueError("tavern_snapshot_reply_anchor_not_transcript_tail")
        if (
            claimed_step.participant_prompt_hash != expected_step_prompt_hash
            or snapshot.actor.prompt_hash != expected_step_prompt_hash
        ):
            raise ValueError("tavern_snapshot_step_prompt_hash_mismatch")
        if (
            not snapshot.run_context_digest
            or not any(
                ref.resource_type == "tavern_room"
                and ref.resource_id == snapshot.room.id
                and ref.revision == snapshot.room.revision
                for ref in context.subject_refs
            )
        ):
            raise ValueError("tavern_snapshot_room_binding_mismatch")
        raw, validation_messages, prompt_budget_report = generate(
            snapshot, snapshot.actor
        )
        if not isinstance(prompt_budget_report, TavernPromptBudgetReport):
            raise ValueError("tavern_snapshot_prompt_budget_report_missing")
        validation_messages = require_authorized_message_suffix(
            authorized_messages=snapshot.recent_messages,
            candidate_messages=validation_messages,
        )
        authorized.update(
            snapshot=snapshot,
            actor=snapshot.actor,
            validation_messages=list(validation_messages),
            prompt_budget_report=prompt_budget_report,
        )
        return raw

    def validate(decoded):
        if not isinstance(decoded, TavernActorReply):
            raise ValueError("tavern_actor_invalid_payload")
        snapshot = authorized.get("snapshot")
        actor = authorized.get("actor")
        validation_messages = authorized.get("validation_messages")
        prompt_budget_report = authorized.get("prompt_budget_report")
        if (
            not isinstance(snapshot, TavernActorProtectedSnapshotV2)
            or not isinstance(actor, TavernParticipantRecord)
            or not isinstance(validation_messages, list)
            or not isinstance(prompt_budget_report, TavernPromptBudgetReport)
        ):
            raise ValueError("tavern_snapshot_not_authorized_for_validation")
        try:
            reply, trace = harness.validate_and_repair(
                reply=decoded,
                actor=actor,
                participants=snapshot.participants,
                recent_messages=validation_messages,
                user_message=snapshot.user_message,
                guidance=snapshot.guidance,
                allowed_target_ids=[
                    item.persona_id for item in snapshot.participants
                ],
                required_target_id=snapshot.required_target_id,
                policy=snapshot.room.harness_policy,
            )
        except TavernHarnessViolation as exc:
            failure_trace = harness.merge_prompt_budget_report(
                exc.trace,
                prompt_budget_report,
            )
            checks = tuple(
                HarnessCheckV2(
                    name=item.name,
                    status=item.status,
                    code=item.code,
                    message=item.message,
                )
                for item in failure_trace.checks
            )
            raise HarnessRuntimeDomainValidationError(str(exc), checks) from exc
        trace = harness.merge_prompt_budget_report(trace, prompt_budget_report)
        if model_recoveries is not None:
            trace = harness.merge_model_recoveries(trace, model_recoveries())
        last_trace["trace"] = trace
        checks = (
            HarnessCheckV2(
                name="authorized_snapshot_binding",
                status=HarnessCheckStatus.PASSED,
                code="tavern_authorized_snapshot_binding_valid",
                message="Resolved Tavern snapshot matched the authoritative Run and Speaker Step projection.",
            ),
        ) + tuple(
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
            name="TavernActorWorkflowAdapter", version="tavern-actor-workflow-adapter-v2"
        ),
        trace_contract=HarnessContractRef(
            name="TavernActorReply", version="tavern-actor-reply-v2"
        ),
        generate=generate_from_resolved_snapshot,
        decode=decode,
        validate=validate,
        commit=commit,
        read_back=read_back,
        recovery_strategy="retry_strict_actor_reply",
    )
