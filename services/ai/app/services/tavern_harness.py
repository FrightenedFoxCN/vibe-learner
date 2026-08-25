from __future__ import annotations

from dataclasses import dataclass
import html
import re
import time
import unicodedata

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
from app.models.tavern_integrity import persona_prompt_hash, tavern_payload_digest
from app.services.tavern_prompt import (
    TAVERN_ACTOR_PROMPT_VERSION,
    TAVERN_PROMPT_BUDGET_VERSION,
    TavernPromptBudgetError,
    TavernPromptBudgetReport,
)


TAVERN_SPEAKER_IDENTITY_POLICY_VERSION = "tavern-speaker-identity-v2"

# Explicit security projection for commonly exploitable Unicode
# Default_Ignorable_Code_Point values. Do not broaden this to an entire
# Unicode category: combining marks and language joiners outside this reviewed
# set can carry legitimate linguistic meaning.
_IDENTITY_IGNORABLE_CODEPOINTS = frozenset(
    {
        0x00AD,  # SOFT HYPHEN
        0x034F,  # COMBINING GRAPHEME JOINER
        0x061C,  # ARABIC LETTER MARK
        0x180E,  # MONGOLIAN VOWEL SEPARATOR
        0x200B,  # ZERO WIDTH SPACE
        0x200C,  # ZERO WIDTH NON-JOINER
        0x200D,  # ZERO WIDTH JOINER
        0x200E,  # LEFT-TO-RIGHT MARK
        0x200F,  # RIGHT-TO-LEFT MARK
        0x3164,  # HANGUL FILLER
        0xFEFF,  # ZERO WIDTH NO-BREAK SPACE / BOM
        0xFFA0,  # HALFWIDTH HANGUL FILLER
    }
)
_IDENTITY_IGNORABLE_RANGES = (
    (0x115F, 0x1160),  # HANGUL CHOSEONG/JUNGSEONG FILLER
    (0x17B4, 0x17B5),  # KHMER VOWEL INHERENT controls
    (0x180B, 0x180D),  # MONGOLIAN variation selectors
    (0x202A, 0x202E),  # bidirectional embedding/override controls
    (0x2060, 0x206F),  # word joiner and invisible/bidi controls
    (0xFE00, 0xFE0F),  # variation selectors
    (0x1BCA0, 0x1BCA3),  # shorthand format controls
    (0x1D173, 0x1D17A),  # musical symbol format controls
    (0xE0000, 0xE007F),  # tags
    (0xE0100, 0xE01EF),  # variation selector supplement
)
_IDENTITY_HTML_ENTITY_PATTERN = re.compile(
    r"&(?:#[xX][0-9A-Fa-f]+|#[0-9]+|[A-Za-z][A-Za-z0-9]+);"
)
_COMMONMARK_ESCAPABLE_PUNCTUATION = frozenset(
    "!\"#$%&'()*+,-./:;<=>?@[\\]^_`{|}~"
)


@dataclass(frozen=True)
class TavernSpeakerIdentityMarker:
    persona_id: str
    display_name: str
    aliases: tuple[str, ...]


@dataclass(frozen=True)
class TavernSpeakerIdentityViolation:
    persona_id: str
    alias: str
    kind: str
    start: int


class TavernActorHarness:
    def build_lease_exhaustion_trace(
        self,
        *,
        actor: TavernParticipantRecord,
        policy: TavernHarnessPolicy,
        claim_count: int,
        max_claims: int,
    ) -> HarnessTraceRecord:
        return HarnessTraceRecord(
            version=_trace_version(policy),
            workflow="tavern",
            stage="lease_recovery",
            status=HarnessStatus.FAILED,
            schema_name="TavernSpeakerStepLease",
            context_digest=_digest(
                {
                    "actor_id": actor.persona_id,
                    "prompt_hash": actor.prompt_hash,
                }
            ),
            checks=[
                HarnessCheckRecord(
                    name="bounded_step_claims",
                    status=HarnessCheckStatus.FAILED,
                    code="tavern_step_claims_exhausted",
                    message=(
                        f"角色步骤已耗尽 {claim_count}/{max_claims} 次运行所有权。"
                    ),
                )
            ],
            attempts=max(1, min(3, claim_count)),
            recovery_strategy="lease_takeover_exhausted",
        )

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
            rf"^\s*{re.escape(actor.display_name)}\s*[:：﹕꞉︓]\s*",
            re.IGNORECASE,
        )
        if own_prefix.search(repaired_text):
            repaired_text = own_prefix.sub("", repaired_text, count=1).strip()
            recovery_steps.append("strip_self_prefix")

        impersonated_id = ""
        identity_failed = False
        if policy.prevent_speaker_impersonation:
            identity_markers = build_speaker_identity_markers(
                participants,
                actor_persona_id=actor.persona_id,
            )
            violation = find_cross_speaker_impersonation(
                repaired_text,
                identity_markers,
            )
            if violation is not None:
                impersonated_id = violation.persona_id
                repaired_text = repaired_text[: violation.start].rstrip()
                recovery_steps.append("truncate_cross_speaker_content")

            # Re-scan every model-owned display/performance field after text
            # repair. Non-text impersonation is not safely rewritable.
            repaired_fields = {
                "text": repaired_text,
                "mood": reply.mood,
                "action": reply.action,
                "speech_style": reply.speech_style,
                "delivery_cue": reply.delivery_cue,
                "state_commentary": reply.state_commentary,
            }
            remaining_identity_violation = next(
                (
                    (field_name, found)
                    for field_name, value in repaired_fields.items()
                    if (
                        found := find_cross_speaker_impersonation(
                            value,
                            identity_markers,
                        )
                    )
                    is not None
                ),
                None,
            )
            identity_failed = bool(
                (violation is not None and not repaired_text.strip())
                or remaining_identity_violation is not None
            )
            if remaining_identity_violation is not None:
                impersonated_id = remaining_identity_violation[1].persona_id
        checks.append(
            HarnessCheckRecord(
                name="speaker_identity",
                status=(
                    HarnessCheckStatus.FAILED
                    if identity_failed
                    else HarnessCheckStatus.WARNING
                    if impersonated_id
                    else HarnessCheckStatus.PASSED
                ),
                code=(
                    f"cross_speaker_impersonation_unrepairable:{impersonated_id}"
                    if identity_failed
                    else f"cross_speaker_impersonation:{impersonated_id}"
                    if impersonated_id
                    else ""
                ),
                message=(
                    "检测到无法安全修复的其他角色台词或内心活动。"
                    if identity_failed
                    else "已截断其他角色署名后的内容，并重新检查全部输出字段。"
                    if impersonated_id
                    else "说话者归属有效。"
                ),
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
        failed = identity_failed or leaked_prompt or leaked_guidance or empty_reply
        trace = HarnessTraceRecord(
            version=_trace_version(policy),
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

    def merge_prompt_budget_report(
        self,
        trace: HarnessTraceRecord,
        report: TavernPromptBudgetReport,
    ) -> HarnessTraceRecord:
        """Attach content-free preflight evidence to the legacy Tavern trace."""

        merged = trace.model_copy(deep=True)
        trimmed = report.removed_message_count > 0
        merged.checks.append(
            HarnessCheckRecord(
                name="prompt_budget",
                status=(
                    HarnessCheckStatus.WARNING
                    if trimmed
                    else HarnessCheckStatus.PASSED
                ),
                code=(
                    f"tavern_prompt_transcript_trimmed:{report.removed_message_count}"
                    if trimmed
                    else ""
                ),
                message=(
                    f"{report.version}: prompt_bytes "
                    f"{report.original_prompt_bytes}->{report.final_prompt_bytes}; "
                    f"transcript_bytes {report.original_transcript_bytes}->"
                    f"{report.final_transcript_bytes}; "
                    f"removed_messages={report.removed_message_count}; "
                    f"input_token_estimate={report.input_token_estimate}."
                ),
            )
        )
        if trimmed and merged.status != HarnessStatus.FAILED:
            merged.status = HarnessStatus.REPAIRED
            strategies = [
                item
                for item in merged.recovery_strategy.split("+")
                if item and item != "none"
            ]
            strategies.append("trim_oldest_transcript_for_prompt_budget")
            merged.recovery_strategy = "+".join(dict.fromkeys(strategies))
        return merged

    def merge_prompt_budget_failure(
        self,
        trace: HarnessTraceRecord,
        error: TavernPromptBudgetError,
    ) -> HarnessTraceRecord:
        """Attach content-free actual/limit evidence for preflight rejection."""

        merged = trace.model_copy(deep=True)
        merged.checks.append(
            HarnessCheckRecord(
                name="prompt_budget",
                status=HarnessCheckStatus.FAILED,
                code=error.code,
                message=(
                    f"{TAVERN_PROMPT_BUDGET_VERSION}: partition={error.partition}; "
                    f"actual={error.actual}; limit={error.limit}."
                ),
            )
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
            version=_trace_version(policy),
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


def _digest(value: object) -> str:
    return tavern_payload_digest(value)


def _trace_version(policy: TavernHarnessPolicy) -> str:
    return (
        f"{policy.version}/{TAVERN_ACTOR_PROMPT_VERSION}/"
        f"{TAVERN_SPEAKER_IDENTITY_POLICY_VERSION}/{TAVERN_PROMPT_BUDGET_VERSION}"
    )


def build_speaker_identity_markers(
    participants: list[TavernParticipantRecord],
    *,
    actor_persona_id: str,
) -> list[TavernSpeakerIdentityMarker]:
    """Compile reviewable server-owned names, IDs, and safe ID aliases."""

    markers: list[TavernSpeakerIdentityMarker] = []
    for participant in sorted(participants, key=lambda item: item.display_order):
        if participant.persona_id == actor_persona_id:
            continue
        aliases = {
            _normalize_identity_alias(participant.display_name),
            _normalize_identity_alias(participant.persona_id),
            *(
                _normalize_identity_alias(item)
                for item in _safe_persona_id_aliases(participant.persona_id)
            ),
        }
        aliases.discard("")
        markers.append(
            TavernSpeakerIdentityMarker(
                persona_id=participant.persona_id,
                display_name=participant.display_name,
                aliases=tuple(sorted(aliases, key=lambda item: (-len(item), item))),
            )
        )
    return markers


def find_cross_speaker_impersonation(
    value: str,
    markers: list[TavernSpeakerIdentityMarker],
) -> TavernSpeakerIdentityViolation | None:
    """Find script-like other-speaker dialogue or attributed inner activity.

    Plain third-person mentions do not match. A name/ID/alias must be used as a
    speaker label, introduce a quotation, or own an inner-thought verb.
    """

    alias_owners: dict[str, TavernSpeakerIdentityMarker] = {}
    for marker in markers:
        for alias in marker.aliases:
            alias_owners.setdefault(_identity_comparison_text(alias), marker)
    if not alias_owners or not value:
        return None

    normalized_value, visible_value, original_offsets, code_span_ids = (
        _identity_comparison_projection(value)
    )

    aliases = sorted(alias_owners, key=lambda item: (-len(item), item))
    alias_pattern = "(?P<alias>" + "|".join(re.escape(item) for item in aliases) + ")"
    colon = r"(?P<colon>[:：﹕꞉︓])"
    open_quote = r"[\"“‘「『]"
    label_open = (
        r"(?:[*_~`]{1,3}|\[|"
        r"<(?:b|strong|em|i|code|s|del)(?:[ \t][^>\r\n]{0,128})?>)*"
    )
    label_close = (
        r"(?:[*_~`]{1,3}|\](?:\([^\)\r\n]{0,512}\))?|"
        r"</(?:b|strong|em|i|code|s|del)[ \t]*>)*"
    )
    patterns = [
        (
            "script_label",
            re.compile(
                rf"(?im)^[ \t]*(?:>[ \t]*)?(?:[-+*][ \t]+)?"
                rf"{label_open}(?:{open_quote}[ \t]*)?{alias_pattern}"
                rf"{label_close}[ \t]*{colon}",
            ),
        ),
        (
            "quoted_label",
            re.compile(
                rf"{open_quote}[ \t]*{label_open}{alias_pattern}{label_close}"
                rf"[ \t]*{colon}",
            ),
        ),
        (
            "inline_label",
            re.compile(
                rf"(?<![A-Za-z0-9_.:/-]){label_open}"
                rf"(?:{open_quote}[ \t]*)?{alias_pattern}"
                rf"{label_close}[ \t]*{colon}",
            ),
        ),
        (
            "quoted_speech",
            re.compile(
                rf"{alias_pattern}[ \t]*(?:说道|说|问道|问|回答|答道|"
                rf"喊道|喊|低语|嘀咕|回应|开口)[ \t]*(?:{colon}|{open_quote})",
            ),
        ),
        (
            "inner_activity",
            re.compile(
                rf"{alias_pattern}[ \t]*(?:心想|暗想|想道|想着|"
                rf"内心(?:想|道|活动)?|脑海中?(?:想|浮现))",
            ),
        ),
    ]
    candidates: list[TavernSpeakerIdentityViolation] = []
    for kind, pattern in patterns:
        match = pattern.search(normalized_value)
        if match is None:
            continue
        if kind in {"script_label", "quoted_label", "inline_label"} and (
            _identity_match_is_one_code_span(
                visible_value,
                code_span_ids,
                match.start("alias"),
                match.end("colon"),
            )
        ):
            continue
        alias = match.group("alias")
        owner = alias_owners.get(alias)
        if owner is None:
            continue
        candidates.append(
            TavernSpeakerIdentityViolation(
                persona_id=owner.persona_id,
                alias=alias,
                kind=kind,
                start=_identity_original_offset(
                    visible_value,
                    original_offsets,
                    match.start(),
                    fallback=len(value),
                ),
            )
        )
    if not candidates:
        return None
    return min(candidates, key=lambda item: (item.start, -len(item.alias), item.persona_id))


def _safe_persona_id_aliases(persona_id: str) -> tuple[str, ...]:
    normalized = unicodedata.normalize("NFKC", persona_id).strip()
    pieces = [item for item in re.split(r"[-_.:/\s]+", normalized) if item]
    if len(pieces) < 2:
        return ()
    generic_prefixes = {"persona", "character", "actor", "role"}
    candidate = pieces[-1]
    if pieces[0].casefold() not in generic_prefixes:
        return ()
    if not (1 <= len(candidate) <= 32) or candidate.casefold() in generic_prefixes:
        return ()
    return (candidate,)


def _normalize_identity_alias(value: str) -> str:
    return unicodedata.normalize("NFKC", value).strip()


def _identity_comparison_text(value: str) -> str:
    return _identity_comparison_projection(value)[0]


def _identity_comparison_projection(
    value: str,
) -> tuple[str, str, list[int], list[int | None]]:
    """Project rendered identity text while preserving original source offsets."""

    visible_value, original_offsets, code_span_ids = _identity_display_projection(value)
    return (
        _normalize_identity_visible_text(visible_value),
        visible_value,
        original_offsets,
        code_span_ids,
    )


def _identity_display_projection(
    value: str,
) -> tuple[str, list[int], list[int | None]]:
    """Build a conservative CommonMark-like visible-text security projection."""

    visible: list[str] = []
    original_offsets: list[int] = []
    code_span_ids: list[int | None] = []
    pending_removed_start: int | None = None
    code_spans = _commonmark_code_spans(value)
    emphasis_delimiters = _commonmark_emphasis_delimiters(value, code_spans)
    link_closings: dict[int, int] = {}

    def mark_removed(index: int) -> None:
        nonlocal pending_removed_start
        if pending_removed_start is None:
            pending_removed_start = index

    def append_visible(
        character: str,
        source_index: int,
        *,
        code_span_id: int | None = None,
    ) -> None:
        nonlocal pending_removed_start
        visible.append(character)
        original_offsets.append(
            pending_removed_start
            if pending_removed_start is not None
            else source_index
        )
        code_span_ids.append(code_span_id)
        pending_removed_start = None

    index = 0
    while index < len(value):
        character = value[index]

        code_span = code_spans.get(index)
        if code_span is not None:
            content_start, content_end, span_end = code_span
            mark_removed(index)
            for content_index in range(content_start, content_end):
                content_character = value[content_index]
                if _is_identity_ignorable(content_character):
                    mark_removed(content_index)
                elif content_character in "\r\n":
                    append_visible(" ", content_index, code_span_id=index)
                else:
                    append_visible(
                        content_character,
                        content_index,
                        code_span_id=index,
                    )
            mark_removed(content_end)
            index = span_end
            continue

        if (
            character == "\\"
            and index + 1 < len(value)
            and value[index + 1] in _COMMONMARK_ESCAPABLE_PUNCTUATION
        ):
            mark_removed(index)
            append_visible(value[index + 1], index + 1)
            index += 2
            continue

        entity = _IDENTITY_HTML_ENTITY_PATTERN.match(value, index)
        if entity is not None:
            decoded = html.unescape(entity.group(0))
            if decoded != entity.group(0):
                for decoded_character in decoded:
                    if _is_identity_ignorable(decoded_character):
                        mark_removed(index)
                    else:
                        append_visible(decoded_character, index)
                index = entity.end()
                continue

        if _is_identity_ignorable(character):
            mark_removed(index)
            index += 1
            continue

        if index in emphasis_delimiters:
            mark_removed(index)
            index += 1
            continue

        if character == "[" and not _is_commonmark_escaped(value, index):
            inline_link = _commonmark_inline_link(value, index)
            if inline_link is not None:
                closing_index, destination_end = inline_link
                link_closings[closing_index] = destination_end
                mark_removed(index)
                index += 1
                continue

        if character == "]" and index in link_closings:
            mark_removed(index)
            index = link_closings[index]
            continue

        append_visible(character, index)
        index += 1

    return "".join(visible), original_offsets, code_span_ids


def _commonmark_code_spans(value: str) -> dict[int, tuple[int, int, int]]:
    spans: dict[int, tuple[int, int, int]] = {}
    index = 0
    while index < len(value):
        if value[index] != "`" or _is_commonmark_escaped(value, index):
            index += 1
            continue
        run_length = 1
        while index + run_length < len(value) and value[index + run_length] == "`":
            run_length += 1
        closing = index + run_length
        while closing < len(value):
            closing = value.find("`" * run_length, closing)
            if closing < 0:
                break
            before_is_tick = closing > 0 and value[closing - 1] == "`"
            after_is_tick = (
                closing + run_length < len(value)
                and value[closing + run_length] == "`"
            )
            if not before_is_tick and not after_is_tick:
                spans[index] = (
                    index + run_length,
                    closing,
                    closing + run_length,
                )
                index = closing + run_length
                break
            closing += run_length
        else:
            index += run_length
            continue
        if closing < 0:
            index += run_length
    return spans


def _commonmark_emphasis_delimiters(
    value: str,
    code_spans: dict[int, tuple[int, int, int]],
) -> set[int]:
    excluded = {
        index
        for content_start, content_end, span_end in code_spans.values()
        for index in range(content_start - 1, span_end)
    }
    delimiters: set[int] = set()
    masked = "".join("\n" if index in excluded else character for index, character in enumerate(value))
    for character, maximum in (("*", 3), ("_", 3), ("~", 2)):
        pattern = re.compile(
            rf"(?<!\\)(?P<open>{re.escape(character)}{{1,{maximum}}})"
            rf"(?P<body>\S(?:[^\r\n]*?\S)?)(?P=open)"
        )
        for match in pattern.finditer(masked):
            opening = match.start("open")
            closing = match.start("open") + len(match.group("open")) + len(
                match.group("body")
            )
            if character == "_":
                before = value[opening - 1] if opening > 0 else ""
                after_open = value[match.end("open")] if match.end("open") < len(value) else ""
                before_close = value[closing - 1] if closing > 0 else ""
                after_close_index = closing + len(match.group("open"))
                after_close = (
                    value[after_close_index]
                    if after_close_index < len(value)
                    else ""
                )
                if before.isalnum() and after_open.isalnum():
                    continue
                if before_close.isalnum() and after_close.isalnum():
                    continue
            delimiters.update(range(opening, match.end("open")))
            delimiters.update(range(closing, closing + len(match.group("open"))))
    return delimiters


def _commonmark_inline_link(value: str, start: int) -> tuple[int, int] | None:
    closing = value.find("]", start + 1)
    if closing < 0 or "\n" in value[start + 1 : closing]:
        return None
    destination_start = closing + 1
    if destination_start >= len(value) or value[destination_start] != "(":
        return None
    destination_end = _commonmark_link_destination_end(value, destination_start)
    if destination_end == destination_start:
        return None
    return closing, destination_end


def _is_commonmark_escaped(value: str, index: int) -> bool:
    backslashes = 0
    cursor = index - 1
    while cursor >= 0 and value[cursor] == "\\":
        backslashes += 1
        cursor -= 1
    return backslashes % 2 == 1


def _commonmark_link_destination_end(value: str, start: int) -> int:
    """Return the exclusive end of one balanced inline-link destination."""

    if start >= len(value) or value[start] != "(":
        return start
    depth = 0
    index = start
    while index < len(value):
        character = value[index]
        if character in "\r\n":
            return start
        if character == "\\" and index + 1 < len(value):
            index += 2
            continue
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    return start


def _normalize_identity_visible_text(value: str) -> str:
    """Apply whole-string Unicode compatibility and caseless normalization."""

    normalized = unicodedata.normalize("NFKC", value)
    return unicodedata.normalize("NFKC", normalized.casefold())


def _identity_match_is_one_code_span(
    visible_value: str,
    code_span_ids: list[int | None],
    normalized_start: int,
    normalized_end: int,
) -> bool:
    if normalized_end <= normalized_start or not code_span_ids:
        return False
    visible_start = _identity_visible_index(visible_value, normalized_start)
    visible_end = _identity_visible_index(visible_value, normalized_end - 1)
    matched_ids = code_span_ids[visible_start : visible_end + 1]
    return bool(
        matched_ids
        and matched_ids[0] is not None
        and all(code_span_id == matched_ids[0] for code_span_id in matched_ids)
    )


def _is_identity_ignorable(character: str) -> bool:
    codepoint = ord(character)
    return codepoint in _IDENTITY_IGNORABLE_CODEPOINTS or any(
        lower <= codepoint <= upper
        for lower, upper in _IDENTITY_IGNORABLE_RANGES
    )


def _identity_original_offset(
    visible_value: str,
    original_offsets: list[int],
    normalized_index: int,
    *,
    fallback: int,
) -> int:
    """Map a normalized match start to the earliest safe original offset."""

    if not original_offsets:
        return fallback
    visible_index = _identity_visible_index(visible_value, normalized_index)
    visible_index = min(visible_index, len(original_offsets) - 1)
    return original_offsets[visible_index]


def _identity_visible_index(visible_value: str, normalized_index: int) -> int:
    lower = 0
    upper = len(visible_value)
    while lower < upper:
        midpoint = (lower + upper) // 2
        prefix_length = len(
            _normalize_identity_visible_text(visible_value[:midpoint])
        )
        if prefix_length > normalized_index:
            upper = midpoint
        else:
            lower = midpoint + 1
    return min(max(0, lower - 1), max(0, len(visible_value) - 1))
