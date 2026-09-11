from __future__ import annotations

import json
import math
from dataclasses import dataclass
from typing import Any, Literal, Mapping, Sequence

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.models.harness import HarnessStage, HarnessWorkflow
from app.models.planning import PlanningToolErrorResultV1
from app.models.study_chat_tool_contracts import StudyChatToolErrorResultV1
from app.models.tool_manifest import (
    TOOL_INPUT_MODELS,
    TOOL_MANIFEST_REGISTRY,
    TOOL_RESULT_MODELS,
    ToolDependency,
    ToolLifecycleStatus,
    ToolManifestEntryV1,
    ToolManifestRegistryV1,
    ToolProviderCapability,
    ToolResultProjectionMode,
    ToolSensitivityLevel,
    provider_parameters_digest,
    provider_parameters_for_model,
    resolve_tool_manifest_entry,
)


class ToolProviderProjectionModel(BaseModel):
    model_config = ConfigDict(
        extra="forbid",
        strict=True,
        frozen=True,
        allow_inf_nan=False,
    )


class ProviderFunctionDefinitionV1(ToolProviderProjectionModel):
    name: str = Field(pattern=r"^[a-z][a-z0-9_]{0,79}$")
    description: str = Field(min_length=1, max_length=1_000)
    strict: Literal[True] = True
    parameters: dict[str, Any]


class ProviderFunctionToolV1(ToolProviderProjectionModel):
    type: Literal["function"] = "function"
    function: ProviderFunctionDefinitionV1


class ToolContractViolation(ValueError):
    def __init__(
        self,
        code: str,
        *,
        path: Sequence[str | int] = (),
        detail: str = "",
    ) -> None:
        self.code = code
        self.path = tuple(path)
        self.detail = detail
        rendered_path = ".".join(str(part) for part in self.path)
        suffix = f" at {rendered_path}" if rendered_path else ""
        super().__init__(f"{code}{suffix}")


class ToolArgumentDecodeError(ToolContractViolation):
    pass


class ToolResultValidationError(ToolContractViolation):
    pass


class ProviderToolCallDecodeError(ToolContractViolation):
    pass


@dataclass(frozen=True, slots=True)
class DecodedProviderToolCallV1:
    """A decoded call; the provider ID is transport correlation only."""

    transport_correlation_id: str
    manifest_key: str
    canonical_name: str
    arguments: BaseModel


class ToolExecutionBudgetTracker:
    def __init__(self) -> None:
        self._operation_calls: dict[str, int] = {}
        self._round_calls: dict[str, int] = {}

    def begin_round(self) -> None:
        self._round_calls.clear()

    def admit(self, entry: ToolManifestEntryV1) -> None:
        operation_calls = self._operation_calls.get(entry.key, 0)
        round_calls = self._round_calls.get(entry.key, 0)
        if operation_calls >= entry.budget.max_calls_per_operation:
            raise ToolContractViolation("tool_operation_budget_exceeded")
        if round_calls >= entry.budget.max_calls_per_round:
            raise ToolContractViolation("tool_round_budget_exceeded")
        self._operation_calls[entry.key] = operation_calls + 1
        self._round_calls[entry.key] = round_calls + 1


def provider_function_for_entry(entry: ToolManifestEntryV1) -> ProviderFunctionToolV1:
    model = TOOL_INPUT_MODELS.get(entry.key)
    if model is None:
        raise ValueError("tool_provider_input_contract_missing")
    digest = provider_parameters_digest(model)
    if digest != entry.provider_parameters_digest:
        raise ValueError("tool_provider_schema_digest_mismatch")
    return ProviderFunctionToolV1(
        function=ProviderFunctionDefinitionV1(
            name=entry.canonical_name,
            description=entry.display.provider_description,
            parameters=provider_parameters_for_model(model),
        )
    )


def project_provider_tools(
    *,
    workflow: HarnessWorkflow,
    offered_in_stage: HarnessStage,
    available_dependencies: set[ToolDependency] | frozenset[ToolDependency],
    provider_capabilities: set[ToolProviderCapability]
    | frozenset[ToolProviderCapability],
    disabled_keys: set[str] | frozenset[str] = frozenset(),
    registry: ToolManifestRegistryV1 = TOOL_MANIFEST_REGISTRY,
) -> tuple[ProviderFunctionToolV1, ...]:
    projected: list[ProviderFunctionToolV1] = []
    projected_names: set[str] = set()
    for entry in registry.tools:
        if (
            entry.workflow != workflow
            or entry.offered_in_stage != offered_in_stage
            or entry.status != ToolLifecycleStatus.ACTIVE
            or entry.key in disabled_keys
            or not set(entry.dependencies).issubset(available_dependencies)
            or not set(entry.provider_capabilities).issubset(provider_capabilities)
        ):
            continue
        if entry.canonical_name in projected_names:
            raise ValueError("tool_provider_projection_name_collision")
        projected_names.add(entry.canonical_name)
        projected.append(provider_function_for_entry(entry))
    return tuple(projected)


def _reject_nonfinite(value: Any, path: tuple[str | int, ...] = ()) -> None:
    if isinstance(value, float) and not math.isfinite(value):
        raise ToolContractViolation("tool_contract_nonfinite", path=path)
    if isinstance(value, Mapping):
        for key, child in value.items():
            _reject_nonfinite(child, (*path, str(key)))
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            _reject_nonfinite(child, (*path, index))


def _bounded_json_size(
    value: Any,
    *,
    limit: int,
    error_type: type[ToolContractViolation],
    code: str,
) -> None:
    try:
        encoded = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise error_type(code, detail=type(error).__name__) from error
    if len(encoded) > limit:
        raise error_type(code, detail="byte_budget_exceeded")


def _first_validation_error(error: ValidationError) -> tuple[tuple[str | int, ...], str]:
    item = error.errors(include_url=False, include_context=False, include_input=False)[0]
    path = tuple(item.get("loc", ()))
    detail = str(item.get("type", "validation_error"))
    return path, detail


def _load_strict_json_object(raw: str, *, max_bytes: int) -> dict[str, Any]:
    if not isinstance(raw, str):
        raise ToolArgumentDecodeError("tool_arguments_json_string_required")
    if len(raw.encode("utf-8")) > max_bytes:
        raise ToolArgumentDecodeError(
            "tool_arguments_budget_exceeded",
            detail="byte_budget_exceeded",
        )

    def reject_constant(token: str) -> Any:
        raise ToolArgumentDecodeError(
            "tool_arguments_nonfinite",
            detail=token,
        )

    def reject_duplicate(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ToolArgumentDecodeError(
                    "tool_arguments_duplicate_key",
                    path=(key,),
                )
            result[key] = value
        return result

    try:
        parsed = json.loads(
            raw,
            parse_constant=reject_constant,
            object_pairs_hook=reject_duplicate,
        )
    except ToolArgumentDecodeError:
        raise
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ToolArgumentDecodeError(
            "tool_arguments_json_invalid",
            detail=type(error).__name__,
        ) from error
    if not isinstance(parsed, dict):
        raise ToolArgumentDecodeError("tool_arguments_object_required")
    try:
        _reject_nonfinite(parsed)
    except ToolContractViolation as error:
        raise ToolArgumentDecodeError(
            "tool_arguments_nonfinite",
            path=error.path,
        ) from error
    return parsed


def decode_tool_arguments(
    entry: ToolManifestEntryV1,
    raw_arguments: str,
) -> BaseModel:
    model = TOOL_INPUT_MODELS.get(entry.key)
    if model is None:
        raise ToolArgumentDecodeError("tool_arguments_contract_missing")
    parsed = _load_strict_json_object(
        raw_arguments,
        max_bytes=entry.budget.max_argument_bytes,
    )
    try:
        return model.model_validate(parsed)
    except ValidationError as error:
        path, detail = _first_validation_error(error)
        raise ToolArgumentDecodeError(
            "tool_arguments_contract_invalid",
            path=path,
            detail=detail,
        ) from error


def validate_tool_runtime_result(
    entry: ToolManifestEntryV1,
    payload: Mapping[str, Any] | BaseModel,
) -> BaseModel:
    raw: Any = payload.model_dump(mode="python") if isinstance(payload, BaseModel) else payload
    if not isinstance(raw, Mapping):
        raise ToolResultValidationError("tool_result_object_required")
    try:
        _reject_nonfinite(raw)
    except ToolContractViolation as error:
        raise ToolResultValidationError(
            "tool_result_nonfinite",
            path=error.path,
        ) from error
    _bounded_json_size(
        raw,
        limit=entry.budget.max_internal_result_bytes,
        error_type=ToolResultValidationError,
        code="tool_result_budget_exceeded",
    )
    if raw.get("ok") is False:
        model: type[BaseModel]
        if entry.workflow == HarnessWorkflow.PLANNING:
            model = PlanningToolErrorResultV1
        else:
            model = StudyChatToolErrorResultV1
    else:
        model = TOOL_RESULT_MODELS.get(entry.key)  # type: ignore[assignment]
        if model is None:
            raise ToolResultValidationError("tool_result_contract_missing")
    try:
        validated = model.model_validate(raw)
    except ValidationError as error:
        path, detail = _first_validation_error(error)
        raise ToolResultValidationError(
            "tool_result_contract_invalid",
            path=path,
            detail=detail,
        ) from error
    tool_name = getattr(validated, "tool_name", "")
    if tool_name != entry.canonical_name:
        raise ToolResultValidationError(
            "tool_result_name_mismatch",
            path=("tool_name",),
        )
    return validated


def decode_provider_tool_call(
    raw_call: Mapping[str, Any],
    *,
    workflow: HarnessWorkflow,
    offered_in_stage: HarnessStage,
    registry: ToolManifestRegistryV1 = TOOL_MANIFEST_REGISTRY,
) -> DecodedProviderToolCallV1:
    if not isinstance(raw_call, Mapping):
        raise ProviderToolCallDecodeError("provider_tool_call_object_required")
    if set(raw_call) not in ({"id", "function"}, {"id", "type", "function"}):
        raise ProviderToolCallDecodeError("provider_tool_call_shape_invalid")
    transport_id = raw_call.get("id")
    if not isinstance(transport_id, str) or not transport_id or len(transport_id) > 256:
        raise ProviderToolCallDecodeError(
            "provider_tool_call_id_invalid",
            path=("id",),
        )
    if "type" in raw_call and raw_call.get("type") != "function":
        raise ProviderToolCallDecodeError(
            "provider_tool_call_type_invalid",
            path=("type",),
        )
    function = raw_call.get("function")
    if not isinstance(function, Mapping) or set(function) != {"name", "arguments"}:
        raise ProviderToolCallDecodeError(
            "provider_function_call_shape_invalid",
            path=("function",),
        )
    name = function.get("name")
    arguments_json = function.get("arguments")
    if not isinstance(name, str):
        raise ProviderToolCallDecodeError(
            "provider_function_name_invalid",
            path=("function", "name"),
        )
    try:
        entry = resolve_tool_manifest_entry(
            workflow=workflow,
            offered_in_stage=offered_in_stage,
            transport_name=name,
            registry=registry,
        )
    except ValueError as error:
        raise ProviderToolCallDecodeError(
            str(error),
            path=("function", "name"),
        ) from error
    try:
        decoded = decode_tool_arguments(entry, arguments_json)  # type: ignore[arg-type]
    except ToolArgumentDecodeError as error:
        raise ProviderToolCallDecodeError(
            error.code,
            path=("function", "arguments", *error.path),
            detail=error.detail,
        ) from error
    return DecodedProviderToolCallV1(
        transport_correlation_id=transport_id,
        manifest_key=entry.key,
        canonical_name=entry.canonical_name,
        arguments=decoded,
    )


def build_versioned_tool_error(
    *,
    workflow: HarnessWorkflow,
    tool_name: str,
    error: str,
    path: Sequence[str | int] = (),
    detail: str = "",
) -> BaseModel:
    normalized_name = tool_name if tool_name else "unknown_tool"
    payload = {
        "ok": False,
        "tool_name": normalized_name,
        "error": error,
        "path": list(path),
        "detail": detail,
    }
    if workflow == HarnessWorkflow.PLANNING:
        return PlanningToolErrorResultV1.model_validate(
            {**payload, "study_unit_id": ""}
        )
    return StudyChatToolErrorResultV1.model_validate(payload)


def adapt_tool_runtime_result(
    entry: ToolManifestEntryV1,
    raw_result: Mapping[str, Any],
) -> BaseModel:
    """Map one known domain runtime shape into its exact canonical result DTO."""
    if not isinstance(raw_result, Mapping):
        raise ToolResultValidationError("tool_runtime_result_object_required")
    if raw_result.get("ok") is False:
        error_result = build_versioned_tool_error(
            workflow=entry.workflow,
            tool_name=entry.canonical_name,
            error=str(raw_result.get("error") or "tool_runtime_failed"),
            path=_path_parts(raw_result.get("path")),
            detail=str(raw_result.get("detail") or ""),
        )
        return validate_tool_runtime_result(entry, error_result)
    if entry.workflow == HarnessWorkflow.PLANNING:
        payload = {
            "schema_name": "planning-tool-result",
            "schema_version": "planning-tool-result-v1",
            **raw_result,
            "ok": True,
            "tool_name": entry.canonical_name,
        }
        return validate_tool_runtime_result(entry, payload)
    payload = _adapt_study_runtime_success(entry.canonical_name, raw_result)
    return validate_tool_runtime_result(entry, payload)


def _adapt_study_runtime_success(
    name: str,
    raw: Mapping[str, Any],
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema_name": "study-chat-tool-result",
        "schema_version": "study-chat-tool-result-v1",
        "ok": True,
        "tool_name": name,
        "summary": str(raw.get("summary") or ""),
    }
    if name == "ask_multiple_choice_question":
        return {
            **base,
            "question_type": "multiple_choice",
            "difficulty": raw.get("difficulty"),
            "topic": raw.get("topic", ""),
            "question": raw.get("question"),
            "options": raw.get("options"),
            "call_back": raw.get("call_back", True),
            "answer_key": raw.get("answer_key"),
            "explanation": raw.get("explanation", ""),
            "source_context": raw.get("source_context", ""),
        }
    if name == "ask_fill_blank_question":
        return {
            **base,
            "question_type": "fill_blank",
            "difficulty": raw.get("difficulty"),
            "topic": raw.get("topic", ""),
            "question": raw.get("question"),
            "call_back": raw.get("call_back", True),
            "answer": raw.get("answer"),
            "explanation": raw.get("explanation", ""),
            "source_context": raw.get("source_context", ""),
        }
    if name == "retrieve_memory_context":
        hits = raw.get("hits")
        normalized_hits = [
            {
                "memory_id": item.get("id") or item.get("session_id") or "",
                "content": item.get("content") or item.get("snippet"),
                "source": item.get("source") or "",
                "created_at": item.get("created_at") or "",
            }
            for item in hits
            if isinstance(item, Mapping)
        ] if isinstance(hits, list) else []
        return {
            **base,
            "hit_count": len(normalized_hits),
            "hits": normalized_hits,
        }
    if name == "read_session_memory":
        items = raw.get("memory_items")
        normalized_items = [
            {
                "memory_id": item.get("id") or item.get("memory_id") or "",
                "key": item.get("key"),
                "content": item.get("content"),
                "committed": item.get("committed", item.get("effect_state") != "prepared"),
            }
            for item in items
            if isinstance(item, Mapping)
        ] if isinstance(items, list) else []
        return {**base, "memory_items": normalized_items}
    if name == "write_session_memory":
        proposal = _mapping(raw.get("prepared_proposal"))
        predicted = _mapping(_mapping(raw.get("predicted_state")).get("memory"))
        return {
            **base,
            **_prepared_effect_fields(raw),
            "key": proposal.get("key") or predicted.get("key"),
        }
    if name == "read_system_time":
        return {
            **base,
            "iso_datetime": raw.get("iso_datetime"),
            "date": raw.get("date"),
            "time": raw.get("time"),
            "timezone": raw.get("timezone", ""),
            "weekday": raw.get("weekday", ""),
        }
    if name == "schedule_session_follow_up":
        proposal = _mapping(raw.get("prepared_proposal"))
        return {
            **base,
            **_prepared_effect_fields(raw),
            "requires_client_schedule": True,
            "delay_seconds": proposal.get("delay_seconds") or raw.get("delay_seconds"),
        }
    if name == "read_affinity_state":
        return {
            **base,
            "score": raw.get("score"),
            "level": raw.get("level"),
            "state_summary": raw.get("summary", ""),
            "committed": raw.get("committed", True),
        }
    if name == "update_affinity_state":
        predicted = _mapping(raw.get("predicted_state"))
        return {
            **base,
            **_prepared_effect_fields(raw),
            "score": predicted.get("score"),
            "level": predicted.get("level"),
        }
    if name == "read_learning_plan_progress":
        progress = _mapping(raw.get("progress_summary"))
        schedule = raw.get("schedule")
        normalized_schedule = [
            {
                "item_id": item.get("id"),
                "title": item.get("title"),
                "status": item.get("status"),
            }
            for item in schedule
            if isinstance(item, Mapping)
        ] if isinstance(schedule, list) else []
        return {
            **base,
            "course_title": raw.get("course_title"),
            "completion_percent": progress.get("completion_percent", 0.0),
            "schedule": normalized_schedule,
        }
    if name in {"update_learning_plan", "update_learning_plan_progress"}:
        predicted = _mapping(raw.get("predicted_state"))
        return {
            **base,
            **_prepared_effect_fields(raw),
            "requires_confirmation": True,
            "plan_id": predicted.get("plan_id"),
            "preview_lines": predicted.get("preview_lines", []),
        }
    if name in {"read_page_range_content", "read_projected_pdf_content"}:
        content_payload = {
            **base,
            "page_start": raw.get("page_start"),
            "page_end": raw.get("page_end"),
            "chunk_count": raw.get("chunk_count", 0),
            "content": raw.get("content", ""),
        }
        if name == "read_projected_pdf_content":
            content_payload.update(
                source_kind="attachment_pdf",
                source_id=raw.get("source_id"),
            )
        return content_payload
    if name in {"read_page_range_images", "read_projected_pdf_images"}:
        image_payload = {
            **base,
            "page_start": raw.get("page_start"),
            "page_end": raw.get("page_end"),
            "image_count": raw.get("image_count", 0),
            "page_numbers": raw.get("page_numbers", []),
        }
        if name == "read_projected_pdf_images":
            image_payload.update(
                source_kind="attachment_pdf",
                source_id=raw.get("source_id"),
            )
        return image_payload
    if name in {"project_uploaded_pdf", "project_uploaded_image"}:
        predicted = _mapping(raw.get("predicted_state"))
        return {
            **base,
            **_prepared_effect_fields(raw),
            "source_kind": predicted.get("source_kind"),
            "source_id": predicted.get("source_id", ""),
            "page_number": predicted.get("page_number", 0),
        }
    if name == "generate_projected_image":
        predicted = _mapping(raw.get("predicted_state"))
        return {
            **base,
            **_prepared_effect_fields(raw),
            "source_kind": "generated_image",
            "source_id": predicted.get("source_id", ""),
            "page_number": predicted.get("page_number", 1),
            "external_effect_state": raw.get("external_effect_state"),
            "external_effect_id": raw.get("external_effect_id"),
            "external_effect_read_back": raw.get("external_effect_read_back"),
            "revised_prompt": raw.get("revised_prompt", ""),
        }
    if name in {
        "focus_projected_pdf_page",
        "highlight_projected_pdf_text",
        "annotate_projected_pdf_region",
        "clear_projected_pdf_overlays",
        "annotate_projected_image_region",
        "clear_projected_image_overlays",
    }:
        predicted = _mapping(raw.get("predicted_state"))
        proposal = _mapping(raw.get("prepared_proposal"))
        projection_payload = {
            **base,
            **_prepared_effect_fields(raw),
            "source_kind": (
                "attachment_pdf"
                if "pdf" in name
                else predicted.get("source_kind", "")
            ),
            "source_id": predicted.get("source_id", ""),
            "page_number": predicted.get("page_number", proposal.get("page_number", 0)),
        }
        if name == "highlight_projected_pdf_text":
            projection_payload["match_count"] = raw.get("match_count")
        return projection_payload
    if name == "read_scene_overview":
        return {
            **base,
            "scene_instance_id": raw.get("scene_instance_id"),
            "scene_title": raw.get("selected_scene_title") or raw.get("scene_name", ""),
            "selected_path": raw.get("selected_scene_path", []),
            "object_names": _scene_object_names(raw.get("scene_tree")),
            "selected_scene_id": raw.get("selected_scene_id", ""),
            **_scene_tool_members(raw.get("scene_tree")),
        }
    if name in {
        "add_scene",
        "move_to_scene",
        "add_object",
        "update_object_description",
        "delete_object",
    }:
        return {
            **base,
            **_prepared_effect_fields(raw),
            "scene_instance_id": raw.get("scene_instance_id"),
            "selected_scene_id": raw.get("selected_scene_id") or _mapping(raw.get("scene_profile")).get("scene_id", ""),
            "added_scene_id": raw.get("added_scene_id", ""),
            "object_id": raw.get("object_id", ""),
        }
    raise ToolResultValidationError("tool_runtime_result_adapter_missing")


def project_validated_tool_result(
    entry: ToolManifestEntryV1,
    result: BaseModel,
    *,
    audience: Literal["provider", "trace", "public"],
) -> dict[str, Any]:
    canonical = result.model_dump(mode="json")
    if audience == "provider":
        projected = _provider_result_projection(entry, canonical)
        limit = entry.budget.max_provider_result_bytes
    else:
        mode = (
            entry.sensitivity.trace_projection
            if audience == "trace"
            else entry.sensitivity.public_projection
        )
        projected = _safe_observability_projection(canonical, mode=mode)
        limit = entry.budget.max_public_result_bytes
    _bounded_json_size(
        projected,
        limit=limit,
        error_type=ToolResultValidationError,
        code=f"tool_{audience}_result_budget_exceeded",
    )
    return projected


def project_tool_arguments_for_observability(
    entry: ToolManifestEntryV1,
    arguments: BaseModel,
) -> str:
    if entry.sensitivity.arguments == ToolSensitivityLevel.PUBLIC:
        payload: dict[str, Any] = arguments.model_dump(mode="json")
    else:
        payload = {"redacted": True}
    payload = {
        "contract_version": entry.input_contract.version,
        **payload,
    }
    return json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    )


def _provider_result_projection(
    entry: ToolManifestEntryV1,
    canonical: Mapping[str, Any],
) -> dict[str, Any]:
    name = entry.canonical_name
    if canonical.get("ok") is False:
        return {
            "schema_version": canonical.get("schema_version"),
            "ok": False,
            "tool_name": name,
            "error": canonical.get("error"),
        }
    # Planning tools exist to return grounded planning context to the model.
    # Their provider projection may carry protected content under the manifest
    # budget, while trace/public projections remain independently content-free.
    if entry.workflow == HarnessWorkflow.PLANNING:
        return dict(canonical)
    if name in {"ask_multiple_choice_question", "ask_fill_blank_question"}:
        allowed = {
            "schema_version",
            "ok",
            "tool_name",
            "question_type",
            "difficulty",
            "topic",
            "question",
            "options",
            "call_back",
        }
    elif name in {
        "retrieve_memory_context",
        "read_session_memory",
        "read_learning_plan_progress",
        "read_page_range_content",
        "read_projected_pdf_content",
        "read_scene_overview",
        "read_system_time",
    }:
        allowed = set(canonical)
    elif name in {"read_page_range_images", "read_projected_pdf_images"}:
        allowed = {
            "schema_version",
            "ok",
            "tool_name",
            "page_start",
            "page_end",
            "image_count",
            "page_numbers",
            "source_kind",
            "source_id",
        }
    else:
        allowed = {
            "schema_version",
            "ok",
            "tool_name",
            "summary",
            "effect_state",
            "committed",
            "requires_client_schedule",
            "delay_seconds",
            "requires_confirmation",
            "plan_id",
            "preview_lines",
            "score",
            "level",
            "source_kind",
            "source_id",
            "page_number",
            "match_count",
            "scene_instance_id",
            "selected_scene_id",
            "added_scene_id",
            "object_id",
        }
    return {key: value for key, value in canonical.items() if key in allowed}


def _safe_observability_projection(
    canonical: Mapping[str, Any],
    *,
    mode: ToolResultProjectionMode,
) -> dict[str, Any]:
    if mode == ToolResultProjectionMode.FULL:
        return dict(canonical)
    base = {
        "schema_version": canonical.get("schema_version"),
        "ok": canonical.get("ok"),
        "tool_name": canonical.get("tool_name"),
    }
    if canonical.get("ok") is False:
        base["error"] = canonical.get("error")
    if mode == ToolResultProjectionMode.OMITTED:
        return {**base, "omitted": True}
    if mode == ToolResultProjectionMode.REDACTED:
        return {**base, "redacted": True}
    return {
        **base,
        "content_free": True,
        "summary": str(canonical.get("summary") or ""),
    }


def _prepared_effect_fields(raw: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "effect_state": "prepared",
        "committed": False,
        "prepared_effect_id": raw.get("prepared_effect_id"),
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _path_parts(value: Any) -> list[str | int]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, (str, int)) and not isinstance(item, bool)][:16]


def _scene_tool_members(value: Any) -> dict[str, Any]:
    scenes: list[dict[str, Any]] = []
    objects: list[dict[str, Any]] = []
    truncated = False

    def visit(nodes: Any, parent_id: str = "") -> None:
        nonlocal truncated
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, Mapping):
                continue
            if len(scenes) >= 128:
                truncated = True
                return
            scene_id = node.get("id")
            scenes.append({"scene_id": scene_id, "parent_scene_id": parent_id, "title": node.get("title")})
            for obj in node.get("objects") or []:
                if len(objects) >= 128:
                    truncated = True
                    break
                objects.append({"object_id": obj.get("id"), "scene_id": scene_id,
                    "name": obj.get("name"), "description": obj.get("description", "")})
            visit(node.get("children"), scene_id)

    visit(value)
    return {"scenes": scenes, "objects": objects, "truncated": truncated}


def _scene_object_names(value: Any) -> list[str]:
    names: list[str] = []

    def visit(nodes: Any) -> None:
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, Mapping):
                continue
            objects = node.get("objects")
            if isinstance(objects, list):
                for item in objects:
                    if isinstance(item, Mapping) and isinstance(item.get("name"), str):
                        names.append(item["name"])
            visit(node.get("children"))

    visit(value)
    return names[:128]


def tool_manifest_golden_snapshot() -> dict[str, Any]:
    return {
        "schema_name": "ToolManifestGolden",
        "schema_version": "tool-manifest-v1",
        "manifest": TOOL_MANIFEST_REGISTRY.model_dump(mode="json"),
        "provider_functions": [
            {
                "key": entry.key,
                "projection": provider_function_for_entry(entry).model_dump(mode="json"),
            }
            for entry in TOOL_MANIFEST_REGISTRY.tools
        ],
    }
