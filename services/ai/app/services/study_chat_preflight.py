from __future__ import annotations

from app.models.domain import StudySessionRecord
from app.models.study_chat_operation import StudyChatOperationRequestPayload


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
