from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from fastapi import HTTPException

from app.models.domain import DialogueTurnRecord, StudyChatResult, StudySessionRecord
from app.services.local_store import LocalJsonStore


class StudySessionService:
    def __init__(self, store: LocalJsonStore) -> None:
        self.store = store

    def create_session(
        self, *, document_id: str, persona_id: str, section_id: str
    ) -> StudySessionRecord:
        session = StudySessionRecord(
            id=f"session-{uuid4().hex[:10]}",
            document_id=document_id,
            persona_id=persona_id,
            section_id=section_id,
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

    def _load_sessions(self) -> list[StudySessionRecord]:
        return self.store.load_list("sessions", StudySessionRecord)

    def _save_sessions(self, sessions: list[StudySessionRecord]) -> None:
        self.store.save_list("sessions", sessions)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
