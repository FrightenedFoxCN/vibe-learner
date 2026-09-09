from __future__ import annotations

from app.models.domain import StudySessionRecord
from app.models.study_chat_operation import StudyChatOperationRequestPayload
from app.models.harness import HarnessStage, HarnessWorkflow
from app.models.tool_manifest import resolve_tool_manifest_entry
from app.services.model_tool_config import CHAT_STAGE, TOOL_CATALOG
from app.services.tool_provider_projection import provider_function_for_entry


class StudyChatPreflightError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


def validate_study_chat_preclaim(
    *,
    session: StudySessionRecord,
    request_payload: StudyChatOperationRequestPayload,
) -> None:
    """Fail deterministic Session/request conflicts before execution is claimed."""
    # Catalog/schema drift is a local configuration failure. Detect it before
    # claim, attachment staging, embeddings, or any model/tool execution.
    try:
        for name, spec in TOOL_CATALOG[CHAT_STAGE].items():
            entry = resolve_tool_manifest_entry(
                workflow=HarnessWorkflow.STUDY_CHAT,
                offered_in_stage=HarnessStage.STUDY_CHAT_REPLY,
                transport_name=name,
            )
            if spec["description"] != entry.display.provider_description:
                raise ValueError("study_tool_description_manifest_mismatch")
            provider_function_for_entry(entry)
    except (ValueError, RuntimeError, KeyError) as exc:
        raise StudyChatPreflightError("study_tool_catalog_invalid") from exc
    if session.revision != request_payload.expected_session_revision:
        raise StudyChatPreflightError("study_chat_preflight_revision_changed")
    if session.scene_profile is not None and not session.scene_instance_id:
        raise StudyChatPreflightError("session_scene_binding_required")
    if request_payload.message_kind == "scheduled_follow_up":
        target = next(
            (
                item
                for item in session.pending_follow_ups
                if item.id == request_payload.follow_up_id
                and item.status == "pending"
            ),
            None,
        )
        if target is None:
            raise StudyChatPreflightError("follow_up_not_pending")
