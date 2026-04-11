from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable

from app.models.domain import (
    PlanGenerationRoundRecord,
    PlanGenerationTraceRecord,
    PlanToolCallTraceRecord,
)
from app.services.plan_tool_runtime import PlanToolRuntime
from app.services.prompt_loader import load_prompt_template


@dataclass(frozen=True)
class OpenAIPlanRunnerResult:
    content: str
    trace: PlanGenerationTraceRecord


class OpenAIPlanRunner:
    def __init__(
        self,
        *,
        model: str,
        timeout_seconds: int,
        request_chat_completion: Callable[[dict[str, Any]], tuple[dict[str, Any], int]],
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.request_chat_completion = request_chat_completion

    def run(
        self,
        *,
        document_id: str,
        messages: list[dict[str, Any]],
        tool_runtime: PlanToolRuntime,
        progress_callback: Callable[[str, dict[str, object]], None] | None = None,
    ) -> OpenAIPlanRunnerResult:
        current_messages: list[dict[str, Any]] = [*messages]
        prompt_template = load_prompt_template("openai_plan_runner_prompt.txt")
        trace = PlanGenerationTraceRecord(
            document_id=document_id,
            model=self.model,
            created_at=_now(),
            rounds=[],
        )
        max_rounds = 4
        max_empty_response_retries = 1
        empty_response_retries = 0
        max_tool_probe_retries = 1
        tool_probe_retries = 0
        for round_index in range(max_rounds):
            _emit_progress(
                progress_callback,
                "model_round_started",
                {
                    "round_index": round_index,
                    "timeout_seconds": self.timeout_seconds,
                    "tools_enabled": tool_runtime.has_tools(),
                },
            )
            payload: dict[str, Any] = {
                "model": self.model,
                "messages": current_messages,
                "temperature": 0.2,
            }
            if tool_runtime.has_tools():
                payload["tools"] = tool_runtime.openai_tools()
                payload["tool_choice"] = "auto"
            else:
                payload["response_format"] = {"type": "json_object"}
            raw_payload, elapsed_ms = self.request_chat_completion(payload)
            choice = raw_payload["choices"][0]
            message = choice["message"]
            thinking = _extract_reasoning_text(
                raw_payload=raw_payload,
                choice=choice,
                message=message,
            )
            tool_calls = message.get("tool_calls") or []
            if tool_calls:
                trace_round = PlanGenerationRoundRecord(
                    round_index=round_index,
                    finish_reason=str(choice.get("finish_reason") or ""),
                    assistant_content=_coerce_text_content(message.get("content")),
                    thinking=thinking,
                    elapsed_ms=elapsed_ms,
                    timeout_seconds=self.timeout_seconds,
                    tool_calls=[],
                )
                current_messages.append(
                    {
                        "role": "assistant",
                        "content": message.get("content") or "",
                        "tool_calls": tool_calls,
                    }
                )
                for tool_call in tool_calls:
                    execution = tool_runtime.execute_tool_call(tool_call)
                    _emit_progress(
                        progress_callback,
                        "model_tool_call",
                        {
                            "round_index": round_index,
                            "tool_call_id": execution.tool_call_id,
                            "tool_name": execution.tool_name,
                        },
                    )
                    trace_round.tool_calls.append(
                        PlanToolCallTraceRecord(
                            tool_call_id=execution.tool_call_id,
                            tool_name=execution.tool_name,
                            arguments_json=execution.arguments_json,
                            result_summary=execution.trace_summary,
                            result_json=json.dumps(execution.result, ensure_ascii=False),
                        )
                    )
                    current_messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": execution.tool_call_id,
                            "name": execution.tool_name,
                            "content": json.dumps(execution.result, ensure_ascii=False),
                        }
                    )
                    if execution.follow_up_messages:
                        current_messages.extend(execution.follow_up_messages)
                trace.rounds.append(trace_round)
                _emit_progress(
                    progress_callback,
                    "model_round_completed",
                    {
                        "round_index": round_index,
                        "elapsed_ms": elapsed_ms,
                        "finish_reason": str(choice.get("finish_reason") or ""),
                        "tool_call_count": len(tool_calls),
                    },
                )
                continue

            content = _coerce_text_content(message.get("content"))
            if content.strip():
                if (
                    tool_runtime.has_tools()
                    and tool_probe_retries < max_tool_probe_retries
                    and _looks_coarse_grained(tool_runtime.current_study_units())
                    and not _trace_has_tool_calls(trace)
                ):
                    tool_probe_retries += 1
                    _emit_progress(
                        progress_callback,
                        "model_recovery_attempt",
                        {
                            "round_index": round_index,
                            "attempt": tool_probe_retries,
                            "reason": "coarse_units_without_tool_calls",
                            "strategy": "force_detail_tool_call",
                        },
                    )
                    current_messages.append(
                        {
                            "role": "user",
                            "content": prompt_template.require("tool_probe_retry"),
                        }
                    )
                    continue
                trace.rounds.append(
                    PlanGenerationRoundRecord(
                        round_index=round_index,
                        finish_reason=str(choice.get("finish_reason") or ""),
                        assistant_content=content,
                        thinking=thinking,
                        elapsed_ms=elapsed_ms,
                        timeout_seconds=self.timeout_seconds,
                        tool_calls=[],
                    )
                )
                _emit_progress(
                    progress_callback,
                    "model_round_completed",
                    {
                        "round_index": round_index,
                        "elapsed_ms": elapsed_ms,
                        "finish_reason": str(choice.get("finish_reason") or ""),
                        "tool_call_count": 0,
                        "has_content": True,
                    },
                )
                return OpenAIPlanRunnerResult(
                    content=content,
                    trace=trace,
                )
            _emit_progress(
                progress_callback,
                "model_round_failed",
                {
                    "round_index": round_index,
                    "elapsed_ms": elapsed_ms,
                    "finish_reason": str(choice.get("finish_reason") or ""),
                    "error": "plan_model_empty_response",
                },
            )
            if empty_response_retries < max_empty_response_retries:
                empty_response_retries += 1
                _emit_progress(
                    progress_callback,
                    "model_recovery_attempt",
                    {
                        "round_index": round_index,
                        "attempt": empty_response_retries,
                        "reason": "plan_model_empty_response",
                        "strategy": "retry_with_tools",
                    },
                )
                current_messages.append(
                    {
                        "role": "user",
                        "content": prompt_template.require("empty_response_retry"),
                    }
                )
                continue
            raise RuntimeError("plan_model_empty_response")
        _emit_progress(
            progress_callback,
            "model_round_failed",
            {
                "round_index": max_rounds - 1,
                "max_rounds": max_rounds,
                "error": "plan_model_tool_loop_exhausted",
            },
        )
        raise RuntimeError("plan_model_tool_loop_exhausted")


def _extract_reasoning_text(
    *,
    raw_payload: dict[str, Any],
    choice: dict[str, Any],
    message: dict[str, Any],
) -> str:
    candidates = [
        message.get("reasoning_content"),
        message.get("reasoning"),
        message.get("thinking"),
        choice.get("reasoning_content"),
        choice.get("reasoning"),
        raw_payload.get("reasoning_content"),
        raw_payload.get("reasoning"),
    ]
    parts = [_coerce_text_content(candidate) for candidate in candidates]
    text = "\n\n".join(part for part in parts if part)
    return text[:12000]


def _coerce_text_content(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        parts = [_coerce_text_content(item) for item in value]
        return "\n".join(part for part in parts if part)
    if isinstance(value, dict):
        if isinstance(value.get("text"), str):
            return value["text"]
        if isinstance(value.get("content"), str):
            return value["content"]
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _emit_progress(
    callback: Callable[[str, dict[str, object]], None] | None,
    stage: str,
    payload: dict[str, object],
) -> None:
    if callback is None:
        return
    callback(stage, payload)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _trace_has_tool_calls(trace: PlanGenerationTraceRecord) -> bool:
    return any(round_record.tool_calls for round_record in trace.rounds)


def _looks_coarse_grained(study_units: list[Any]) -> bool:
    if not study_units:
        return False
    plannable = [
        unit
        for unit in study_units
        if bool(getattr(unit, "include_in_plan", True))
    ] or study_units
    if len(plannable) <= 1:
        return True
    max_span = max(
        (
            int(getattr(unit, "page_end", 0))
            - int(getattr(unit, "page_start", 0))
            + 1
        )
        for unit in plannable
    )
    return len(plannable) <= 2 and max_span >= 80
