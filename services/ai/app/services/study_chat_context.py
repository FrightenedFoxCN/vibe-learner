from __future__ import annotations

from app.models.domain import Citation


def _compose_hidden_prefixed_message(*, message: str, hidden_message_prefix: str) -> str:
    visible_message = message.strip()
    hidden_prefix = hidden_message_prefix.strip()
    if not hidden_prefix:
        return visible_message
    if not visible_message:
        return hidden_prefix
    return (
        "以下内容是上一轮遗留的隐藏衔接上下文，只用于帮助你承接本轮，不要把它当成学习者这次显式发言来逐条复述：\n"
        f"{hidden_prefix}\n\n"
        f"学习者这一轮真正发出的新消息：{visible_message}"
    )


def _resolve_session_state_context(*, session_tool_runtime, follow_up_id: str) -> str:
    runtime_state = session_tool_runtime.session_context().strip()
    if follow_up_id.strip():
        runtime_state = (
            f"{runtime_state}\n当前这轮是已触发的自动续接 follow-up={follow_up_id.strip()}，"
            "不要再把它当成仍未处理的待办。"
        ).strip()
    return runtime_state


def _compose_session_prompt(*, session, session_state_context: str) -> str:
    base = session.session_system_prompt.strip()
    if not session_state_context:
        return base
    if not base:
        return f"会话动态状态：\n{session_state_context}"
    return f"{base}\n\n会话动态状态：\n{session_state_context}"


def _merge_chat_citations(base: list[Citation], extra: list[Citation]) -> list[Citation]:
    merged: list[Citation] = []
    seen: set[tuple[str, str, int, int, str]] = set()
    for citation in [*(base or []), *(extra or [])]:
        key = (
            citation.source_kind,
            citation.source_id,
            citation.page_start,
            citation.page_end,
            citation.title,
        )
        if key in seen:
            continue
        seen.add(key)
        merged.append(citation)
    return merged


def _resolve_session_document(document_id: str, plan, *, document_service):
    resolved_document_id = document_id.strip() or (plan.document_id.strip() if plan is not None else "")
    if not resolved_document_id:
        return None
    return document_service.require_document(resolved_document_id)


def _scene_profile_summary(session) -> str:
    if not session.scene_profile:
        return ""
    return session.scene_profile.summary.strip()
