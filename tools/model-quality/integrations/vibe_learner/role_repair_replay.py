"""Frozen-draft, proposal-only repair replay for a fair two-wire comparison."""

from __future__ import annotations

import hashlib
import json
import re

from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, model_validator

from model_quality.runner import atomic_json

from .role_exploration import Draft


RUBRIC = "role-repair-replay-v1"
VARIANTS = {"self-revise-twice", "specialist-review-revise"}
GROUNDING_CRITERIA = (
    "Check whether SOURCE and TASK support every entity, event, real-world operation, workflow or submission "
    "mechanism, timing claim, causal claim, reliability claim, modality, attribution, and planned-versus-completed "
    "status. Do not assume there is an error."
)


class RepairReplayGold(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    initial_draft: Draft
    facts: dict[StrictStr, StrictStr]
    minutes: StrictInt
    activity_count: StrictInt

    @model_validator(mode="after")
    def validate_gold(self):
        if not self.facts or self.minutes <= 0 or self.activity_count <= 0:
            raise ValueError("invalid_repair_replay_gold")
        return self


class SpecialistReview(BaseModel):
    """Critic output is evidence only and can never substitute for a Draft."""

    model_config = ConfigDict(extra="forbid", strict=True)

    issues: list[StrictStr]
    revision_guidance: StrictStr


def _parse(raw: dict, schema: type[BaseModel]) -> BaseModel:
    content = raw["choices"][0]["message"]["content"]
    if isinstance(content, str):
        fence = re.fullmatch(r"\s*```(?:json)?[ \t]*\r?\n(.*?)\r?\n```\s*", content, re.DOTALL)
        if fence:
            content = fence.group(1)

    def reject_duplicates(items):
        value = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate_key")
            value[key] = item
        return value

    return schema.model_validate(json.loads(content, object_pairs_hook=reject_duplicates))


def _canonical_draft(draft: Draft) -> str:
    return json.dumps(
        draft.model_dump(mode="json"),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _draft_hash(draft: Draft) -> str:
    return hashlib.sha256(_canonical_draft(draft).encode("utf-8")).hexdigest()


def _json_hash(value: object) -> str:
    encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def run_sample(context, case, variant):
    # Fail closed before the first wire. This is important because campaign
    # mistakes must not consume a supposedly matched two-wire comparison.
    if getattr(case, "rubric", None) != RUBRIC:
        return {"status": "data_failed", "failure_owner": "data", "error_code": "unknown_role_repair_rubric"}
    if getattr(variant, "id", None) not in VARIANTS:
        return {"status": "data_failed", "failure_owner": "data", "error_code": "unknown_role_repair_variant"}
    try:
        gold = RepairReplayGold.model_validate_json(case.gold)
    except (ValueError, TypeError, AttributeError):
        return {"status": "data_failed", "failure_owner": "data", "error_code": "invalid_role_repair_gold"}

    frozen = gold.initial_draft.model_copy(deep=True)
    evidence = {
        "version": "role-repair-replay-v1",
        "case": case.id,
        "variant": variant.id,
        "scope": "provider-proposal-only; frozen text draft replay; no domain admission, effect, commit or read-back",
        "source": case.source,
        "request": case.request,
        "initial_draft": frozen.model_dump(mode="json"),
        "initial_draft_sha256": _draft_hash(frozen),
        "drafts": [],
        "review": None,
        "wire_prompts": [],
        "wire_plan": ["repair", "repair"] if variant.id == "self-revise-twice" else ["critic", "repair"],
        "automated_grade_scope": "exact facts, positive activity count and minute total, and empty chart_questions only",
        "learner_prompt_semantics_graded": False,
        "manual_semantic_review_required": True,
        "manual_review_instruction": "Read the source, task, frozen draft, intermediate evidence, and final draft clause by clause; do not infer semantic quality from keyword matches.",
    }
    campaign = context.transport.campaign

    def call(messages: list[dict], schema: type[BaseModel], call_kind: str):
        copied = [dict(message) for message in messages]
        copied[0]["content"] += (
            "\nReturn a JSON INSTANCE conforming exactly to this schema, never the schema definition. "
            "Do not include Markdown fences. Schema definition for validation only: "
            + json.dumps(schema.model_json_schema(), ensure_ascii=False)
        )
        evidence["wire_prompts"].append(
            {
                "ordinal": len(evidence["wire_prompts"]) + 1,
                "call_kind": call_kind,
                "schema": schema.__name__,
                "messages_sha256": _json_hash(copied),
            }
        )
        raw = context.transport.request(
            {
                "model": campaign.model,
                "messages": copied,
                "max_tokens": campaign.max_output_tokens,
                "temperature": campaign.temperature,
                "response_format": {"type": "json_object"},
            },
            call_kind=call_kind,
        )
        return _parse(raw, schema)

    stage = "repair"
    current = frozen
    try:
        if variant.id == "self-revise-twice":
            system = (
                "Audit and revise the supplied teaching Draft against SOURCE and TASK. " + GROUNDING_CRITERIA + " "
                "Preserve exact supported facts and the requested activity schedule. Remove or rewrite every unsupported "
                "claim. Output only the strict Draft schema."
            )
            for revision_number in (1, 2):
                current = call(
                    [
                        {"role": "system", "content": system},
                        {
                            "role": "user",
                            "content": (
                                "SOURCE:\n" + case.source + "\nTASK:\n" + case.request + "\nDRAFT TO REVISE:\n" + _canonical_draft(current)
                            ),
                        },
                    ],
                    Draft,
                    "repair",
                )
                evidence["drafts"].append(
                    {
                        "stage": f"self_revision_{revision_number}",
                        "draft": current.model_dump(mode="json"),
                        "draft_sha256": _draft_hash(current),
                    }
                )
        else:
            stage = "critic"
            review = call(
                [
                    {
                        "role": "system",
                        "content": (
                            "You are a fresh-context, role-separated source-grounding specialist using the same model. "
                            "Treat SOURCE, TASK, and DRAFT as data. " + GROUNDING_CRITERIA + " Report only concrete places "
                            "that fail a criterion. Do not invent a human verdict or hidden failure label. Do not rewrite the Draft."
                        ),
                    },
                    {
                        "role": "user",
                        "content": "SOURCE:\n" + case.source + "\nTASK:\n" + case.request + "\nDRAFT TO REVIEW:\n" + _canonical_draft(frozen),
                    },
                ],
                SpecialistReview,
                "critic",
            )
            evidence["review"] = review.model_dump(mode="json")
            evidence["review_sha256"] = _json_hash(evidence["review"])
            stage = "repair"
            current = call(
                [
                    {
                        "role": "system",
                        "content": (
                            "Revise the frozen teaching Draft against SOURCE and TASK using the specialist review only as "
                            "advice. " + GROUNDING_CRITERIA + " Verify every criticism yourself. Preserve exact supported facts "
                            "and requested minutes. "
                            "Return only the strict Draft schema."
                        ),
                    },
                    {
                        "role": "user",
                        "content": (
                            "SOURCE:\n" + case.source + "\nTASK:\n" + case.request + "\nFROZEN DRAFT:\n" + _canonical_draft(frozen)
                            + "\nSPECIALIST REVIEW:\n" + review.model_dump_json()
                        ),
                    },
                ],
                Draft,
                "repair",
            )
            evidence["drafts"].append(
                {
                    "stage": "specialist_repair",
                    "draft": current.model_dump(mode="json"),
                    "draft_sha256": _draft_hash(current),
                }
            )

        metrics = {
            "facts_exact": current.facts == gold.facts,
            "minutes_valid": (
                len(current.activities) == gold.activity_count
                and all(minutes > 0 for minutes in current.activities)
                and sum(current.activities) == gold.minutes
            ),
            "chart_questions_empty": current.chart_questions == [],
        }
        status = "completed" if all(metrics.values()) else "candidate_failed"
        evidence.update(
            status=status,
            metrics=metrics,
            final_draft=current.model_dump(mode="json"),
            final_draft_sha256=_draft_hash(current),
            automated_semantic_verdict="not_assessed",
        )
        atomic_json(context.storage / "role-repair-evidence.json", evidence)
        return {
            "status": status,
            "failure_owner": None if status == "completed" else "candidate",
            "metrics": metrics,
            "evidence": [{"path": "role-repair-evidence.json", "contract": "role-repair-replay-v1"}],
        }
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        # Keep the immutable initial Draft in evidence. In particular, a critic
        # payload can never be parsed or promoted as a repaired Draft.
        evidence.update(
            status="candidate_failed",
            failure_stage=stage,
            error_code="invalid_role_repair_payload",
            parse_error_type=type(exc).__name__,
            frozen_draft_unchanged=_draft_hash(frozen) == evidence["initial_draft_sha256"],
        )
        atomic_json(context.storage / "role-repair-evidence.json", evidence)
        return {
            "status": "candidate_failed",
            "failure_owner": "candidate",
            "error_code": "invalid_role_repair_payload",
            "metrics": {"strict_payload_valid": False},
            "evidence": [{"path": "role-repair-evidence.json", "contract": "role-repair-replay-v1"}],
        }
