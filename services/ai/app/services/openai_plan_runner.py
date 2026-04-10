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
        trace = PlanGenerationTraceRecord(
            document_id=document_id,
            model=self.model,
            created_at=_now(),
            rounds=[],
        )
        max_rounds = 4
        max_empty_response_retries = 1
        empty_response_retries = 0
        force_json_response = False
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
            if tool_runtime.has_tools() and not force_json_response:
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
                force_json_response = False
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
                force_json_response = True
                _emit_progress(
                    progress_callback,
                    "model_recovery_attempt",
                    {
                        "round_index": round_index,
                        "attempt": empty_response_retries,
                        "reason": "plan_model_empty_response",
                        "strategy": "force_json_without_tools",
                    },
                )
                current_messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Your previous assistant message was empty. Continue from existing context and "
                            "return a complete learning-plan JSON object now. Do not return an empty response."
                        ),
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
