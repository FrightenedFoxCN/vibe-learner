from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.models.domain import (
    DialogueTurnRecord,
    SceneProfileRecord,
    StudyChatResult,
    StudySessionRecord,
)
from app.services.local_store import LocalJsonStore


class StudySessionService:
    def __init__(self, store: LocalJsonStore) -> None:
        self.store = store

    def create_session(
        self,
        *,
        session_id: str | None = None,
        document_id: str,
        persona_id: str,
        scene_instance_id: str = "",
        scene_profile: SceneProfileRecord | None = None,
        section_id: str,
        section_title: str = "",
        theme_hint: str = "",
        session_system_prompt: str = "",
    ) -> StudySessionRecord:
        session = StudySessionRecord(
            id=session_id or f"session-{uuid4().hex[:10]}",
            document_id=document_id,
            persona_id=persona_id,
            scene_instance_id=scene_instance_id,
            scene_profile=scene_profile,
            section_id=section_id,
            section_title=section_title,
            theme_hint=theme_hint,
            session_system_prompt=session_system_prompt,
            status="active",
            turns=[],
            created_at=_now(),
            updated_at=_now(),
        )
        sessions = self._load_sessions()
        sessions.append(session)
        self._save_sessions(sessions)
        return session

    def append_turn(
        self, *, session_id: str, learner_message: str, result: StudyChatResult
    ) -> StudySessionRecord:
        sessions = self._load_sessions()
        session = self.require_session(session_id, sessions)
        session.turns.append(
            DialogueTurnRecord(
                learner_message=learner_message,
                assistant_reply=result.reply,
                citations=result.citations,
                character_events=result.character_events,
                rich_blocks=result.rich_blocks,
                interactive_question=result.interactive_question,
                persona_slot_trace=result.persona_slot_trace,
                memory_trace=result.memory_trace,
                tool_calls=result.tool_calls,
                scene_profile=result.scene_profile,
                created_at=_now(),
            )
        )
        if result.scene_profile is not None:
            session.scene_profile = result.scene_profile
        session.updated_at = _now()
        self._save_sessions(sessions)
        return session

    def update_session(
        self,
        *,
        session_id: str,
        section_id: str | None = None,
        scene_instance_id: str | None = None,
        scene_profile: SceneProfileRecord | None = None,
        has_scene_profile: bool = False,
        section_title: str | None = None,
        session_system_prompt: str | None = None,
    ) -> StudySessionRecord:
        sessions = self._load_sessions()
        session = self.require_session(session_id, sessions)
        if section_id is not None:
            session.section_id = section_id
        if scene_instance_id is not None:
            session.scene_instance_id = scene_instance_id
        if has_scene_profile:
            session.scene_profile = scene_profile
        if section_title is not None:
            session.section_title = section_title
        if session_system_prompt is not None:
            session.session_system_prompt = session_system_prompt
        session.updated_at = _now()
        self._save_sessions(sessions)
        return session

    def append_attempt_turn(
        self,
        *,
        session_id: str,
        learner_message: str,
        assistant_reply: str,
    ) -> StudySessionRecord:
        sessions = self._load_sessions()
        session = self.require_session(session_id, sessions)
        session.turns.append(
            DialogueTurnRecord(
                learner_message=learner_message,
                assistant_reply=assistant_reply,
                citations=[],
                character_events=[],
                interactive_question=None,
                created_at=_now(),
            )
        )
        session.updated_at = _now()
        self._save_sessions(sessions)
        return session

    def require_session(
        self, session_id: str, sessions: list[StudySessionRecord] | None = None
    ) -> StudySessionRecord:
        if sessions is None:
            sessions = self._load_sessions()
        for session in sessions:
            if session.id == session_id:
                return session
        raise HTTPException(status_code=404, detail="session_not_found")

    def list_sessions(
        self,
        *,
        document_id: str | None = None,
        persona_id: str | None = None,
        scene_id: str | None = None,
        section_id: str | None = None,
    ) -> list[StudySessionRecord]:
        sessions = self._load_sessions()
        result = sessions
        if document_id:
            result = [session for session in result if session.document_id == document_id]
        if persona_id:
            result = [session for session in result if session.persona_id == persona_id]
        if scene_id:
            result = [
                session
                for session in result
                if session.scene_profile and session.scene_profile.scene_id == scene_id
            ]
        if section_id:
            result = [session for session in result if session.section_id == section_id]
        return result

    def _load_sessions(self) -> list[StudySessionRecord]:
        return self.store.load_list("sessions", StudySessionRecord)

    def _save_sessions(self, sessions: list[StudySessionRecord]) -> None:
        self.store.save_list("sessions", sessions)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
