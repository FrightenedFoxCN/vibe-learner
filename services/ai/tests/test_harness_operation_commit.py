from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from pydantic import ValidationError

from app.models.harness import (
    HarnessTraceV3,
    build_tavern_persona_message_commit_binding,
    canonical_harness_digest,
    validate_harness_operation_commit,
)
from app.models.tavern import (
    TavernAuthorKind,
    TavernMessageRecord,
    TavernParticipantRecord,
    TavernRunRecord,
    TavernRunStatus,
    TavernTurnResponse,
    TavernSpeakerStepRecord,
    TavernSpeakerStepStatus,
    build_tavern_persona_message_committed_projection,
)
from app.models.tavern_commit import (
    TavernPersonaMessageCommitBindingV1,
    TavernPersonaMessageCommitMetadataV1,
    TavernPersonaMessageCommittedProjectionV1,
)
from app.models.domain import PersonaProfile
from app.models.tavern_integrity import persona_prompt_hash


FIXTURE = Path(__file__).parent / "fixtures" / "harness" / "passed_not_applicable_v3.json"
OPERATION_ID = "harness-operation-11111111111111111111111111111111"
EFFECT_BATCH_ID = "effect-message-10"


def _base_trace() -> dict[str, object]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    payload["contract"] = {
        "name": "TavernActorReply",
        "version": "tavern-actor-reply-v2",
    }
    return payload


def _projection(**changes: object) -> TavernPersonaMessageCommittedProjectionV1:
    values: dict[str, object] = {
        "operation_id": OPERATION_ID,
        "effect_batch_id": EFFECT_BATCH_ID,
        "room_id": "room-1",
        "message_id": "message-10",
        "sequence": 10,
        "run_id": "run-1",
        "step_index": 0,
        "reply_to_message_id": "message-9",
        "author_kind": "persona",
        "persona_id": "persona-1",
        "persona_name": "Ada",
        "content": "We should compare the two clues.",
        "emotion": "focused",
        "action": "leans forward",
        "speech_style": "precise",
        "addressed_participant_ids": ["persona-2"],
        "client_request_id": "request-actor-1",
        "created_at": "2026-08-12T10:00:00Z",
    }
    values.update(changes)
    return TavernPersonaMessageCommittedProjectionV1.model_validate(values)


def _repository_records() -> tuple[
    TavernMessageRecord,
    TavernRunRecord,
    TavernSpeakerStepRecord,
    list[TavernParticipantRecord],
]:
    def persona(persona_id: str, name: str) -> PersonaProfile:
        return PersonaProfile(
            id=persona_id,
            name=name,
            source="manual",
            summary="careful observer",
            system_prompt="stay in character",
            available_emotions=["focused"],
            available_actions=["leans forward"],
            default_speech_style="precise",
        )

    first_persona = persona("persona-1", "Ada")
    second_persona = persona("persona-2", "Lin")
    participants = [
        TavernParticipantRecord(
            room_id="room-1",
            persona_id="persona-1",
            display_order=0,
            display_name="Ada",
            persona_snapshot=first_persona,
            prompt_hash=persona_prompt_hash(first_persona.model_dump(mode="json")),
            joined_at="2026-08-12T09:00:00Z",
        ),
        TavernParticipantRecord(
            room_id="room-1",
            persona_id="persona-2",
            display_order=1,
            display_name="Lin",
            persona_snapshot=second_persona,
            prompt_hash=persona_prompt_hash(second_persona.model_dump(mode="json")),
            joined_at="2026-08-12T09:00:00Z",
        ),
    ]
    step = TavernSpeakerStepRecord(
        run_id="run-1",
        step_index=0,
        persona_id="persona-1",
        participant_prompt_hash=participants[0].prompt_hash,
        status=TavernSpeakerStepStatus.COMPLETED,
        message_id="message-10",
        reply_to_message_id="message-9",
    )
    run = TavernRunRecord(
        id="run-1",
        room_id="room-1",
        idempotency_key="request-actor-1",
        mode="direct",
        anchor_message_id="message-9",
        scheduled_participant_ids=["persona-1"],
        speaker_steps=[step],
        status=TavernRunStatus.COMPLETED,
        expected_room_revision=4,
        generated_message_ids=["message-10"],
        terminal_sequence=10,
        created_at="2026-08-12T09:59:00Z",
    )
    message = TavernMessageRecord(
        id="message-10",
        room_id="room-1",
        sequence=10,
        run_id="run-1",
        author_kind=TavernAuthorKind.PERSONA,
        persona_id="persona-1",
        persona_name="Ada",
        content="We should compare the two clues.",
        emotion="focused",
        action="leans forward",
        speech_style="precise",
        addressed_participant_ids=["persona-2"],
        reply_to_message_id="message-9",
        client_request_id="request-actor-1",
        created_at="2026-08-12T10:00:00Z",
        commit_metadata=TavernPersonaMessageCommitMetadataV1(
            operation_id=OPERATION_ID,
            effect_batch_id=EFFECT_BATCH_ID,
        ),
    )
    return message, run, step, participants


def _reply_anchor() -> TavernMessageRecord:
    return TavernMessageRecord(
        id="message-9",
        room_id="room-1",
        sequence=9,
        run_id="run-1",
        author_kind=TavernAuthorKind.USER,
        content="What do the clues suggest?",
        created_at="2026-08-12T09:59:30Z",
    )


def _committed_trace(
    projection: TavernPersonaMessageCommittedProjectionV1,
) -> HarnessTraceV3:
    payload = _base_trace()
    digest = canonical_harness_digest(projection)
    payload["attempt_records"].append(
        {
            "attempt_id": "attempt-commit-1",
            "attempt_index": 3,
            "phase": "commit",
            "status": "passed",
            "output_digest": digest,
            "error_code": "",
            "duration_ms": 1,
        }
    )
    payload["duration_ms"] = 9
    payload["commit_evidence"] = {
        "status": "committed",
        "effect_batch_id": projection.effect_batch_id,
        "payload_contract": {
            "name": "TavernPersonaMessageCommittedProjection",
            "version": "tavern-persona-message-committed-projection-v1",
        },
        "digest_algorithm": "sha256",
        "digest_scope": "committed_projection",
        "attempted_resource_refs": [
            {
                "resource_type": "tavern_message",
                "resource_id": projection.message_id,
                "revision": None,
            }
        ],
        "committed_resources": [
            {
                "resource_type": "tavern_message",
                "resource_id": projection.message_id,
                "expected_revision": None,
                "committed_revision": None,
                "first_sequence": projection.sequence,
                "last_sequence": projection.sequence,
                "payload_digest": digest,
            }
        ],
        "payload_digest": digest,
        "committed_at": "2026-08-12T10:00:00.008Z",
        "rollback_reason_code": "",
        "rolled_back_at": None,
    }
    return HarnessTraceV3.model_validate(payload)


class HarnessOperationCommitTests(unittest.TestCase):
    def test_internal_commit_metadata_is_not_part_of_api_schema(self) -> None:
        message_schema = TavernTurnResponse.model_json_schema()["$defs"][
            "TavernMessageRecord"
        ]

        self.assertNotIn("commit_metadata", message_schema["properties"])

    def test_context_only_v3_fixture_is_not_an_adopted_actor_operation(self) -> None:
        with self.assertRaisesRegex(
            ValidationError,
            "harness_operation_commit_payload_contract_required",
        ):
            HarnessTraceV3.model_validate(_base_trace())

    def test_context_foundation_v1_fixture_remains_readable(self) -> None:
        trace = HarnessTraceV3.model_validate(
            json.loads(FIXTURE.read_text(encoding="utf-8"))
        )
        self.assertEqual(trace.contract.version, "tavern-actor-reply-v1")

    def test_actor_commit_binds_canonical_projection_and_identity(self) -> None:
        projection = _projection()
        trace = _committed_trace(projection)
        binding = build_tavern_persona_message_commit_binding(projection)
        message, run, step, participants = _repository_records()

        validated = validate_harness_operation_commit(
            trace,
            binding,
            message=message,
            run=run,
            step=step,
            participants=participants,
            reply_anchor=_reply_anchor(),
        )

        self.assertEqual(validated, projection)
        self.assertEqual(binding.projection_digest, canonical_harness_digest(projection))
        self.assertNotIn("content", TavernPersonaMessageCommitBindingV1.model_fields)

    def test_actor_commit_preserves_existing_idempotency_key_character_set(self) -> None:
        request_id = "request actor/1"
        message, run, step, participants = _repository_records()
        message = message.model_copy(update={"client_request_id": request_id})
        run = run.model_copy(update={"idempotency_key": request_id})
        projection = build_tavern_persona_message_committed_projection(
            message=message,
            run=run,
            step=step,
            participants=participants,
            reply_anchor=_reply_anchor(),
        )
        trace = _committed_trace(projection)
        binding = build_tavern_persona_message_commit_binding(projection)

        validated = validate_harness_operation_commit(
            trace,
            binding,
            message=message,
            run=run,
            step=step,
            participants=participants,
            reply_anchor=_reply_anchor(),
        )

        self.assertEqual(validated.client_request_id, request_id)

    def test_actor_commit_rejects_contract_resource_and_scope_forgery(self) -> None:
        projection = _projection()
        binding = build_tavern_persona_message_commit_binding(projection)
        trace = _committed_trace(projection).model_dump(mode="json")
        cases = []
        wrong_version = deepcopy(trace)
        wrong_version["commit_evidence"]["payload_contract"]["version"] = "wrong-v1"
        cases.append((wrong_version, "harness_operation_commit_policy_unregistered"))
        extra_room = deepcopy(trace)
        extra_room["commit_evidence"]["attempted_resource_refs"].append(
            {"resource_type": "tavern_room", "resource_id": "room-1", "revision": 4}
        )
        extra_room["commit_evidence"]["attempted_resource_refs"].sort(
            key=lambda item: (item["resource_type"], item["resource_id"])
        )
        extra_room["commit_evidence"]["committed_resources"].append(
            {
                "resource_type": "tavern_room",
                "resource_id": "room-1",
                "expected_revision": 4,
                "committed_revision": 5,
                "first_sequence": None,
                "last_sequence": None,
                "payload_digest": "a" * 64,
            }
        )
        extra_room["commit_evidence"]["committed_resources"].sort(
            key=lambda item: (item["resource_type"], item["resource_id"])
        )
        cases.append((extra_room, "harness_projection_digest_requires_single_resource"))
        wrong_scope = deepcopy(trace)
        wrong_scope["commit_evidence"]["digest_scope"] = "committed_batch"
        cases.append((wrong_scope, "harness_batch_manifest_digest_mismatch"))

        for payload, error in cases:
            with self.subTest(error=error):
                with self.assertRaisesRegex(ValidationError, error):
                    HarnessTraceV3.model_validate(payload)

        wrong_trace_contract = deepcopy(trace)
        wrong_trace_contract["contract"] = {
            "name": "TavernActorReply",
            "version": "tavern-actor-reply-v9",
        }
        with self.assertRaisesRegex(
            ValidationError,
            "harness_operation_commit_policy_unregistered",
        ):
            HarnessTraceV3.model_validate(wrong_trace_contract)

    def test_sidecar_rejects_cross_operation_room_and_projection_forgery(self) -> None:
        projection = _projection()
        trace = _committed_trace(projection)
        binding = build_tavern_persona_message_commit_binding(projection)
        message, run, step, participants = _repository_records()
        for forged_binding in (
            binding.model_copy(
                update={
                    "operation_id": (
                        "harness-operation-22222222222222222222222222222222"
                    )
                }
            ),
            binding.model_copy(update={"room_id": "room-2"}),
            binding.model_copy(update={"run_id": "run-2"}),
            binding.model_copy(update={"step_index": 1}),
            binding.model_copy(update={"reply_to_message_id": "message-8"}),
            binding.model_copy(update={"persona_id": "persona-2"}),
        ):
            with self.assertRaises(ValueError):
                validate_harness_operation_commit(
                    trace,
                    forged_binding,
                    message=message,
                    run=run,
                    step=step,
                    participants=participants,
                    reply_anchor=_reply_anchor(),
                )

    def test_sidecar_rejects_fully_rehashed_self_consistent_forgery(self) -> None:
        authoritative = _projection()
        forged = _projection(
            run_id="run-2",
            step_index=1,
            reply_to_message_id="message-8",
            persona_id="persona-2",
            persona_name="Lin",
        )
        forged_trace = _committed_trace(forged)
        forged_binding = build_tavern_persona_message_commit_binding(forged)
        message, run, step, participants = _repository_records()

        with self.assertRaisesRegex(
            ValueError,
            "harness_operation_commit_binding_projection_mismatch",
        ):
            validate_harness_operation_commit(
                forged_trace,
                forged_binding,
                message=message,
                run=run,
                step=step,
                participants=participants,
                reply_anchor=_reply_anchor(),
            )
        self.assertNotEqual(
            forged_binding,
            build_tavern_persona_message_commit_binding(authoritative),
        )

    def test_sidecar_rejects_rebound_persisted_operation_and_effect_batch(self) -> None:
        projection = _projection()
        message, run, step, participants = _repository_records()
        rebound = _projection(
            operation_id="harness-operation-22222222222222222222222222222222",
            effect_batch_id="effect-message-10-rebound",
        )

        with self.assertRaisesRegex(
            ValueError,
            "harness_operation_commit_binding_projection_mismatch",
        ):
            validate_harness_operation_commit(
                _committed_trace(rebound),
                build_tavern_persona_message_commit_binding(rebound),
                message=message,
                run=run,
                step=step,
                participants=participants,
                reply_anchor=_reply_anchor(),
            )

        trace_payload = _committed_trace(projection).model_dump(mode="json")
        trace_payload["commit_evidence"]["effect_batch_id"] = "effect-message-10-forged"
        forged_effect_trace = HarnessTraceV3.model_validate(trace_payload)
        with self.assertRaisesRegex(
            ValueError,
            "harness_operation_commit_binding_effect_batch_mismatch",
        ):
            validate_harness_operation_commit(
                forged_effect_trace,
                build_tavern_persona_message_commit_binding(projection),
                message=message,
                run=run,
                step=step,
                participants=participants,
                reply_anchor=_reply_anchor(),
            )

    def test_actor_failed_and_skipped_cannot_escape_registered_policy(self) -> None:
        failed = _base_trace()
        failed["status"] = "failed"
        failed["output_digest"] = None
        failed["attempt_records"][-1] = {
            "attempt_id": "attempt-validate-1",
            "attempt_index": 2,
            "phase": "validate",
            "status": "failed",
            "output_digest": None,
            "error_code": "actor_validation_failed",
            "duration_ms": 1,
        }
        failed["attempt_records"].append(
            {
                "attempt_id": "attempt-commit-1",
                "attempt_index": 3,
                "phase": "commit",
                "status": "failed",
                "output_digest": None,
                "error_code": "commit_not_attempted",
                "duration_ms": 0,
            }
        )
        failed["error_code"] = "actor_validation_failed"
        failed["commit_evidence"] = {
            "status": "not_committed",
            "effect_batch_id": "effect-message-attempt-1",
            "payload_contract": {
                "name": "TavernPersonaMessageCommittedProjection",
                "version": "tavern-persona-message-committed-projection-v1",
            },
            "digest_algorithm": "sha256",
            "digest_scope": "committed_projection",
            "attempted_resource_refs": [
                {
                    "resource_type": "tavern_message",
                    "resource_id": "message-attempt-1",
                    "revision": None,
                }
            ],
            "committed_resources": [],
            "payload_digest": None,
            "committed_at": None,
            "rollback_reason_code": "",
            "rolled_back_at": None,
        }
        self.assertEqual(
            HarnessTraceV3.model_validate(failed).commit_evidence.status.value,
            "not_committed",
        )

        missing_policy_metadata = deepcopy(failed)
        missing_policy_metadata["commit_evidence"] = {
            "status": "not_committed",
            "effect_batch_id": None,
            "payload_contract": None,
            "digest_algorithm": None,
            "digest_scope": None,
            "attempted_resource_refs": [],
            "committed_resources": [],
            "payload_digest": None,
            "committed_at": None,
            "rollback_reason_code": "",
            "rolled_back_at": None,
        }
        with self.assertRaisesRegex(
            ValidationError,
            "harness_not_committed_attempt_evidence_missing",
        ):
            HarnessTraceV3.model_validate(missing_policy_metadata)

        skipped = json.loads(FIXTURE.read_text(encoding="utf-8"))
        skipped["contract"] = {
            "name": "TavernActorReply",
            "version": "tavern-actor-reply-v2",
        }
        skipped["status"] = "skipped"
        skipped["output_digest"] = None
        skipped["attempt_records"] = [
            {
                "attempt_id": "attempt-generate-1",
                "attempt_index": 1,
                "phase": "generate",
                "status": "skipped",
                "output_digest": None,
                "error_code": "",
                "duration_ms": 0,
            }
        ]
        skipped["duration_ms"] = 0
        with self.assertRaisesRegex(
            ValidationError,
            "harness_operation_commit_payload_contract_required",
        ):
            HarnessTraceV3.model_validate(skipped)

    def test_projection_and_binding_model_construct_bypasses_are_revalidated(self) -> None:
        projection = _projection()
        trace = _committed_trace(projection)
        binding = build_tavern_persona_message_commit_binding(projection)
        message, run, step, participants = _repository_records()
        malformed_binding = TavernPersonaMessageCommitBindingV1.model_construct(
            **{
                **binding.model_dump(mode="python"),
                "projection_digest": "not-a-digest",
            }
        )
        with self.assertRaises(ValidationError):
            validate_harness_operation_commit(
                trace,
                malformed_binding,
                message=message,
                run=run,
                step=step,
                participants=participants,
                reply_anchor=_reply_anchor(),
            )

    def test_repository_projection_builder_rejects_cross_graph_records(self) -> None:
        message, run, step, participants = _repository_records()
        projection = build_tavern_persona_message_committed_projection(
            message=message,
            run=run,
            step=step,
            participants=participants,
            reply_anchor=_reply_anchor(),
        )
        self.assertEqual(projection.message_id, message.id)

        for forged_step in (
            step.model_copy(update={"run_id": "run-2"}),
            step.model_copy(update={"message_id": "message-11"}),
            step.model_copy(update={"persona_id": "persona-2"}),
            step.model_copy(update={"reply_to_message_id": "message-8"}),
            step.model_copy(update={"participant_prompt_hash": "hash-forged"}),
        ):
            with self.assertRaises(ValueError):
                build_tavern_persona_message_committed_projection(
                    message=message,
                    run=run,
                    step=forged_step,
                    participants=participants,
                    reply_anchor=_reply_anchor(),
                )

    def test_repository_projection_rejects_roster_and_anchor_forgery(self) -> None:
        message, run, step, participants = _repository_records()
        foreign_persona = participants[1].model_copy(
            update={"room_id": "room-2"},
        )
        snapshot_tampered = participants[0].model_copy(deep=True)
        snapshot_tampered.persona_snapshot.summary = "tampered after snapshot"
        identity_tampered = participants[0].model_copy(deep=True)
        identity_tampered.persona_snapshot.id = "persona-foreign"

        participant_cases = (
            [snapshot_tampered, participants[1]],
            [identity_tampered, participants[1]],
            [participants[0], foreign_persona],
        )
        for forged_participants in participant_cases:
            with self.subTest(participants=forged_participants):
                with self.assertRaises(ValueError):
                    build_tavern_persona_message_committed_projection(
                        message=message,
                        run=run,
                        step=step,
                        participants=forged_participants,
                        reply_anchor=_reply_anchor(),
                    )

        schedule_cases = (
            run.model_copy(
                update={
                    "scheduled_participant_ids": ["persona-1", "persona-1"],
                    "speaker_steps": [
                        step,
                        step.model_copy(update={"step_index": 1}),
                    ],
                }
            ),
            run.model_copy(
                update={
                    "scheduled_participant_ids": ["persona-1", "persona-foreign"],
                    "speaker_steps": [
                        step,
                        step.model_copy(
                            update={
                                "step_index": 1,
                                "persona_id": "persona-foreign",
                            }
                        ),
                    ],
                }
            ),
        )
        for forged_run in schedule_cases:
            with self.subTest(schedule=forged_run.scheduled_participant_ids):
                with self.assertRaises(ValueError):
                    build_tavern_persona_message_committed_projection(
                        message=message,
                        run=forged_run,
                        step=step,
                        participants=participants,
                        reply_anchor=_reply_anchor(),
                    )

        anchor_cases = (
            _reply_anchor().model_copy(update={"room_id": "room-2"}),
            _reply_anchor().model_copy(update={"sequence": message.sequence}),
            _reply_anchor().model_copy(update={"id": "message-foreign"}),
        )
        for forged_anchor in anchor_cases:
            with self.subTest(anchor=forged_anchor):
                with self.assertRaises(ValueError):
                    build_tavern_persona_message_committed_projection(
                        message=message,
                        run=run,
                        step=step,
                        participants=participants,
                        reply_anchor=forged_anchor,
                    )

    def test_repository_projection_revalidates_constructed_commit_metadata(self) -> None:
        message, run, step, participants = _repository_records()
        message = message.model_copy(
            update={
                "commit_metadata": TavernPersonaMessageCommitMetadataV1.model_construct(
                    operation_id="not-an-operation",
                    effect_batch_id=EFFECT_BATCH_ID,
                )
            }
        )

        with self.assertRaises(ValidationError):
            build_tavern_persona_message_committed_projection(
                message=message,
                run=run,
                step=step,
                participants=participants,
                reply_anchor=_reply_anchor(),
            )


if __name__ == "__main__":
    unittest.main()
