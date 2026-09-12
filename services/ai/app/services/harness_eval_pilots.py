"""Deterministic Wave 2 pilot suites and their reviewed release baselines."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.domain import PersonaProfile, StudyUnitRecord
from app.models.harness import HarnessContractRef, HarnessStage, HarnessWorkflow, canonical_harness_digest
from app.models.harness_eval import (
    HARNESS_EVAL_FAILURE_TAXONOMY_CONTRACT,
    HarnessEvalBooleanMetricV1,
    HarnessEvalCaseV1,
    HarnessEvalEnvironmentV1,
    HarnessEvalExecutionBudgetV1,
    HarnessEvalExpectedInvariantV1,
    HarnessEvalFixtureSourceV1,
    HarnessEvalGraderResultV1,
    HarnessEvalIntegerMetricV1,
    HarnessEvalProvenanceV1,
    HarnessEvalReasoningConfigV1,
    HarnessEvalRunV1,
    HarnessEvalSamplingConfigV1,
    HarnessEvalSystemConfigV1,
    canonical_harness_eval_case_digest,
    canonical_harness_eval_environment_digest,
    canonical_harness_eval_run_digest,
    canonical_harness_eval_system_config_digest,
)
from app.models.harness_eval_baseline import (
    HarnessEvalBaselineV1,
    HarnessEvalGateDecisionV1,
    HarnessEvalMetricThresholdV1,
    build_harness_eval_baseline,
    evaluate_harness_eval_baseline,
)
from app.models.harness_manifest import (
    HARNESS_WORKFLOW_MANIFEST_SCHEMA_VERSION,
    PLANNING_TOOL_EVAL_SUITE,
    STUDY_CHAT_EVAL_SUITE,
    TAVERN_IDENTITY_EVAL_SUITE,
)
from app.models.harness_operation import (
    HARNESS_DOMAIN_OPERATION_ROUTES,
    HarnessDomainOperationKind,
    HarnessOperationBindingV1,
)
from app.models.tavern import (
    TavernActorReply,
    TavernHarnessPolicy,
    TavernParticipantRecord,
)
from app.models.tavern_integrity import persona_prompt_hash
from app.persistence.database import Database
from app.persistence.harness_operation_repository import HarnessOperationBindingRepository
from app.persistence.models import HarnessOperationBindingRow
from app.services.harness_eval_runner import (
    CANDIDATE_PASS_RATE,
    FINAL_SCHEMA_VALID_RATE,
    HarnessEvalCandidateResult,
    HarnessEvalExecution,
    HarnessEvalFixturePayload,
    HarnessEvalGraderRegistry,
    HarnessEvalRouteAdapter,
    HarnessEvalRunner,
    HarnessEvalSuiteRegistration,
    HarnessEvalSuiteRegistry,
)
from app.services.plan_prompt import build_study_unit_detail_map
from app.services.plan_tool_runtime import build_plan_tool_runtime
from app.services.tavern_harness import TavernActorHarness, TavernHarnessViolation
from app.services.study_v3 import StudyV3ReplyAdapter


FIXTURE_PATH = (
    Path(__file__).parents[4]
    / "packages"
    / "shared"
    / "fixtures"
    / "harness"
    / "pilot-eval-cases-v1.json"
)
STUDY_FIXTURE_PATH = FIXTURE_PATH.parent / "study-chat-eval-cases-v1.json"
BASELINE_ROOT = FIXTURE_PATH.parent / "eval-pilots"
PILOT_RUNNER_CONTRACT = HarnessContractRef(
    name="HarnessPilotEvalRunner",
    version="harness-pilot-eval-runner-v1",
)
PILOT_SUITE_REGISTRY_CONTRACT = HarnessContractRef(
    name="HarnessPilotEvalSuiteRegistry",
    version="harness-pilot-eval-suite-registry-v1",
)
PILOT_GRADER_REGISTRY_CONTRACT = HarnessContractRef(
    name="HarnessPilotEvalGraderRegistry",
    version="harness-pilot-eval-grader-registry-v1",
)
PILOT_ENVIRONMENT_CONTRACT = HarnessContractRef(
    name="HarnessPilotPortableEnvironment",
    version="harness-pilot-portable-environment-v1",
)
PILOT_FIXTURE_CONTRACT = HarnessContractRef(
    name="HarnessPilotEvalCasePayload",
    version="harness-pilot-eval-case-payload-v1",
)
PILOT_WORKFLOW_MANIFEST_CONTRACT = HarnessContractRef(
    name="HarnessWorkflowManifest",
    version=HARNESS_WORKFLOW_MANIFEST_SCHEMA_VERSION,
)
TAVERN_GRADER_CONTRACT = HarnessContractRef(
    name="tavern_identity_grader",
    version="tavern-identity-grader-v1",
)
PLANNING_GRADER_CONTRACT = HarnessContractRef(
    name="planning_tool_grader",
    version="planning-tool-grader-v1",
)
STUDY_GRADER_CONTRACT = HarnessContractRef(
    name="study_chat_reply_grader",
    version="study-chat-reply-grader-v1",
)
TAVERN_OUTCOME_INVARIANT = HarnessContractRef(
    name="tavern_identity_and_prompt_safety",
    version="tavern-identity-and-prompt-safety-v1",
)
PLANNING_OUTCOME_INVARIANT = HarnessContractRef(
    name="planning_tool_contract_and_grounding",
    version="planning-tool-contract-and-grounding-v1",
)
STUDY_OUTCOME_INVARIANT = HarnessContractRef(
    name="study_chat_reply_citation_event_tool_correctness",
    version="study-chat-reply-citation-event-tool-correctness-v1",
)

TAVERN_CORRECT_RATE = HarnessContractRef(
    name="tavern_identity_correct_rate",
    version="tavern-identity-correct-rate-v1",
)
TAVERN_FALSE_POSITIVE_RATE = HarnessContractRef(
    name="tavern_identity_false_positive_rate",
    version="tavern-identity-false-positive-rate-v1",
)
TAVERN_FALSE_NEGATIVE_RATE = HarnessContractRef(
    name="tavern_identity_false_negative_rate",
    version="tavern-identity-false-negative-rate-v1",
)
TAVERN_PROMPT_LEAK_BLOCK_RATE = HarnessContractRef(
    name="tavern_prompt_leak_block_rate",
    version="tavern-prompt-leak-block-rate-v1",
)
PLANNING_CORRECT_RATE = HarnessContractRef(
    name="planning_tool_correct_rate",
    version="planning-tool-correct-rate-v1",
)
PLANNING_GROUNDING_RATE = HarnessContractRef(
    name="planning_tool_grounding_rate",
    version="planning-tool-grounding-rate-v1",
)
PLANNING_INVALID_CALL_RATE = HarnessContractRef(
    name="planning_tool_invalid_call_rate",
    version="planning-tool-invalid-call-rate-v1",
)
PLANNING_TOOL_CALL_COUNT = HarnessContractRef(
    name="planning_tool_call_count",
    version="planning-tool-call-count-v1",
)
PLANNING_PROVIDER_CALL_COUNT = HarnessContractRef(
    name="planning_provider_call_count",
    version="planning-provider-call-count-v1",
)
STUDY_CORRECT_RATE = HarnessContractRef(
    name="study_chat_reply_correct_rate",
    version="study-chat-reply-correct-rate-v1",
)


class _FixtureModel(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, frozen=True)


class TavernPilotCase(_FixtureModel):
    case_id: str
    split: Literal["regression", "held_out"]
    tags: list[str]
    actor_id: str
    actor_name: str
    other_id: str
    other_name: str
    text: str
    action: str
    addressed_participant_ids: list[str]
    user_message: str
    guidance: str
    expected_status: Literal["passed", "repaired", "rejected"]


class PlanningPilotCase(_FixtureModel):
    case_id: str
    split: Literal["regression", "held_out"]
    tags: list[str]
    tool_name: str
    arguments_json: str
    disabled_tools: list[str]
    repeat_count: int = Field(ge=1, le=4)
    expected_ok: bool
    expected_error: str

    @model_validator(mode="after")
    def validate_expected_result(self) -> "PlanningPilotCase":
        if self.expected_ok == bool(self.expected_error):
            raise ValueError("planning_pilot_expected_result_invalid")
        return self


class StudyPilotCase(_FixtureModel):
    case_id: str
    split: Literal["regression", "held_out"]
    tags: list[str]
    scenario: Literal[
        "valid",
        "empty_reply",
        "citation_source",
        "character_event",
        "tool_identity",
        "tool_contract",
        "tool_json",
        "extra_field",
    ]
    expected_status: Literal["accepted", "rejected"]


class StudyPilotEvalCasesV1(_FixtureModel):
    schema_name: Literal["StudyChatEvalCases"]
    schema_version: Literal["study-chat-eval-cases-v1"]
    review_contract: HarnessContractRef
    review_attestation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    study_cases: list[StudyPilotCase] = Field(min_length=8, max_length=64)

    @model_validator(mode="after")
    def validate_cases(self) -> "StudyPilotEvalCasesV1":
        ids = [item.case_id for item in self.study_cases]
        if len(ids) != len(set(ids)):
            raise ValueError("study_chat_eval_case_id_duplicate")
        if not any(item.split == "held_out" for item in self.study_cases):
            raise ValueError("study_chat_eval_held_out_split_missing")
        for item in self.study_cases:
            if item.tags != sorted(set(item.tags)):
                raise ValueError("study_chat_eval_case_tags_not_canonical")
        expected = canonical_harness_digest(
            {
                "contract": self.review_contract.model_dump(mode="json"),
                "study_cases": [
                    item.model_dump(mode="json") for item in self.study_cases
                ],
            }
        )
        if self.review_attestation_digest != expected:
            raise ValueError("study_chat_eval_review_attestation_digest_mismatch")
        return self


class HarnessPilotEvalCasesV1(_FixtureModel):
    schema_name: Literal["HarnessPilotEvalCases"]
    schema_version: Literal["harness-pilot-eval-cases-v1"]
    review_contract: HarnessContractRef
    review_attestation_digest: str = Field(pattern=r"^[0-9a-f]{64}$")
    tavern_cases: list[TavernPilotCase] = Field(min_length=8, max_length=64)
    planning_cases: list[PlanningPilotCase] = Field(min_length=8, max_length=64)

    @model_validator(mode="after")
    def validate_cases(self) -> "HarnessPilotEvalCasesV1":
        for cases in (self.tavern_cases, self.planning_cases):
            ids = [item.case_id for item in cases]
            if len(ids) != len(set(ids)):
                raise ValueError("harness_pilot_case_id_duplicate")
            if not any(item.split == "held_out" for item in cases):
                raise ValueError("harness_pilot_held_out_split_missing")
            for item in cases:
                if item.tags != sorted(set(item.tags)):
                    raise ValueError("harness_pilot_case_tags_not_canonical")
        expected = canonical_harness_digest(
            {
                "contract": self.review_contract.model_dump(mode="json"),
                "tavern_cases": [
                    item.model_dump(mode="json") for item in self.tavern_cases
                ],
                "planning_cases": [
                    item.model_dump(mode="json") for item in self.planning_cases
                ],
            }
        )
        if self.review_attestation_digest != expected:
            raise ValueError("harness_pilot_review_attestation_digest_mismatch")
        return self


@dataclass(frozen=True)
class HarnessPilotEvalBundle:
    cases: dict[tuple[str, str], tuple[HarnessEvalCaseV1, ...]]
    runs: dict[tuple[str, str], HarnessEvalRunV1]
    executions: dict[tuple[str, str], HarnessEvalExecution]
    baselines: dict[tuple[str, str], HarnessEvalBaselineV1]
    decisions: dict[tuple[str, str], HarnessEvalGateDecisionV1]


class _PilotOperationAuthority:
    def __init__(self, database: Database) -> None:
        self.database = database
        self.repository = HarnessOperationBindingRepository(database)

    def admit(self, *, case, run, repetition_index: int, seed: int):
        identity = canonical_harness_digest(
            {
                "run": run.run_id,
                "case": case.case_digest,
                "repetition": repetition_index,
                "seed": seed,
            }
        )
        if case.workflow == HarnessWorkflow.TAVERN.value:
            kind = HarnessDomainOperationKind.TAVERN_RUN
        elif case.workflow == HarnessWorkflow.STUDY_CHAT.value:
            kind = HarnessDomainOperationKind.STUDY_CHAT
        else:
            kind = HarnessDomainOperationKind.LEARNING_PLAN_GENERATION
        workflow, entry_stage = HARNESS_DOMAIN_OPERATION_ROUTES[kind]
        binding = HarnessOperationBindingV1(
            harness_operation_id=f"harness-operation-{identity[:32]}",
            domain_operation_kind=kind,
            domain_operation_id=f"pilot-{identity[:32]}",
            workflow=workflow,
            entry_stage=entry_stage,
            admitted_at=datetime(2026, 9, 3, tzinfo=UTC),
        )
        existing = self.repository.resolve_harness_id(
            harness_operation_id=binding.harness_operation_id
        )
        if existing is not None:
            if existing != binding:
                raise RuntimeError("harness_pilot_operation_identity_collision")
            return existing
        with self.database.session() as session:
            session.add(
                HarnessOperationBindingRow(
                    **binding.model_dump(mode="json", exclude_none=False)
                )
            )
        return binding

    def resolve_harness_id(self, *, harness_operation_id: str):
        return self.repository.resolve_harness_id(
            harness_operation_id=harness_operation_id
        )


class _TavernPilotGrader:
    contract = TAVERN_GRADER_CONTRACT
    implementation_contract = HarnessContractRef(
        name="TavernIdentityDeterministicGrader",
        version="tavern-identity-deterministic-grader-v1",
    )
    configuration_digest = canonical_harness_digest(
        {"expected_statuses": ["passed", "repaired", "rejected"]}
    )
    kind = "deterministic"

    def grade(self, *, case, candidate_evidence, payload, **_):
        expected = str(payload["expected_status"])
        actual = str((candidate_evidence or {}).get("actual_status", "missing"))
        correct = actual == expected
        is_positive = expected == "passed"
        unsafe = expected in {"repaired", "rejected"}
        is_leak = "prompt_safety" in payload["tags"] or "guidance_leak" in payload["tags"]
        metrics = [
            _boolean_metric(TAVERN_CORRECT_RATE, correct, case.case_digest),
            _boolean_metric(
                TAVERN_FALSE_POSITIVE_RATE,
                is_positive and actual != "passed",
                case.case_digest,
            ),
            _boolean_metric(
                TAVERN_FALSE_NEGATIVE_RATE,
                unsafe and actual == "passed",
                case.case_digest,
            ),
        ]
        if is_leak:
            metrics.append(
                _boolean_metric(
                    TAVERN_PROMPT_LEAK_BLOCK_RATE,
                    actual == "rejected",
                    case.case_digest,
                )
            )
        return _grader_result(
            grader=self,
            case=case,
            passed=correct,
            metrics=metrics,
            evidence={"expected": expected, "actual": actual},
        )


class _PlanningPilotGrader:
    contract = PLANNING_GRADER_CONTRACT
    implementation_contract = HarnessContractRef(
        name="PlanningToolDeterministicGrader",
        version="planning-tool-deterministic-grader-v1",
    )
    configuration_digest = canonical_harness_digest(
        {"checks": ["ok", "error", "grounding", "budget"]}
    )
    kind = "deterministic"

    def grade(self, *, case, candidate_evidence, payload, **_):
        evidence = candidate_evidence or {}
        actual_ok = bool(evidence.get("actual_ok", False))
        actual_error = str(evidence.get("actual_error", ""))
        expected_ok = bool(payload["expected_ok"])
        expected_error = str(payload["expected_error"])
        correct = actual_ok == expected_ok and actual_error == expected_error
        grounded = not actual_ok or bool(evidence.get("grounded", False))
        metrics = [
            _boolean_metric(PLANNING_CORRECT_RATE, correct, case.case_digest),
            _boolean_metric(PLANNING_GROUNDING_RATE, grounded, case.case_digest),
            _boolean_metric(
                PLANNING_INVALID_CALL_RATE,
                not actual_ok,
                case.case_digest,
            ),
        ]
        return _grader_result(
            grader=self,
            case=case,
            passed=correct and grounded,
            metrics=metrics,
            evidence={
                "expected_ok": expected_ok,
                "actual_ok": actual_ok,
                "expected_error": expected_error,
                "actual_error": actual_error,
            },
        )


class _StudyPilotGrader:
    contract = STUDY_GRADER_CONTRACT
    implementation_contract = HarnessContractRef(
        name="StudyChatReplyDeterministicGrader",
        version="study-chat-reply-deterministic-grader-v1",
    )
    configuration_digest = canonical_harness_digest(
        {"statuses": ["accepted", "rejected"]}
    )
    kind = "deterministic"

    def grade(self, *, case, candidate_evidence, payload, **_):
        expected = str(payload["expected_status"])
        actual = str((candidate_evidence or {}).get("actual_status", "missing"))
        correct = actual == expected
        return _grader_result(
            grader=self,
            case=case,
            passed=correct,
            metrics=[_boolean_metric(STUDY_CORRECT_RATE, correct, case.case_digest)],
            evidence={"expected": expected, "actual": actual},
        )


def _boolean_metric(
    contract: HarnessContractRef,
    value: bool,
    evidence: str,
) -> HarnessEvalBooleanMetricV1:
    return HarnessEvalBooleanMetricV1(
        metric=contract,
        value=value,
        evidence_digest=canonical_harness_digest(
            {"metric": contract.model_dump(mode="json"), "value": value, "evidence": evidence}
        ),
    )


def _integer_metric(
    contract: HarnessContractRef,
    value: int,
    unit: Literal["milliseconds", "tool_calls", "provider_calls"],
    evidence: str,
) -> HarnessEvalIntegerMetricV1:
    return HarnessEvalIntegerMetricV1(
        metric=contract,
        unit=unit,
        value=value,
        evidence_digest=canonical_harness_digest(
            {"metric": contract.model_dump(mode="json"), "value": value, "evidence": evidence}
        ),
    )


def _grader_result(*, grader, case, passed: bool, metrics, evidence):
    digest = canonical_harness_digest(evidence)
    return HarnessEvalGraderResultV1(
        grader_result_id=f"grader-result-{canonical_harness_digest({'case': case.case_digest, 'grader': grader.contract.model_dump(mode='json')})[:32]}",
        grader=grader.contract,
        grader_kind="deterministic",
        grader_config_digest=grader.configuration_digest,
        execution_status="completed",
        verdict="passed" if passed else "failed",
        score=1.0 if passed else 0.0,
        metrics=sorted(metrics, key=lambda item: (item.metric.name, item.metric.version)),
        failure_codes=[],
        evidence_digest=digest,
        duration_ms=0,
    )


def _persona(persona_id: str, name: str) -> PersonaProfile:
    return PersonaProfile(
        id=persona_id,
        name=name,
        source="eval_fixture",
        summary=f"{name} 的测试角色",
        relationship="同伴",
        learner_address="你",
        system_prompt="保持角色身份稳定。",
        reference_hints=[],
        slots=[],
        available_emotions=["calm"],
        available_actions=["pause"],
        default_speech_style="warm",
    )


def _participant(persona: PersonaProfile, order: int) -> TavernParticipantRecord:
    return TavernParticipantRecord(
        room_id="pilot-room",
        persona_id=persona.id,
        display_order=order,
        display_name=persona.name,
        persona_snapshot=persona,
        prompt_hash=persona_prompt_hash(persona.model_dump(mode="json")),
        joined_at="2026-09-03T00:00:00+00:00",
    )


def _execute_tavern(*, payload, run, **_):
    case = TavernPilotCase.model_validate(payload)
    actor = _participant(_persona(case.actor_id, case.actor_name), 0)
    other = _participant(_persona(case.other_id, case.other_name), 1)
    reply = TavernActorReply(
        text=case.text,
        mood="calm",
        action=case.action,
        speech_style="warm",
        delivery_cue="自然停顿",
        state_commentary="保持当前身份",
        addressed_participant_ids=case.addressed_participant_ids,
    )
    started = time.perf_counter()
    try:
        _, trace = TavernActorHarness().validate_and_repair(
            reply=reply,
            actor=actor,
            participants=[actor, other],
            recent_messages=[],
            user_message=case.user_message,
            guidance=case.guidance,
            allowed_target_ids=[actor.persona_id, other.persona_id],
            policy=TavernHarnessPolicy(),
        )
        actual = trace.status.value
    except TavernHarnessViolation as error:
        trace = error.trace
        actual = "rejected"
    duration_ms = max(0, int((time.perf_counter() - started) * 1000))
    return HarnessEvalCandidateResult(
        candidate_outcome="repaired" if actual == "repaired" else "passed",
        raw_schema_valid=True,
        final_schema_valid=True,
        trace_contract=run.tested_system.harness_contract,
        trace_digest=canonical_harness_digest(trace.model_dump(mode="json")),
        evidence_digest=canonical_harness_digest(
            {"status": actual, "checks": [(item.name, item.status.value, item.code) for item in trace.checks]}
        ),
        duration_ms=duration_ms,
        grader_evidence={"actual_status": actual},
    )


def _execute_planning(*, payload, run, **_):
    case = PlanningPilotCase.model_validate(payload)
    unit = StudyUnitRecord(
        id="unit-1",
        document_id="document-1",
        title="Vector Spaces",
        page_start=1,
        page_end=4,
        source_section_ids=["section-1"],
        summary="Basis, span, and linear independence.",
    )
    runtime = build_plan_tool_runtime(
        study_units=[unit],
        detail_map=build_study_unit_detail_map(study_units=[unit]),
        disabled_tools=set(case.disabled_tools),
    )
    runtime.begin_round()
    started = time.perf_counter()
    execution = None
    for index in range(case.repeat_count):
        execution = runtime.execute_tool_call(
            {
                "id": f"pilot-call-{index + 1}",
                "type": "function",
                "function": {
                    "name": case.tool_name,
                    "arguments": case.arguments_json,
                },
            }
        )
    assert execution is not None
    duration_ms = max(0, int((time.perf_counter() - started) * 1000))
    result = execution.result
    actual_ok = result.get("ok") is True
    actual_error = str(result.get("error") or "")
    grounded = not actual_ok or (
        case.tool_name != "get_study_unit_detail"
        or (
            isinstance(result.get("detail"), dict)
            and result["detail"].get("unit_id") == "unit-1"
        )
    )
    latency_contract = HarnessContractRef(
        name=f"planning_{case.tool_name}_latency_ms",
        version="planning-tool-latency-ms-v1",
    )
    metrics = (
        _integer_metric(
            PLANNING_TOOL_CALL_COUNT,
            case.repeat_count,
            "tool_calls",
            execution.trace_summary,
        ),
        _integer_metric(
            PLANNING_PROVIDER_CALL_COUNT,
            0,
            "provider_calls",
            execution.trace_summary,
        ),
        _integer_metric(
            latency_contract,
            duration_ms,
            "milliseconds",
            execution.trace_summary,
        ),
    )
    evidence = {
        "tool": execution.tool_name,
        "ok": actual_ok,
        "error": actual_error,
        "argument_contract": execution.argument_contract_version,
        "result_contract": execution.result_contract_version,
        "trace_result": execution.trace_result,
    }
    return HarnessEvalCandidateResult(
        candidate_outcome="passed",
        raw_schema_valid=True,
        final_schema_valid=True,
        trace_contract=run.tested_system.harness_contract,
        trace_digest=canonical_harness_digest(evidence),
        metrics=tuple(sorted(metrics, key=lambda item: (item.metric.name, item.metric.version))),
        evidence_digest=canonical_harness_digest(evidence),
        duration_ms=duration_ms,
        grader_evidence={
            "actual_ok": actual_ok,
            "actual_error": actual_error,
            "grounded": grounded,
        },
    )


def _study_candidate_payload(scenario: str) -> dict[str, object]:
    payload: dict[str, object] = {
        "reply": "A basis is linearly independent and spans the space.",
        "citations": [
            {
                "section_id": "unit-1",
                "title": "Vector Spaces",
                "page_start": 1,
                "page_end": 2,
                "source_kind": "document",
                "source_id": "section-1",
            }
        ],
        "character_events": [
            {
                "emotion": "calm",
                "action": "point",
                "speech_style": "steady",
                "scene_hint": "",
                "line_segment_id": "session-eval:chat:0",
                "timing_hint": "normal",
            }
        ],
        "tool_calls": [
            {
                "tool_call_id": "tool-call-1",
                "tool_name": "read_session_memory",
                "arguments_json": "{}",
                "argument_contract_version": "study-tool-arguments-v1",
                "result_contract_version": "study-tool-result-v1",
                "result_summary": "memory read",
                "result_json": "{}",
            }
        ],
    }
    if scenario == "empty_reply":
        payload["reply"] = ""
    elif scenario == "citation_source":
        payload["citations"][0]["source_kind"] = ""  # type: ignore[index]
    elif scenario == "character_event":
        payload["character_events"][0]["action"] = ""  # type: ignore[index]
    elif scenario == "tool_identity":
        payload["tool_calls"][0]["tool_call_id"] = ""  # type: ignore[index]
    elif scenario == "tool_contract":
        payload["tool_calls"][0]["result_contract_version"] = ""  # type: ignore[index]
    elif scenario == "tool_json":
        payload["tool_calls"][0]["result_json"] = "[1,2]"  # type: ignore[index]
    elif scenario == "extra_field":
        payload["server_owned_revision"] = 99
    return payload


def _execute_study(*, payload, run, **_):
    case = StudyPilotCase.model_validate(payload)
    started = time.perf_counter()
    try:
        StudyV3ReplyAdapter().decode(_study_candidate_payload(case.scenario))
        actual = "accepted"
    except (TypeError, ValueError):
        actual = "rejected"
    duration_ms = max(0, int((time.perf_counter() - started) * 1000))
    evidence = {"scenario": case.scenario, "actual_status": actual}
    return HarnessEvalCandidateResult(
        candidate_outcome="passed",
        raw_schema_valid=True,
        final_schema_valid=True,
        trace_contract=run.tested_system.harness_contract,
        trace_digest=canonical_harness_digest(evidence),
        evidence_digest=canonical_harness_digest(evidence),
        duration_ms=duration_ms,
        grader_evidence={"actual_status": actual},
    )


def _load_fixtures() -> HarnessPilotEvalCasesV1:
    return HarnessPilotEvalCasesV1.model_validate_json(
        FIXTURE_PATH.read_text(encoding="utf-8")
    )


def _load_study_fixtures() -> StudyPilotEvalCasesV1:
    return StudyPilotEvalCasesV1.model_validate_json(
        STUDY_FIXTURE_PATH.read_text(encoding="utf-8")
    )


def _case(
    *,
    suite: HarnessContractRef,
    workflow: HarnessWorkflow,
    stage: HarnessStage,
    eval_route: str,
    payload: TavernPilotCase | PlanningPilotCase | StudyPilotCase,
    invariant: HarnessContractRef,
    grader: HarnessContractRef,
    review_contract: HarnessContractRef,
    review_attestation_digest: str,
) -> HarnessEvalCaseV1:
    serialized = payload.model_dump(mode="json")
    held_out = payload.split == "held_out"
    draft = {
        "schema_name": "HarnessEvalCase",
        "schema_version": "harness-eval-case-v1",
        "case_id": payload.case_id,
        "case_version": f"{payload.case_id}-v1",
        "case_digest": "0" * 64,
        "suite": suite.model_dump(mode="json"),
        "workflow": workflow.value,
        "stage": stage.value,
        "eval_route": eval_route,
        "source": HarnessEvalFixtureSourceV1(
            fixture_id=payload.case_id,
            payload_contract=PILOT_FIXTURE_CONTRACT,
            payload_digest=canonical_harness_digest(serialized),
        ).model_dump(mode="json"),
        "provenance": HarnessEvalProvenanceV1(
            source_kind="independently_reviewed" if held_out else "developer_authored",
            review_status="independently_reviewed" if held_out else "developer_reviewed",
            review_contract=review_contract if held_out else None,
            attestation_digest=review_attestation_digest if held_out else None,
        ).model_dump(mode="json"),
        "sensitivity": "internal",
        "split": payload.split,
        "tags": payload.tags,
        "expected_invariants": [
            HarnessEvalExpectedInvariantV1(
                invariant=invariant,
                expected_outcome="passed",
            ).model_dump(mode="json")
        ],
        "grader_refs": [grader.model_dump(mode="json")],
    }
    draft["case_digest"] = canonical_harness_eval_case_digest(draft)
    return HarnessEvalCaseV1.model_validate(draft)


def _system_config(*, suite: HarnessContractRef) -> HarnessEvalSystemConfigV1:
    if suite == TAVERN_IDENTITY_EVAL_SUITE:
        values = {
            "harness_contract": HarnessContractRef(
                name="HarnessTraceV1",
                version="tavern-harness-trace-v1",
            ),
            "provider_adapter_contract": HarnessContractRef(
                name="TavernActorHarness",
                version="tavern-actor-workflow-adapter-v1",
            ),
            "provider_model_contract": HarnessContractRef(
                name="DeterministicFixtureReply",
                version="deterministic-fixture-reply-v1",
            ),
            "input_contract": PILOT_FIXTURE_CONTRACT,
            "output_contract": HarnessContractRef(
                name="TavernActorValidationOutcome",
                version="tavern-actor-validation-outcome-v1",
            ),
            "prompt_contract": HarnessContractRef(
                name="TavernActorPrompt",
                version="tavern-actor-v1",
            ),
            "policy_contract": HarnessContractRef(
                name="TavernHarnessPolicy",
                version="tavern-harness-v1",
            ),
            "toolset_contract": None,
            "component_contracts": [
                HarnessContractRef(
                    name="tavern_actor_prompt",
                    version="tavern-actor-v1",
                ),
                HarnessContractRef(
                    name="tavern_persona_compiler",
                    version="tavern-persona-compiler-v1",
                ),
                HarnessContractRef(
                    name="tavern_scheduler",
                    version="tavern-schedule-v1",
                ),
            ],
            "max_tool_calls": 0,
        }
    elif suite == PLANNING_TOOL_EVAL_SUITE:
        values = {
            "harness_contract": HarnessContractRef(
                name="PlanningToolExecutionProjection",
                version="planning-tool-execution-trace-v1",
            ),
            "provider_adapter_contract": HarnessContractRef(
                name="PlanToolRuntime",
                version="planning-tool-runtime-v1",
            ),
            "provider_model_contract": HarnessContractRef(
                name="DeterministicToolCallFixture",
                version="deterministic-tool-call-fixture-v1",
            ),
            "input_contract": PILOT_FIXTURE_CONTRACT,
            "output_contract": HarnessContractRef(
                name="PlanningToolExecution",
                version="planning-tool-execution-v1",
            ),
            "prompt_contract": None,
            "policy_contract": HarnessContractRef(
                name="PlanningToolExecutionPolicy",
                version="planning-tool-execution-policy-v1",
            ),
            "toolset_contract": HarnessContractRef(
                name="ToolManifestRegistry",
                version="tool-manifest-v1",
            ),
            "component_contracts": [
                HarnessContractRef(
                    name="planning_tool_runtime",
                    version="planning-tool-runtime-v1",
                ),
                HarnessContractRef(
                    name="planning_toolset",
                    version="planning-toolset-v1",
                ),
            ],
            "max_tool_calls": 3,
        }
    else:
        values = {
            "harness_contract": HarnessContractRef(
                name="StudyChatReply",
                version="study-chat-reply-trace-v1",
            ),
            "provider_adapter_contract": HarnessContractRef(
                name="StudyChatWorkflowAdapter",
                version="study-chat-workflow-adapter-v1",
            ),
            "provider_model_contract": HarnessContractRef(
                name="DeterministicStudyReplyFixture",
                version="deterministic-study-reply-fixture-v1",
            ),
            "input_contract": PILOT_FIXTURE_CONTRACT,
            "output_contract": HarnessContractRef(
                name="StudyChatRuntimeOutput",
                version="study-chat-runtime-output-v1",
            ),
            "prompt_contract": HarnessContractRef(
                name="StudyChatPrompt",
                version="study-chat-prompt-v1",
            ),
            "policy_contract": HarnessContractRef(
                name="StudyChatHarnessPolicy",
                version="study-chat-harness-v1",
            ),
            "toolset_contract": HarnessContractRef(
                name="ToolManifestRegistry",
                version="tool-manifest-v1",
            ),
            "component_contracts": [
                HarnessContractRef(
                    name="study_chat_prompt",
                    version="study-chat-prompt-v1",
                ),
                HarnessContractRef(
                    name="study_chat_toolset",
                    version="study-chat-toolset-v2",
                ),
                HarnessContractRef(
                    name="study_visual_grounding",
                    version="study-visual-grounding-v1",
                ),
            ],
            "max_tool_calls": 1,
        }
    return HarnessEvalSystemConfigV1(
        workflow_manifest_contract=PILOT_WORKFLOW_MANIFEST_CONTRACT,
        harness_contract=values["harness_contract"],
        provider_adapter_contract=values["provider_adapter_contract"],
        provider_model_contract=values["provider_model_contract"],
        input_contract=values["input_contract"],
        output_contract=values["output_contract"],
        prompt_contract=values["prompt_contract"],
        policy_contract=values["policy_contract"],
        toolset_contract=values["toolset_contract"],
        component_contracts=values["component_contracts"],
        reasoning=HarnessEvalReasoningConfigV1(
            mode="not_supported",
            budget_tokens=None,
        ),
        sampling=HarnessEvalSamplingConfigV1(
            temperature=0.0,
            top_p=1.0,
            seed_strategy="per_sample",
            fixed_seed=None,
        ),
        budgets=HarnessEvalExecutionBudgetV1(
            max_attempts=3,
            max_repairs=2,
            max_tool_calls=values["max_tool_calls"],
            max_provider_calls=0,
            max_input_tokens=8_192,
            max_output_tokens=2_048,
            max_wall_time_ms=30_000,
            per_call_timeout_ms=10_000,
            max_cost_micro_usd=0,
        ),
        source_revision=(
            "harness-wave-3-study-eval-v1"
            if suite == STUDY_CHAT_EVAL_SUITE
            else "harness-wave-2-pilot-v1"
        ),
        worktree_state="clean",
        source_tree_digest=None,
    )


def _run(*, suite: HarnessContractRef, cases: tuple[HarnessEvalCaseV1, ...]):
    system = _system_config(suite=suite)
    environment = HarnessEvalEnvironmentV1(
        environment_contract=PILOT_ENVIRONMENT_CONTRACT,
        platform="portable",
        architecture="portable",
        python_version="3.12",
        node_version=None,
        database_kind="sqlite",
        provider_mode="mock",
    )
    case_set_digest = canonical_harness_digest(
        [item.model_dump(mode="json", exclude_none=False) for item in cases]
    )
    suite_manifest_digest = canonical_harness_digest(
        {
            "suite": suite.model_dump(mode="json"),
            "cases": [item.case_digest for item in cases],
        }
    )
    run_id = f"harness-eval-run-{canonical_harness_digest({'suite': suite.model_dump(mode='json'), 'cases': case_set_digest, 'source': system.source_revision})[:32]}"
    draft = {
        "schema_name": "HarnessEvalRun",
        "schema_version": "harness-eval-run-v1",
        "run_id": run_id,
        "suite": suite.model_dump(mode="json"),
        "suite_manifest_digest": suite_manifest_digest,
        "case_set_digest": case_set_digest,
        "execution_mode": "fixture",
        "splits": ["held_out", "regression"],
        "repetition_count": 1,
        "seeds": [17],
        "runner_contract": PILOT_RUNNER_CONTRACT.model_dump(mode="json"),
        "failure_taxonomy_contract": HARNESS_EVAL_FAILURE_TAXONOMY_CONTRACT.model_dump(mode="json"),
        "grader_registry_contract": PILOT_GRADER_REGISTRY_CONTRACT.model_dump(mode="json"),
        "tested_system": system.model_dump(mode="json", exclude_none=False),
        "tested_system_config_digest": canonical_harness_eval_system_config_digest(system),
        "environment": environment.model_dump(mode="json", exclude_none=False),
        "environment_digest": canonical_harness_eval_environment_digest(environment),
        "admitted_at": "2026-09-03T00:00:00Z",
        "run_digest": "0" * 64,
    }
    draft["run_digest"] = canonical_harness_eval_run_digest(draft)
    return HarnessEvalRunV1.model_validate(draft)


def _registration(
    *,
    suite: HarnessContractRef,
    workflow: HarnessWorkflow,
    stage: HarnessStage,
    route: str,
    run: HarnessEvalRunV1,
    cases: tuple[HarnessEvalCaseV1, ...],
) -> HarnessEvalSuiteRegistration:
    values = [
        PILOT_SUITE_REGISTRY_CONTRACT,
        suite,
        PILOT_RUNNER_CONTRACT,
        PILOT_GRADER_REGISTRY_CONTRACT,
        run.failure_taxonomy_contract,
        run.environment.environment_contract,
        run.tested_system.workflow_manifest_contract,
        run.tested_system.harness_contract,
        run.tested_system.provider_adapter_contract,
        run.tested_system.provider_model_contract,
        run.tested_system.input_contract,
        run.tested_system.output_contract,
        *run.tested_system.component_contracts,
        PILOT_FIXTURE_CONTRACT,
        *(item.grader_refs[0] for item in cases),
        *(item.expected_invariants[0].invariant for item in cases),
    ]
    for optional in (
        run.tested_system.prompt_contract,
        run.tested_system.policy_contract,
        run.tested_system.toolset_contract,
    ):
        if optional is not None:
            values.append(optional)
    known = {
        (item.name, item.version): item
        for item in values
    }
    return HarnessEvalSuiteRegistration(
        registration_contract=PILOT_SUITE_REGISTRY_CONTRACT,
        suite=suite,
        workflow=workflow,
        stage=stage,
        eval_route=route,
        runner_contract=PILOT_RUNNER_CONTRACT,
        grader_registry_contract=PILOT_GRADER_REGISTRY_CONTRACT,
        tested_system=run.tested_system,
        known_contracts=tuple(known[key] for key in sorted(known)),
        allowed_execution_modes=("fixture",),
    )


def _current_planning_cases(fixture: HarnessPilotEvalCasesV1) -> list[PlanningPilotCase]:
    # Keep the independently reviewed historical book immutable. Only this
    # developer-authored budget regression changes with the reviewed quota.
    replacement = PlanningPilotCase.model_validate_json(
        FIXTURE_PATH.with_name("planning-detail-budget-regression-v2.json").read_text(encoding="utf-8")
    )
    if replacement.split != "regression":
        raise ValueError("planning_budget_replacement_must_be_regression")
    return [replacement if item.case_id == "planning-tool-duplicate-call-001" else item
        for item in fixture.planning_cases]


def build_harness_pilot_runner() -> HarnessEvalRunner:
    fixture = _load_fixtures()
    study_fixture = _load_study_fixtures()
    tavern_cases = tuple(sorted((
        _case(
            suite=TAVERN_IDENTITY_EVAL_SUITE,
            workflow=HarnessWorkflow.TAVERN,
            stage=HarnessStage.TAVERN_ACTOR_REPLY,
            eval_route="tavern.actor_reply",
            payload=item,
            invariant=TAVERN_OUTCOME_INVARIANT,
            grader=TAVERN_GRADER_CONTRACT,
            review_contract=fixture.review_contract,
            review_attestation_digest=fixture.review_attestation_digest,
        )
        for item in fixture.tavern_cases
    ), key=lambda item: (item.case_id, item.case_version)))
    planning_cases = tuple(sorted((
        _case(
            suite=PLANNING_TOOL_EVAL_SUITE,
            workflow=HarnessWorkflow.PLANNING,
            stage=HarnessStage.PLANNING_TOOL_EXECUTION,
            eval_route="planning.tool_execution",
            payload=item,
            invariant=PLANNING_OUTCOME_INVARIANT,
            grader=PLANNING_GRADER_CONTRACT,
            review_contract=fixture.review_contract,
            review_attestation_digest=fixture.review_attestation_digest,
        )
        for item in _current_planning_cases(fixture)
    ), key=lambda item: (item.case_id, item.case_version)))
    study_cases = tuple(
        sorted(
            (
                _case(
                    suite=STUDY_CHAT_EVAL_SUITE,
                    workflow=HarnessWorkflow.STUDY_CHAT,
                    stage=HarnessStage.STUDY_CHAT_REPLY,
                    eval_route="study_chat.reply",
                    payload=item,
                    invariant=STUDY_OUTCOME_INVARIANT,
                    grader=STUDY_GRADER_CONTRACT,
                    review_contract=study_fixture.review_contract,
                    review_attestation_digest=(
                        study_fixture.review_attestation_digest
                    ),
                )
                for item in study_fixture.study_cases
            ),
            key=lambda item: (item.case_id, item.case_version),
        )
    )
    runs = {
        (TAVERN_IDENTITY_EVAL_SUITE.name, TAVERN_IDENTITY_EVAL_SUITE.version): _run(
            suite=TAVERN_IDENTITY_EVAL_SUITE,
            cases=tavern_cases,
        ),
        (PLANNING_TOOL_EVAL_SUITE.name, PLANNING_TOOL_EVAL_SUITE.version): _run(
            suite=PLANNING_TOOL_EVAL_SUITE,
            cases=planning_cases,
        ),
        (STUDY_CHAT_EVAL_SUITE.name, STUDY_CHAT_EVAL_SUITE.version): _run(
            suite=STUDY_CHAT_EVAL_SUITE,
            cases=study_cases,
        ),
    }
    suites = HarnessEvalSuiteRegistry(PILOT_SUITE_REGISTRY_CONTRACT)
    suites.register(
        _registration(
            suite=TAVERN_IDENTITY_EVAL_SUITE,
            workflow=HarnessWorkflow.TAVERN,
            stage=HarnessStage.TAVERN_ACTOR_REPLY,
            route="tavern.actor_reply",
            run=runs[(TAVERN_IDENTITY_EVAL_SUITE.name, TAVERN_IDENTITY_EVAL_SUITE.version)],
            cases=tavern_cases,
        )
    )
    suites.register(
        _registration(
            suite=STUDY_CHAT_EVAL_SUITE,
            workflow=HarnessWorkflow.STUDY_CHAT,
            stage=HarnessStage.STUDY_CHAT_REPLY,
            route="study_chat.reply",
            run=runs[
                (STUDY_CHAT_EVAL_SUITE.name, STUDY_CHAT_EVAL_SUITE.version)
            ],
            cases=study_cases,
        )
    )
    suites.register(
        _registration(
            suite=PLANNING_TOOL_EVAL_SUITE,
            workflow=HarnessWorkflow.PLANNING,
            stage=HarnessStage.PLANNING_TOOL_EXECUTION,
            route="planning.tool_execution",
            run=runs[(PLANNING_TOOL_EVAL_SUITE.name, PLANNING_TOOL_EVAL_SUITE.version)],
            cases=planning_cases,
        )
    )
    graders = HarnessEvalGraderRegistry(PILOT_GRADER_REGISTRY_CONTRACT)
    graders.register(_TavernPilotGrader())
    graders.register(_PlanningPilotGrader())
    graders.register(_StudyPilotGrader())
    temporary = TemporaryDirectory()
    database = Database(f"sqlite:///{Path(temporary.name) / 'pilots.sqlite3'}")
    database.create_schema()
    authority = _PilotOperationAuthority(database)
    payloads = {
        item.case_id: item.model_dump(mode="json")
        for item in (
            *fixture.tavern_cases,
            *_current_planning_cases(fixture),
            *study_fixture.study_cases,
        )
    }

    def resolve(case: HarnessEvalCaseV1) -> HarnessEvalFixturePayload:
        payload = payloads[case.source.fixture_id]
        return HarnessEvalFixturePayload(
            payload=payload,
            payload_digest=canonical_harness_digest(payload),
        )

    runner = HarnessEvalRunner(
        suite_registry=suites,
        adapters=(
            HarnessEvalRouteAdapter(
                suite=TAVERN_IDENTITY_EVAL_SUITE,
                eval_route="tavern.actor_reply",
                operation_admitter=authority.admit,
                fixture_resolver=resolve,
                synthetic_resolver=None,
                execute=_execute_tavern,
            ),
            HarnessEvalRouteAdapter(
                suite=PLANNING_TOOL_EVAL_SUITE,
                eval_route="planning.tool_execution",
                operation_admitter=authority.admit,
                fixture_resolver=resolve,
                synthetic_resolver=None,
                execute=_execute_planning,
            ),
            HarnessEvalRouteAdapter(
                suite=STUDY_CHAT_EVAL_SUITE,
                eval_route="study_chat.reply",
                operation_admitter=authority.admit,
                fixture_resolver=resolve,
                synthetic_resolver=None,
                execute=_execute_study,
            ),
        ),
        graders=graders,
        operation_resolver=authority,
    )
    runner._pilot_resources = (
        temporary,
        database,
        fixture,
        study_fixture,
        runs,
        tavern_cases,
        planning_cases,
        study_cases,
    )
    return runner


def execute_harness_pilot_bundle(
    *,
    refresh_baselines: bool = False,
) -> HarnessPilotEvalBundle:
    runner = build_harness_pilot_runner()
    (
        _,
        _,
        fixture,
        study_fixture,
        runs,
        tavern_cases,
        planning_cases,
        study_cases,
    ) = runner._pilot_resources
    cases = {
        (TAVERN_IDENTITY_EVAL_SUITE.name, TAVERN_IDENTITY_EVAL_SUITE.version): tavern_cases,
        (PLANNING_TOOL_EVAL_SUITE.name, PLANNING_TOOL_EVAL_SUITE.version): planning_cases,
        (STUDY_CHAT_EVAL_SUITE.name, STUDY_CHAT_EVAL_SUITE.version): study_cases,
    }
    executions = {}
    baselines = {}
    decisions = {}
    for suite in (
        TAVERN_IDENTITY_EVAL_SUITE,
        PLANNING_TOOL_EVAL_SUITE,
        STUDY_CHAT_EVAL_SUITE,
    ):
        key = (suite.name, suite.version)
        execution = runner.run(
            runs[key],
            cases[key],
            selected_suites=[suite],
            release_gate=True,
            deterministic_gate=True,
        )
        executions[key] = execution
        if suite == TAVERN_IDENTITY_EVAL_SUITE:
            suite_threshold = TAVERN_CORRECT_RATE
        elif suite == PLANNING_TOOL_EVAL_SUITE:
            suite_threshold = PLANNING_CORRECT_RATE
        else:
            suite_threshold = STUDY_CORRECT_RATE
        thresholds = [
            HarnessEvalMetricThresholdV1(
                metric=CANDIDATE_PASS_RATE,
                direction="minimum",
                absolute_value=1.0,
                max_regression_ratio=0.0,
            ),
            HarnessEvalMetricThresholdV1(
                metric=FINAL_SCHEMA_VALID_RATE,
                direction="minimum",
                absolute_value=1.0,
                max_regression_ratio=0.0,
            ),
            HarnessEvalMetricThresholdV1(
                metric=suite_threshold,
                direction="minimum",
                absolute_value=1.0,
                max_regression_ratio=0.0,
            ),
        ]
        if refresh_baselines:
            baseline = build_harness_eval_baseline(
                baseline_version=f"{suite.version}-baseline-v2" if suite == PLANNING_TOOL_EVAL_SUITE else f"{suite.version}-baseline-v1",
                run=runs[key],
                report=execution.report,
                minimum_sample_count=len(cases[key]),
                thresholds=sorted(
                    thresholds,
                    key=lambda item: (item.metric.name, item.metric.version),
                ),
                review_contract=(
                    HarnessContractRef(name="PlanningDetailBudgetMaintainerReview", version="planning-detail-budget-review-v2")
                    if suite == PLANNING_TOOL_EVAL_SUITE else
                    study_fixture.review_contract
                    if suite == STUDY_CHAT_EVAL_SUITE
                    else fixture.review_contract
                ),
                review_attestation_digest=(
                    canonical_harness_digest({"case_id": "planning-tool-detail-round-limit-002",
                        "same_round_limit": 3, "operation_limit": 4, "review_kind": "developer_reviewed"})
                    if suite == PLANNING_TOOL_EVAL_SUITE else
                    study_fixture.review_attestation_digest
                    if suite == STUDY_CHAT_EVAL_SUITE
                    else fixture.review_attestation_digest
                ),
            )
        else:
            baseline = HarnessEvalBaselineV1.model_validate_json(
                (BASELINE_ROOT / _baseline_directory_name(suite.name) / "baseline.json").read_text(
                    encoding="utf-8"
                )
            )
        baselines[key] = baseline
        decisions[key] = evaluate_harness_eval_baseline(
            baseline=baseline,
            candidate_run=runs[key],
            candidate_report=execution.report,
        )
    return HarnessPilotEvalBundle(
        cases=cases,
        runs=runs,
        executions=executions,
        baselines=baselines,
        decisions=decisions,
    )


def _baseline_directory_name(suite_name: str) -> str:
    return "planning_tool_eval_detail_budget_v2" if suite_name == PLANNING_TOOL_EVAL_SUITE.name else suite_name


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Wave 2 deterministic Harness pilot gates.")
    parser.add_argument("--profile", choices=("pr",), default="pr")
    parser.add_argument("--output-dir", type=Path)
    parser.add_argument("--refresh-baselines", action="store_true")
    args = parser.parse_args(argv)
    bundle = execute_harness_pilot_bundle(
        refresh_baselines=args.refresh_baselines,
    )
    output = BASELINE_ROOT if args.refresh_baselines else args.output_dir
    if output is not None:
        output.mkdir(parents=True, exist_ok=True)
        for key in sorted(bundle.executions):
            name = key[0]
            suite_dir = output / (_baseline_directory_name(name) if args.refresh_baselines else name)
            suite_dir.mkdir(parents=True, exist_ok=True)
            (suite_dir / "raw-samples.json").write_text(
                json.dumps(bundle.executions[key].raw_samples_json(), sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            (suite_dir / "aggregate.json").write_text(
                json.dumps(bundle.executions[key].aggregate_json(), sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            (suite_dir / "baseline.json").write_text(
                json.dumps(bundle.baselines[key].model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
            (suite_dir / "gate-decision.json").write_text(
                json.dumps(bundle.decisions[key].model_dump(mode="json"), sort_keys=True, separators=(",", ":")) + "\n",
                encoding="utf-8",
            )
    summary = {
        name: {
            "report": bundle.executions[key].report.status,
            "samples": bundle.executions[key].report.sample_count,
            "gate": bundle.decisions[key].status,
        }
        for key in sorted(bundle.executions)
        for name in [key[0]]
    }
    print(json.dumps(summary, sort_keys=True))
    return 0 if all(item.status == "passed" for item in bundle.decisions.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
