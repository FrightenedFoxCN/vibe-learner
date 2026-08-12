from __future__ import annotations

import hashlib
import json
import re
import time

from app.models.harness import (
    HarnessCheckRecord,
    HarnessCheckStatus,
    HarnessStatus,
    HarnessTraceRecord,
)
from app.models.domain import ModelRecoveryRecord
from app.models.tavern import (
    TavernActorReply,
    TavernHarnessPolicy,
    TavernMessageRecord,
    TavernParticipantRecord,
)
from app.services.tavern_prompt import TAVERN_ACTOR_PROMPT_VERSION


class TavernActorHarness:
    def validate_and_repair(
        self,
        *,
        reply: TavernActorReply,
        actor: TavernParticipantRecord,
        participants: list[TavernParticipantRecord],
        recent_messages: list[TavernMessageRecord],
        user_message: str,
        guidance: str,
        allowed_target_ids: list[str],
        policy: TavernHarnessPolicy,
        required_target_id: str = "",
    ) -> tuple[TavernActorReply, HarnessTraceRecord]:
        started_at = time.perf_counter()
        input_digest = _digest({"user_message": user_message, "guidance": guidance})
        context_digest = _digest(
            {
                "actor_id": actor.persona_id,
                "prompt_hash": actor.prompt_hash,
                "participant_ids": [item.persona_id for item in participants],
                "message_ids": [item.id for item in recent_messages],
            }
        )
        original_text = reply.text.strip()
        repaired_text = original_text
        repaired_targets = list(reply.addressed_participant_ids)
        recovery_steps: list[str] = []
        checks: list[HarnessCheckRecord] = []

        own_prefix = re.compile(
            rf"^\s*{re.escape(actor.display_name)}\s*[:：]\s*",
            re.IGNORECASE,
        )
        if own_prefix.search(repaired_text):
            repaired_text = own_prefix.sub("", repaired_text, count=1).strip()
            recovery_steps.append("strip_self_prefix")

        impersonated_id = ""
        if policy.prevent_speaker_impersonation:
            for other in participants:
                if other.persona_id == actor.persona_id:
                    continue
                match = re.search(
                    rf"(?m)^\s*{re.escape(other.display_name)}\s*[:：]",
                    repaired_text,
                    re.IGNORECASE,
                )
                if match is not None:
                    impersonated_id = other.persona_id
                    repaired_text = repaired_text[: match.start()].rstrip()
                    recovery_steps.append("truncate_cross_speaker_content")
                    break
        checks.append(
            HarnessCheckRecord(
                name="speaker_identity",
                status=(
                    HarnessCheckStatus.WARNING
                    if impersonated_id
                    else HarnessCheckStatus.PASSED
                ),
                code=(
                    f"cross_speaker_impersonation:{impersonated_id}"
                    if impersonated_id
                    else ""
                ),
                message=("已截断其他角色署名后的内容。" if impersonated_id else "说话者归属有效。"),
            )
        )

        allowed = set(allowed_target_ids)
        invalid_targets = [item for item in repaired_targets if item not in allowed]
        if invalid_targets:
            repaired_targets = [item for item in repaired_targets if item in allowed]
            recovery_steps.append("filter_invalid_targets")
        missing_required_target = bool(
            required_target_id and required_target_id not in repaired_targets
        )
        if missing_required_target:
            repaired_targets.append(required_target_id)
            recovery_steps.append("restore_scheduled_reply_target")
        checks.append(
            HarnessCheckRecord(
                name="addressed_participants",
                status=(
                    HarnessCheckStatus.WARNING
                    if invalid_targets or missing_required_target
                    else HarnessCheckStatus.PASSED
                ),
                code=(
                    f"invalid_target:{invalid_targets[0]}"
                    if invalid_targets
                    else "scheduled_reply_target_restored"
                    if missing_required_target
                    else ""
                ),
                message=(
                    "已移除不在房间中的回应目标。"
                    if invalid_targets
                    else "已恢复服务端安排的上一位说话者目标。"
                    if missing_required_target
                    else "回应目标有效。"
                ),
            )
        )

        if len(repaired_text) > policy.max_reply_characters:
            repaired_text = repaired_text[: policy.max_reply_characters].rstrip() + "…"
            recovery_steps.append("truncate_reply")
            length_status = HarnessCheckStatus.WARNING
        else:
            length_status = HarnessCheckStatus.PASSED
        checks.append(
            HarnessCheckRecord(
                name="reply_length",
                status=length_status,
                code="reply_too_long" if length_status == HarnessCheckStatus.WARNING else "",
                message="回复长度已限制。" if length_status == HarnessCheckStatus.WARNING else "回复长度有效。",
            )
        )

        prompt_material_pattern = re.compile(
            r"(?:系统提示|system\s+prompt|ACTOR_REPLY_SCHEMA|PERSONA_INSTRUCTION|<\/?system>)",
            re.IGNORECASE,
        )
        visible_fields = {
            "text": repaired_text,
            "mood": reply.mood,
            "action": reply.action,
            "speech_style": reply.speech_style,
        }
        leaked_field = next(
            (
                field_name
                for field_name, value in visible_fields.items()
                if prompt_material_pattern.search(value)
            ),
            "",
        )
        leaked_prompt = bool(leaked_field)
        normalized_guidance = guidance.strip()
        leaked_guidance = bool(
            len(normalized_guidance) >= 12
            and any(normalized_guidance in value for value in visible_fields.values())
        )
        checks.append(
            HarnessCheckRecord(
                name="prompt_confidentiality",
                status=(
                    HarnessCheckStatus.FAILED
                    if leaked_prompt or leaked_guidance
                    else HarnessCheckStatus.PASSED
                ),
                code=(
                    f"prompt_material_leak:{leaked_field}"
                    if leaked_prompt
                    else "stage_guidance_leak"
                    if leaked_guidance
                    else ""
                ),
                message=(
                    "检测到可展示字段泄漏内部提示材料。"
                    if leaked_prompt
                    else "检测到角色逐字复述本轮舞台引导。"
                    if leaked_guidance
                    else "未检测到内部提示材料泄漏。"
                ),
            )
        )

        empty_reply = not repaired_text.strip()
        checks.append(
            HarnessCheckRecord(
                name="non_empty_reply",
                status=(HarnessCheckStatus.FAILED if empty_reply else HarnessCheckStatus.PASSED),
                code="empty_reply_after_repair" if empty_reply else "",
                message="修复后回复为空。" if empty_reply else "回复包含可展示内容。",
            )
        )
        failed = leaked_prompt or leaked_guidance or empty_reply
        trace = HarnessTraceRecord(
            version=f"{policy.version}/{TAVERN_ACTOR_PROMPT_VERSION}",
            workflow="tavern",
            stage="actor_reply",
            status=(
                HarnessStatus.FAILED
                if failed
                else HarnessStatus.REPAIRED
                if recovery_steps
                else HarnessStatus.PASSED
            ),
            schema_name="TavernActorReply",
            input_digest=input_digest,
            context_digest=context_digest,
            checks=checks,
            attempts=2 if recovery_steps else 1,
            recovery_strategy="+".join(recovery_steps) if recovery_steps else "none",
            duration_ms=max(0, int((time.perf_counter() - started_at) * 1000)),
        )
        if failed:
            raise TavernHarnessViolation(trace)
        repaired = TavernActorReply(
            text=repaired_text,
            mood=reply.mood,
            action=reply.action or "微微颔首，目光停在对话者身上",
            speech_style=reply.speech_style or actor.persona_snapshot.default_speech_style,
            delivery_cue=reply.delivery_cue,
            state_commentary=reply.state_commentary,
            addressed_participant_ids=repaired_targets,
        )
        return repaired, trace

    def merge_model_recoveries(
        self,
        trace: HarnessTraceRecord,
        recoveries: list[ModelRecoveryRecord],
    ) -> HarnessTraceRecord:
        if not recoveries:
            return trace
        merged = trace.model_copy(deep=True)
        merged.status = (
            HarnessStatus.FAILED
            if trace.status == HarnessStatus.FAILED
            else HarnessStatus.REPAIRED
        )
        merged.attempts = min(
            3,
            max(
                trace.attempts,
                1 + len(recoveries),
                *(item.attempts for item in recoveries),
            ),
        )
        strategies = [
            item
            for item in trace.recovery_strategy.split("+")
            if item and item != "none"
        ]
        strategies.extend(item.strategy for item in recoveries)
        merged.recovery_strategy = "+".join(dict.fromkeys(strategies)) or "none"
        merged.checks.extend(
            HarnessCheckRecord(
                name="model_recovery",
                status=HarnessCheckStatus.WARNING,
                code=f"{item.category}:{item.reason}",
                message=f"模型输出通过 {item.strategy} 完成有界恢复。",
            )
            for item in recoveries
        )
        return merged

    def build_failure_trace(
        self,
        *,
        stage: str,
        error_code: str,
        actor: TavernParticipantRecord,
        participants: list[TavernParticipantRecord],
        recent_messages: list[TavernMessageRecord],
        user_message: str,
        guidance: str,
        policy: TavernHarnessPolicy,
        recoveries: list[ModelRecoveryRecord],
        duration_ms: int = 0,
    ) -> HarnessTraceRecord:
        trace = HarnessTraceRecord(
            version=f"{policy.version}/{TAVERN_ACTOR_PROMPT_VERSION}",
            workflow="tavern",
            stage=stage,
            status=HarnessStatus.FAILED,
            schema_name="TavernActorReply",
            input_digest=_digest({"user_message": user_message, "guidance": guidance}),
            context_digest=_digest(
                {
                    "actor_id": actor.persona_id,
                    "prompt_hash": actor.prompt_hash,
                    "participant_ids": [item.persona_id for item in participants],
                    "message_ids": [item.id for item in recent_messages],
                }
            ),
            checks=[
                HarnessCheckRecord(
                    name=stage,
                    status=HarnessCheckStatus.FAILED,
                    code=error_code[:128],
                    message="本轮未通过可靠性边界，未提交角色消息。",
                )
            ],
            duration_ms=max(0, duration_ms),
        )
        return self.merge_model_recoveries(trace, recoveries)


class TavernHarnessViolation(RuntimeError):
    def __init__(self, trace: HarnessTraceRecord) -> None:
        super().__init__("tavern_actor_harness_failed")
        self.trace = trace


def persona_prompt_hash(persona_payload: object) -> str:
    return tavern_payload_digest(persona_payload)


def tavern_payload_digest(payload: object) -> str:
    return _digest(payload)


def _digest(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()[:16]
