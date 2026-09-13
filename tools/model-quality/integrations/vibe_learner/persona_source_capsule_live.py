"""Fresh, paired Persona proposal experiment with a source-constraint appendix.

This adapter sends exactly one Chat Completions wire per sample.  It does not
enter the Persona domain, retry, search the web, fall back to reasoning text,
or save a Persona.  The capsule appendix is a research prompt projection;
exact-marker findings are deterministic non-semantic evidence only.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from app.models.persona_generation import PersonaCardBatchContentProposalV1
from app.services.provider_payload import (
    _extract_choice_content,
    _extract_choice_diagnostics,
    _extract_json_payload,
)
from app.services.provider_sdk import ProviderRequestAdapter
from app.services.provider_settings import (
    PERSONA_CARD_GENERATION_SCHEMA,
    _render_persona_card_count_hint,
    _setting_prompt_sections,
)
from model_quality.ledger import GateClosed
from model_quality.runner import atomic_json
from model_quality.transport import WireFailure

from .common import Bridge, envelope
from .persona_source_capsule import (
    PersonaSourceCapsuleFixtureV1,
    capsule_sha256,
    validate_persona_source_constraints,
)


FIXTURE = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "persona-scene"
    / "persona-source-capsule-v1.json"
)
FIXTURE_SHA256 = "bf24f623b4644765133d0a9e94fb24f96984c92252a13323f9584c0e79106a23"
RUBRIC = "persona-source-capsule-live-v1"
BASELINE_VARIANT = "production-prompt-fresh"
CANDIDATE_VARIANT = "capsule-prompt-fresh"
SCOPE = "provider-proposal-only; no domain admission, commit or read-back"
EVIDENCE_NAME = "persona-source-capsule-live-evidence.json"
EVIDENCE_CONTRACT = "persona-source-capsule-live-evidence-v1"
PREREGISTERED_GATE = {
    "version": "persona-source-capsule-paired-gate-v1",
    "denominator": "all_8_pairs_including_failed_or_unavailable_candidates",
    "paired_strict_candidates_min": 7,
    "shared_major_reductions_min": 4,
    "candidate_only_major_max": 0,
    "capsule_relationship_major_max": 0,
    "capsule_permission_major_max": 0,
    "blind_reviewers": 2,
    "production_registry_change": False,
    "persona_save": False,
}
CAMPAIGN_ID = "m3-persona-source-capsule-paired-fresh-20260913-v1"
CAMPAIGN_SEED = 91317
CAMPAIGN_CONCURRENCY = 2
CAMPAIGN_TIMEOUT_SECONDS = 90
CAMPAIGN_SAMPLE_DEADLINE_SECONDS = 300
CAMPAIGN_MAX_OUTPUT_TOKENS = 4096
CAMPAIGN_INPUT_RESERVATION_TOKENS = 100000
LIVE_CAMPAIGN_CANONICAL_SHA256 = "c4b4bdf1bcd1a31688c3463502a98feaa521df784be066fbf7a0f6241a5332ea"


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_json(value: object) -> str:
    raw = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    return _sha256_bytes(raw)


def _load_fixture_case(case_id: str):
    raw = FIXTURE.read_bytes()
    if _sha256_bytes(raw) != FIXTURE_SHA256:
        raise ValueError("persona_source_capsule_fixture_digest_mismatch")
    fixture = PersonaSourceCapsuleFixtureV1.model_validate_json(raw, strict=True)
    matches = [row for row in fixture.cases if row.case_id == case_id]
    if len(matches) != 1:
        raise ValueError("persona_source_capsule_fixture_case_mismatch")
    return matches[0]


def build_prompt_projection(capsule) -> dict[str, object]:
    """Project claim coordinates, never duplicated source text or grading gold."""
    return {
        "version": "persona-source-constraint-prompt-v1",
        "address": capsule.address_exact,
        "claims": [
            {
                "claim_id": claim.claim_id,
                "kind": claim.claim_kind,
                "key": claim.claim_key,
                "polarity": claim.polarity,
                "source_char_start": claim.source_span.char_start,
                "source_char_end": claim.source_span.char_end,
            }
            for claim in capsule.claims
        ],
        "rules": [
            "称呼必须使用 address 的原值。",
            "source_char_start/source_char_end 指向 user 消息中同一份冻结来源；按坐标回看原文，不要补写坐标外事实。",
            "polarity 为 denied 时不得断言该 claim；为 unknown 时必须保留未知状态。",
            "不要把角色职业自动改写成与学习者的关系或权限。",
            "只输出既定人格卡片 JSON schema。",
        ],
    }


def _production_payload(*, model: str, source: str, temperature: float, max_tokens: int):
    sections = _setting_prompt_sections()
    count_hint = _render_persona_card_count_hint(1)
    return {
        "model": model,
        "temperature": temperature,
        "max_tokens": max(max_tokens, 1200),
        "response_format": {"type": "json_object"},
        "messages": [
            {
                "role": "system",
                "content": sections["generate_long_text_system"]
                .replace("{{PERSONA_CARD_SCHEMA}}", PERSONA_CARD_GENERATION_SCHEMA)
                .replace("{{CARD_COUNT}}", count_hint),
            },
            {
                "role": "user",
                "content": sections["generate_long_text_user"]
                .replace("{{SOURCE_TEXT}}", source.strip())
                .replace("{{CARD_COUNT}}", count_hint)
                .replace("{{PERSONA_CARD_SCHEMA}}", PERSONA_CARD_GENERATION_SCHEMA),
            },
        ],
    }


def build_payload(*, campaign, source: str, projection: dict[str, object] | None):
    payload = _production_payload(
        model=campaign.model,
        source=source,
        temperature=campaign.temperature,
        max_tokens=campaign.max_output_tokens,
    )
    if projection is not None:
        appendix = json.dumps(
            projection,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        payload["messages"][0]["content"] += (
            "\n\n[persona_source_constraint_appendix_v1]\n" + appendix
        )
    return payload


def _safe_wire(raw: object) -> dict[str, object]:
    result: dict[str, object] = {
        "finish_reason": "missing",
        "prompt_tokens": 0,
        "completion_tokens": 0,
        "total_tokens": 0,
        "final_channel": "message.content",
        "final_content_present": False,
    }
    if not isinstance(raw, dict):
        return result
    finish, _, completion_tokens = _extract_choice_diagnostics(raw)
    result["finish_reason"] = (
        finish
        if finish in {"stop", "length", "tool_calls", "function_call", "content_filter"}
        else "unknown" if finish else "missing"
    )
    usage = raw.get("usage")
    if isinstance(usage, dict):
        for key in ("prompt_tokens", "total_tokens"):
            value = usage.get(key)
            result[key] = value if isinstance(value, int) and value >= 0 else 0
    result["completion_tokens"] = completion_tokens
    choices = raw.get("choices")
    if isinstance(choices, list) and choices and isinstance(choices[0], dict):
        message = choices[0].get("message")
        if isinstance(message, dict):
            content = message.get("content")
            result["final_content_present"] = isinstance(content, str) and bool(content.strip())
    return result


def _result(context, *, status: str, error_code: str | None, evidence: dict[str, object]):
    atomic_json(context.storage / EVIDENCE_NAME, evidence)
    evidence_sha256 = _sha256_bytes((context.storage / EVIDENCE_NAME).read_bytes())
    result: dict[str, object] = {
        "status": status,
        "failure_owner": (
            None
            if status == "completed"
            else "infrastructure" if status == "uncertain" else status.removesuffix("_failed")
        ),
        "metrics": {
            "strict_candidate": bool(evidence.get("strict_candidate")),
            "exact_marker_issue_count": len(evidence.get("exact_marker_issues", [])),
        },
        "scope": SCOPE,
        "evidence": [{
            "path": EVIDENCE_NAME,
            "contract": EVIDENCE_CONTRACT,
            "sha256": evidence_sha256,
        }],
    }
    if error_code is not None:
        result["error_code"] = error_code
    return result


def run_sample(context, case, variant):
    bridge: Bridge | None = None
    try:
        fixture_case = _load_fixture_case(case.id)
        spec = json.loads(case.gold)
        if (
            case.rubric != RUBRIC
            or case.source != fixture_case.source_text
            or not isinstance(spec, dict)
            or spec.get("fixture_sha256") != FIXTURE_SHA256
            or spec.get("source_sha256") != fixture_case.capsule.source_sha256
            or spec.get("capsule_sha256") != capsule_sha256(fixture_case.capsule)
            or spec.get("fake_proposal")
            != fixture_case.valid_minimal_persona_card_batch_proposal
            or spec.get("preregistered_gate") != PREREGISTERED_GATE
        ):
            raise ValueError("persona_source_capsule_case_binding_mismatch")
    except (OSError, ValueError, ValidationError, json.JSONDecodeError):
        return {
            "status": "data_failed",
            "failure_owner": "data",
            "error_code": "persona_source_capsule_fixture_invalid",
            "scope": SCOPE,
        }

    campaign = context.transport.campaign
    if (
        campaign.id != CAMPAIGN_ID
        or campaign.seed != CAMPAIGN_SEED
        or campaign.concurrency != CAMPAIGN_CONCURRENCY
        or campaign.repetitions != 1
        or campaign.timeout_seconds != CAMPAIGN_TIMEOUT_SECONDS
        or campaign.sample_deadline_seconds != CAMPAIGN_SAMPLE_DEADLINE_SECONDS
        or campaign.autoscale is not None
        or campaign.adapter != "vibe_learner.persona_source_capsule_live:run_sample"
        or [item.id for item in campaign.cases]
        != [item.case_id for item in PersonaSourceCapsuleFixtureV1.model_validate_json(
            FIXTURE.read_bytes(), strict=True
        ).cases]
        or [item.id for item in campaign.variants]
        != [BASELINE_VARIANT, CANDIDATE_VARIANT]
        or variant.id not in {BASELINE_VARIANT, CANDIDATE_VARIANT}
        or campaign.model != "MiniMax-M3"
        or campaign.thinking != "adaptive"
        or campaign.temperature != 0.2
        or campaign.max_output_tokens != CAMPAIGN_MAX_OUTPUT_TOKENS
        or campaign.sample_wire_limit != 1
        or campaign.input_reservation_tokens != CAMPAIGN_INPUT_RESERVATION_TOKENS
        or (
            campaign.transport == "minimax"
            and _sha256_json(campaign.model_dump(mode="json"))
            != LIVE_CAMPAIGN_CANONICAL_SHA256
        )
    ):
        return {
            "status": "infrastructure_failed",
            "failure_owner": "infrastructure",
            "error_code": "persona_source_capsule_campaign_invalid",
            "scope": SCOPE,
        }

    projection = (
        build_prompt_projection(fixture_case.capsule)
        if variant.id == CANDIDATE_VARIANT
        else None
    )
    projection_for_digest: object = projection if projection is not None else {
        "version": "production-prompt-no-capsule-projection-v1"
    }
    payload = build_payload(
        campaign=campaign,
        source=case.source,
        projection=projection,
    )
    fake_proposal = fixture_case.valid_minimal_persona_card_batch_proposal
    bridge = Bridge(context, lambda _: envelope(json.dumps(fake_proposal, ensure_ascii=False)))
    evidence: dict[str, object] = {
        "version": EVIDENCE_CONTRACT,
        "case_id": case.id,
        "variant": variant.id,
        "scope": SCOPE,
        "commit_evidence": {"status": "not_applicable"},
        "source_sha256": fixture_case.capsule.source_sha256,
        "capsule_sha256": fixture_case.capsule_sha256,
        "prompt_projection_sha256": _sha256_json(projection_for_digest),
        "provider_payload_sha256": _sha256_json(payload),
        "campaign_config_sha256": _sha256_json(campaign.model_dump(mode="json")),
        "strict_candidate": False,
        "exact_marker_policy": "deterministic_exact_match_non_semantic",
        "exact_marker_issues": [],
    }
    try:
        with bridge.installed():
            raw, _ = ProviderRequestAdapter.request_chat_completion(
                None,  # patched by Bridge; no SDK endpoint can escape the ledger
                payload,
                request_kind="setting",
                model=campaign.model,
            )
    except GateClosed:
        evidence["safe_wire"] = {"dispatch": "gate_closed"}
        return _result(
            context,
            status="infrastructure_failed",
            error_code="persona_source_capsule_gate_closed",
            evidence=evidence,
        )
    except WireFailure as exc:
        evidence["safe_wire"] = {
            "dispatch": "ambiguous_after_request" if exc.uncertain else "known_transport_failure"
        }
        return _result(
            context,
            status="uncertain" if exc.uncertain else "infrastructure_failed",
            error_code=(
                "persona_source_capsule_transport_ambiguous"
                if exc.uncertain
                else "persona_source_capsule_transport_failed"
            ),
            evidence=evidence,
        )
    except Exception:
        evidence["safe_wire"] = {"dispatch": "ambiguous_after_request"}
        return _result(
            context,
            status="uncertain",
            error_code="persona_source_capsule_transport_ambiguous",
            evidence=evidence,
        )

    safe_wire = _safe_wire(raw)
    evidence["safe_wire"] = safe_wire
    finish = safe_wire["finish_reason"]
    if finish in {"missing", "unknown"}:
        return _result(
            context,
            status="infrastructure_failed",
            error_code="persona_source_capsule_finish_reason_invalid",
            evidence=evidence,
        )
    if finish != "stop":
        return _result(
            context,
            status="candidate_failed",
            error_code="persona_source_capsule_non_final_candidate",
            evidence=evidence,
        )
    try:
        content = _extract_choice_content(raw, allow_reasoning_fallback=False)
        decoded = _extract_json_payload(
            content,
            invalid_json_code="persona_source_capsule_invalid_json",
            invalid_payload_code="persona_source_capsule_invalid_payload",
        )
        proposal = PersonaCardBatchContentProposalV1.model_validate(decoded, strict=True)
        if len(proposal.cards) != 1:
            raise ValueError("persona_source_capsule_card_count_invalid")
        issues = validate_persona_source_constraints(
            fixture_case.capsule,
            fixture_case.source_text,
            proposal,
        )
    except (RuntimeError, ValidationError, ValueError):
        return _result(
            context,
            status="candidate_failed",
            error_code="persona_source_capsule_strict_decode_failed",
            evidence=evidence,
        )
    evidence["proposal"] = proposal.model_dump(mode="json")
    evidence["strict_candidate"] = True
    evidence["exact_marker_issues"] = [item.model_dump(mode="json") for item in issues]
    return _result(context, status="completed", error_code=None, evidence=evidence)
