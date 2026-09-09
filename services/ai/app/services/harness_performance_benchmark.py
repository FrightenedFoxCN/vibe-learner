"""Local Wave 5 measurements. No provider import, credentials, or model calls."""
from __future__ import annotations

import argparse
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
import hashlib
from importlib.metadata import version
import json
import math
from pathlib import Path
import platform
import subprocess
from tempfile import TemporaryDirectory
import time

from sqlalchemy import event
import tiktoken

from app.models.domain import PersonaProfile, SceneProfileRecord, StudyUnitRecord
from app.models.harness import HarnessArtifactType, HarnessWorkflow, canonical_harness_digest
from app.models.harness_artifact_access import HarnessArtifactGrantScopeV1, HarnessArtifactPermission, HarnessArtifactResolveRequestV1
from app.models.harness_operation import HarnessDomainOperationKind
from app.models.harness_performance import HARNESS_PERFORMANCE_BUDGET_VERSION, canonical_byte_count
from app.models.tavern import TavernActorReply, TavernAuthorKind, TavernMessageRecord, TavernParticipantRecord
from app.models.tavern_integrity import persona_prompt_hash
from app.models.tool_manifest import TOOL_MANIFEST_ENTRIES
from app.persistence.database import Database
from app.services.harness_broad_adoption import (
    HarnessProposalRuntimeService, PERSONA_SNAPSHOT_CONTRACT,
    PersonaCardContentProposalV1, PersonaGenerationInputManifest, PersonaGenerationProposalV1,
)
from app.services.plan_prompt import build_study_unit_detail_map
from app.services.plan_tool_runtime import build_plan_tool_runtime
from app.services.prompt_loader import load_prompt_template
from app.services.tavern_prompt import preflight_tavern_actor_prompt


FIXTURE_VERSION = "harness-local-performance-fixture-v1"
REPORT_VERSION = "harness-local-performance-report-v1"
WARMUPS = 5
# Named local ceilings; never compare timings without the environment below.
P95_LIMITS_MS = {"runtime": 500, "resolver_1": 100, "resolver_8": 300, "resolver_64": 1500,
                 "resolver_1_before": 100, "resolver_8_before": 300, "resolver_64_before": 1500,
                 "tavern": 1500, "planning_before": 100, "planning_after": 100}


def summarize(samples: list[dict], key: str = "duration_ms") -> dict:
    values = sorted(s[key] for s in samples)
    return {"sample_count": len(values), "p50": values[math.ceil(len(values) * .50) - 1],
            "p95": values[math.ceil(len(values) * .95) - 1], "max": max(values)}


def timed(callback, count: int, sql_counter: list[int] | None = None) -> list[dict]:
    samples = []
    for index in range(WARMUPS + count):
        if sql_counter is not None:
            sql_counter[0] = 0
        started = time.perf_counter_ns()
        detail = callback()
        duration_ms = (time.perf_counter_ns() - started) / 1_000_000
        if index >= WARMUPS:
            samples.append({"duration_ms": duration_ms, **detail,
                            **({"sql_statements": sql_counter[0]} if sql_counter is not None else {})})
    return samples


def tavern_fixture():
    now = "2026-09-08T00:00:00Z"
    participants = []
    for i in range(6):
        persona = PersonaProfile(
            id=f"benchmark-persona-{i}", name=f"旅人{i}", source="user",
            summary="Synthetic bilingual traveler. 合成角色简介。" * 60,
            relationship="同行者", learner_address="你", system_prompt="保持自己的身份。" * 80,
            reference_hints=[], slots=[], available_emotions=["calm"], available_actions=["pause"],
            default_speech_style="warm",
        )
        participants.append(TavernParticipantRecord(
            room_id="benchmark-room", persona_id=persona.id, display_order=i,
            display_name=persona.name, persona_snapshot=persona,
            prompt_hash=persona_prompt_hash(persona.model_dump(mode="json")), joined_at=now,
        ))
    messages = [TavernMessageRecord(
        id=f"benchmark-message-{i}", room_id="benchmark-room", sequence=i + 1,
        author_kind=TavernAuthorKind.USER,
        content=("讨论古城的地图与天气。 Discuss the route and evidence. " * 200)[:8000], created_at=now,
    ) for i in range(40)]
    return dict(persona=participants[0].persona_snapshot, participants=participants,
                scene_profile=SceneProfileRecord(scene_id="benchmark-scene", scene_name="古城", title="古城",
                    summary="A synthetic city. 合成场景。" * 800),
                recent_messages=messages, user_message="大家接着讨论。", guidance="保持角色连续性。",
                allowed_target_ids=[p.persona_id for p in participants],
                actor_reply_schema=json.dumps(TavernActorReply.transport_json_schema(), ensure_ascii=False, sort_keys=True))


def planning_fixture():
    units = [StudyUnitRecord(id=f"unit-{i}", document_id="benchmark-document", title=f"Unit {i}",
        page_start=i + 1, page_end=i + 1, source_section_ids=[], summary="Linear algebra.") for i in range(32)]
    detail = build_study_unit_detail_map(study_units=units)
    calls = [{"id": f"benchmark-call-{i}", "type": "function", "function": {
        "name": "get_study_unit_detail", "arguments": json.dumps({"study_unit_id": f"unit-{i}", "focus": ""})}}
        for i in range(1)]
    calls.append({"id": "benchmark-estimate", "type": "function", "function": {
        "name": "estimate_plan_completion", "arguments": "{}"}})
    def run():
        runtime = build_plan_tool_runtime(study_units=units, detail_map=detail)
        runtime.begin_round()
        results = [runtime.execute_tool_call(call) for call in calls]
        assert all(r.result.get("ok") is True for r in results)
        assert [r.tool_call_id for r in results] == [c["id"] for c in calls]
        assert results[0].result["detail"]["unit_id"] == "unit-0"
        return {"tool_calls": len(results), "provider_calls": 0, "tool_rounds": 1,
                "grounding_valid": True, "result_digest": canonical_harness_digest([r.result for r in results])}
    return run


def benchmark(count: int) -> dict:
    encoding = tiktoken.get_encoding("cl100k_base")
    fixture = tavern_fixture()
    raw = {}
    # Encoding is explicitly named; these are content tokens, not a billed
    # provider chat-wrapper token count or a measured provider latency.
    def prompt_run():
        result = preflight_tavern_actor_prompt(**fixture)
        recovery = load_prompt_template("tavern_actor_prompt.txt").require("recovery").replace(
            "{{ACTOR_REPLY_SCHEMA}}", fixture["actor_reply_schema"])
        count_tokens = lambda text: len(encoding.encode(text, disallowed_special=()))
        tokens = sum(count_tokens(m["content"]) for m in result.messages)
        recovery_tokens = tokens + count_tokens(recovery)
        assert result.report.removed_message_count > 0
        assert recovery_tokens <= 48_000
        assert result.report.final_prompt_bytes <= 256 * 1024
        assert result.report.final_transcript_bytes <= 128 * 1024
        return {**asdict(result.report), "content_tokens": tokens, "recovery_content_tokens": recovery_tokens,
                "provider_calls": 0, "tool_calls": 0, "retained_messages": len(result.recent_messages),
                "prompt_digest": canonical_harness_digest(result.messages)}
    raw["tavern"] = timed(prompt_run, count)
    plan_run = planning_fixture()
    raw["planning_before"] = timed(plan_run, count)
    raw["planning_after"] = timed(plan_run, count)
    with TemporaryDirectory(prefix="harness-performance-") as directory:
        database = Database(f"sqlite:///{directory}/performance.db")
        database.create_schema()
        sql_counter = [0]
        def count_sql(*_):
            sql_counter[0] += 1
        event.listen(database.engine, "before_cursor_execute", count_sql)
        try:
            harness = HarnessProposalRuntimeService.from_database(database)
            binding = harness.workflow_operations.admit(kind=HarnessDomainOperationKind.PERSONA_GENERATION,
                request_manifest={"fixture": FIXTURE_VERSION})
            requests = []
            payload = b"synthetic protected snapshot " * 512
            for _ in range(64):
                artifact = harness.artifacts.register_artifact(artifact_type=HarnessArtifactType.PERSONA_SNAPSHOT,
                    artifact_contract=PERSONA_SNAPSHOT_CONTRACT, content=payload)
                grant = harness.artifacts.issue_grant(harness_operation_id=binding.harness_operation_id,
                    scopes=(HarnessArtifactGrantScopeV1(artifact_type=artifact.artifact_type, artifact_id=artifact.artifact_id,
                        artifact_contract=artifact.artifact_contract, permission=HarnessArtifactPermission.READ),),
                    expires_at=datetime.now(UTC) + timedelta(hours=1))
                requests.append(HarnessArtifactResolveRequestV1(grant_id=grant.grant_id,
                    harness_operation_id=binding.harness_operation_id, artifact_type=artifact.artifact_type,
                    artifact_id=artifact.artifact_id, artifact_contract=artifact.artifact_contract,
                    permission=HarnessArtifactPermission.READ))
            for size in (1, 8, 64):
                def resolve_before():
                    results = tuple(harness.artifacts.resolve(r) for r in requests[:size])
                    assert all(r.content == payload for r in results)
                    return {"references": size, "resolved_bytes": size * len(payload)}
                def resolve():
                    result = harness.artifacts.resolve_batch(requests[:size])
                    assert all(r.content == payload for r in result.results)
                    return {"references": size, "resolved_bytes": size * len(payload)}
                raw[f"resolver_{size}_before"] = timed(resolve_before, count, sql_counter)
                raw[f"resolver_{size}"] = timed(resolve, count, sql_counter)
            proposal = PersonaGenerationProposalV1(request_kind="card_batch", cards=[PersonaCardContentProposalV1(
                title="Example", kind="custom", label="Example", content="Synthetic output")])
            def runtime_run():
                _, trace = harness.run_persona(
                    manifest=PersonaGenerationInputManifest(request_kind="card_batch", mode="long_text",
                        requested_count=1, input_char_count=8192),
                    protected_input={"input_text": "x" * 8192}, generate=lambda _: proposal)
                assert trace.status.value == "passed"
                return {"context_bytes": canonical_byte_count(trace.context), "trace_bytes": canonical_byte_count(trace),
                        "references": len(trace.context.snapshot_refs) + len(trace.context.subject_refs),
                        "attempt_count": len(trace.attempt_records), "checks": len(trace.checks),
                        "repair_count": sum(a.phase.value == "repair" for a in trace.attempt_records),
                        "failed": False, "provider_calls": 0}
            raw["runtime"] = timed(runtime_run, count, sql_counter)
        finally:
            event.remove(database.engine, "before_cursor_execute", count_sql)
            database.dispose()
    summaries = {key: summarize(samples) for key, samples in raw.items()}
    failures = [key for key, s in summaries.items() if s["p95"] > P95_LIMITS_MS[key]]
    for size in (1, 8, 64):
        if max(s["sql_statements"] for s in raw[f"resolver_{size}"]) > 6 * size + 3:
            failures.append(f"resolver_{size}_sql")
    entries = [e for e in TOOL_MANIFEST_ENTRIES.values() if e.workflow == HarnessWorkflow.PLANNING]
    # This decision is a gate: changing a registration requires a new reviewed
    # benchmark/immutable-snapshot protocol before enabling a parallel path.
    assert len(entries) == 6 and all(e.parallel.parallel_safe is False for e in entries)
    source_root = Path(__file__).parents[4]
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=source_root, text=True).strip()
    paths = [Path(__file__), Path(__file__).with_name("harness_runtime.py"),
             Path(__file__).with_name("tavern_prompt.py"), Path(__file__).with_name("plan_tool_runtime.py"),
             Path(__file__).with_name("harness_broad_adoption.py"),
             Path(__file__).with_name("study_v3.py"), Path(__file__).with_name("tavern_v3.py"),
             Path(__file__).parents[1] / "persistence" / "harness_artifact_repository.py",
             Path(__file__).parents[1] / "models" / "harness_performance.py",
             source_root / "services/ai/uv.lock",
             source_root / "packages/shared/fixtures/harness/tool-manifest-v1.json"]
    return {"schema_version": REPORT_VERSION, "fixture_version": FIXTURE_VERSION,
        "measured_at": datetime.now(UTC).isoformat(),
        "budget_version": HARNESS_PERFORMANCE_BUDGET_VERSION, "base_commit": revision,
        "source_sha256": {str(p.relative_to(source_root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
        "environment": {"platform": platform.platform(), "machine": platform.machine(), "python": platform.python_version(),
            "dependencies": {p: version(p) for p in ("tiktoken", "SQLAlchemy", "pydantic")}, "database": "temporary SQLite",
            "clock": "perf_counter_ns", "warmups": WARMUPS, "tokenizer": encoding.name, "provider": "disabled"},
        "planning_decision": {"mode": "retain_serial", "reason": "all_six_tools_registered_parallel_unsafe",
            "candidate_parallel_executed": False, "model_round_reduction_claimed": False,
            "before_after": "same serial implementation, independent sample windows",
            "rollback": "Reject any parallel mode until manifest, immutable snapshot, stable ordering and correctness gates are reviewed"},
        "tavern_fixture": {"participants": 6, "recent_messages": 40, "message_characters": 8000,
            "token_measurement": "cl100k_base content tokens including recovery; no provider wrapper estimate"},
        "provider_measurements": {"status": "not_run_user_requested_local_only", "latency": None, "cost": None,
                                  "repair_rate": None, "failure_rate": None},
        "p95_limits_ms": P95_LIMITS_MS, "summaries": summaries, "samples": raw, "failures": failures,
        "gate_passed": not failures, "independent_acceptance": "pending_with_wave4"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--samples", type=int, default=50)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.samples < 30:
        parser.error("at least 30 measured samples are required")
    result = benchmark(args.samples)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"gate_passed": result["gate_passed"], "summaries": result["summaries"], "failures": result["failures"]}))
    raise SystemExit(0 if result["gate_passed"] else 1)


if __name__ == "__main__":
    main()
