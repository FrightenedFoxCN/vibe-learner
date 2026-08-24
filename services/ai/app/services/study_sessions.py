from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal
from uuid import uuid4

from fastapi import HTTPException

from app.models.domain import (
    DialogueTurnRecord,
    LearnerAttachmentRecord,
    ProjectedPdfOverlayRecord,
    SessionAffinityEventRecord,
    SessionAffinityStateRecord,
    SessionFollowUpRecord,
    SessionMemoryRecord,
    SessionPlanConfirmationRecord,
    SessionProjectedPdfRecord,
    SceneProfileRecord,
    StudyChatResult,
    StudySessionRecord,
)
from app.persistence.study_session_repository import (
    StudyQuestionAttemptCommitRace,
    StudyQuestionAttemptGradingUnavailable,
    StudyQuestionAttemptRequestMismatch,
    StudyQuestionAttemptRevisionConflict,
    StudyQuestionAttemptTurnAlreadyAnswered,
    StudyQuestionAttemptTurnNotFound,
    StudySessionAlreadyExists,
    StudySessionNotFound,
    StudySessionRepository,
    StudySessionRevisionConflict,
)
from app.models.study_question import StudyQuestionAttemptResponseV1
from app.services.local_store import LocalJsonStore


class StudySessionService:
    def __init__(
        self,
        store: LocalJsonStore,
        *,
        repository: StudySessionRepository | None = None,
    ) -> None:
        self.store = store
        # Import a legacy JSON mirror before switching this service to database
        # authority. New writes never use aggregate save_list.
        self.store.load_list("sessions", StudySessionRecord)
        self.repository = repository or StudySessionRepository(store.database)

    def create_session(
        self,
        *,
        session_id: str | None = None,
        document_id: str,
        persona_id: str,
        plan_id: str | None = None,
        scene_instance_id: str = "",
        scene_profile: SceneProfileRecord | None = None,
        study_unit_id: str,
        study_unit_title: str = "",
        theme_hint: str = "",
        session_system_prompt: str = "",
    ) -> StudySessionRecord:
        session = StudySessionRecord(
            id=session_id or f"session-{uuid4().hex[:10]}",
            document_id=document_id,
            persona_id=persona_id,
            plan_id=plan_id,
            scene_instance_id=scene_instance_id,
            scene_profile=scene_profile,
            study_unit_id=study_unit_id,
            study_unit_title=study_unit_title,
            theme_hint=theme_hint,
            session_system_prompt=session_system_prompt,
            status="active",
            turns=[],
            revision=0,
            last_turn_sequence=0,
            prepared_study_unit_ids=[],
            pending_follow_ups=[],
            session_memory=[],
            affinity_state=SessionAffinityStateRecord(),
            plan_confirmations=[],
            projected_pdf=None,
            created_at=_now(),
            updated_at=_now(),
        )
        try:
            created = self.repository.create(session)
        except StudySessionAlreadyExists as exc:
            raise HTTPException(status_code=409, detail="session_already_exists") from exc
        return created

    def append_turn(
        self,
        *,
        session_id: str,
        learner_message: str,
        learner_message_kind: str = "learner",
        learner_attachments: list[LearnerAttachmentRecord] | None = None,
        result: StudyChatResult,
        prepared_study_unit_id: str | None = None,
    ) -> StudySessionRecord:
        created_at = _now()
        turn_id = f"turn-{uuid4().hex[:16]}"

        def mutation(session: StudySessionRecord) -> None:
            next_sequence = session.last_turn_sequence + 1
            session.turns.append(
                DialogueTurnRecord(
                    id=turn_id,
                    sequence=next_sequence,
                    learner_message=learner_message,
                    learner_message_kind=learner_message_kind,
                    learner_attachments=learner_attachments or [],
                    assistant_reply=result.reply,
                    citations=result.citations,
                    character_events=result.character_events,
                    rich_blocks=result.rich_blocks,
                    interactive_question=result.interactive_question,
                    persona_slot_trace=result.persona_slot_trace,
                    memory_trace=result.memory_trace,
                    tool_calls=result.tool_calls,
                    scene_profile=result.scene_profile,
                    model_recoveries=result.model_recoveries,
                    created_at=created_at,
                )
            )
            session.last_turn_sequence = next_sequence
            if prepared_study_unit_id:
                normalized = prepared_study_unit_id.strip()
                if normalized and normalized not in session.prepared_study_unit_ids:
                    session.prepared_study_unit_ids.append(normalized)
            if result.scene_profile is not None:
                session.scene_profile = result.scene_profile
            session.updated_at = created_at

        updated = self._mutate(session_id=session_id, mutation=mutation)
        return updated

    def update_session(
        self,
        *,
        session_id: str,
        study_unit_id: str | None = None,
        scene_instance_id: str | None = None,
        scene_profile: SceneProfileRecord | None = None,
        has_scene_profile: bool = False,
        study_unit_title: str | None = None,
        theme_hint: str | None = None,
        session_system_prompt: str | None = None,
    ) -> StudySessionRecord:
        updated_at = _now()

        def mutation(session: StudySessionRecord) -> None:
            if study_unit_id is not None:
                if study_unit_id != session.study_unit_id:
                    self._cancel_pending_follow_ups(session, canceled_at=updated_at)
                session.study_unit_id = study_unit_id
            if scene_instance_id is not None:
                session.scene_instance_id = scene_instance_id
            if has_scene_profile:
                session.scene_profile = scene_profile
            if study_unit_title is not None:
                session.study_unit_title = study_unit_title
            if theme_hint is not None:
                session.theme_hint = theme_hint
            if session_system_prompt is not None:
                session.session_system_prompt = session_system_prompt
            session.updated_at = updated_at

        updated = self._mutate(session_id=session_id, mutation=mutation)
        return updated

    def schedule_follow_up(
        self,
        *,
        session_id: str,
        delay_seconds: int,
        hidden_message: str,
        reason: str = "",
    ) -> SessionFollowUpRecord:
        created_at = _now()
        follow_up = SessionFollowUpRecord(
            id=f"follow-up-{uuid4().hex[:10]}",
            delay_seconds=max(0, delay_seconds),
            due_at=(datetime.now(timezone.utc) + timedelta(seconds=max(0, delay_seconds))).isoformat(),
            hidden_message=hidden_message.strip(),
            reason=reason.strip(),
            created_at=created_at,
        )

        def mutation(session: StudySessionRecord) -> None:
            session.pending_follow_ups.append(follow_up)
            session.updated_at = created_at

        self._mutate(session_id=session_id, mutation=mutation)
        return follow_up

    def complete_follow_up(self, *, session_id: str, follow_up_id: str) -> StudySessionRecord:
        completed_at = _now()

        def mutation(session: StudySessionRecord) -> None:
            for item in session.pending_follow_ups:
                if item.id != follow_up_id:
                    continue
                item.status = "completed"
                item.completed_at = completed_at
                session.updated_at = completed_at
                return
            raise HTTPException(status_code=404, detail="follow_up_not_found")

        updated = self._mutate(session_id=session_id, mutation=mutation)
        return updated

    def cancel_pending_follow_ups(self, *, session_id: str) -> StudySessionRecord:
        canceled_at = _now()

        def mutation(session: StudySessionRecord) -> bool | None:
            changed = self._cancel_pending_follow_ups(session, canceled_at=canceled_at)
            if not changed:
                return False
            session.updated_at = canceled_at
            return None

        updated = self._mutate(session_id=session_id, mutation=mutation)
        return updated

    def upsert_session_memory(
        self,
        *,
        session_id: str,
        key: str,
        content: str,
        source: str = "tool_call",
    ) -> StudySessionRecord:
        normalized_key = key.strip()
        normalized_content = content.strip()
        if not normalized_key or not normalized_content:
            raise HTTPException(status_code=422, detail="session_memory_invalid")
        mutation_time = _now()
        memory_id = f"memory-{uuid4().hex[:10]}"

        def mutation(session: StudySessionRecord) -> None:
            existing = next(
                (item for item in session.session_memory if item.key == normalized_key),
                None,
            )
            if existing is None:
                session.session_memory.append(
                    SessionMemoryRecord(
                        id=memory_id,
                        key=normalized_key,
                        content=normalized_content,
                        source=source,
                        created_at=mutation_time,
                        updated_at=mutation_time,
                    )
                )
            else:
                existing.content = normalized_content
                existing.source = source
                existing.updated_at = mutation_time
            session.updated_at = mutation_time

        updated = self._mutate(session_id=session_id, mutation=mutation)
        return updated

    def update_affinity(
        self,
        *,
        session_id: str,
        delta: int,
        reason: str = "",
        source: str = "tool_call",
    ) -> StudySessionRecord:
        mutation_time = _now()
        event_id = f"affinity-{uuid4().hex[:10]}"

        def mutation(session: StudySessionRecord) -> None:
            next_score = max(-100, min(100, int(session.affinity_state.score) + int(delta)))
            session.affinity_state.score = next_score
            session.affinity_state.level = _affinity_level(next_score)
            session.affinity_state.summary = reason.strip()
            session.affinity_state.updated_at = mutation_time
            session.affinity_state.events.append(
                SessionAffinityEventRecord(
                    id=event_id,
                    delta=int(delta),
                    reason=reason.strip(),
                    source=source,
                    created_at=mutation_time,
                )
            )
            session.affinity_state.events = session.affinity_state.events[-12:]
            session.updated_at = mutation_time

        updated = self._mutate(session_id=session_id, mutation=mutation)
        return updated

    def create_plan_confirmation(
        self,
        *,
        session_id: str,
        confirmation: SessionPlanConfirmationRecord,
    ) -> StudySessionRecord:
        updated_at = _now()

        def mutation(session: StudySessionRecord) -> None:
            session.plan_confirmations.append(confirmation)
            session.updated_at = updated_at

        updated = self._mutate(session_id=session_id, mutation=mutation)
        return updated

    def resolve_plan_confirmation(
        self,
        *,
        session_id: str,
        confirmation_id: str,
        decision: str,
        note: str = "",
    ) -> tuple[StudySessionRecord, SessionPlanConfirmationRecord]:
        resolved_at = _now()
        resolved: SessionPlanConfirmationRecord | None = None

        def mutation(session: StudySessionRecord) -> None:
            nonlocal resolved
            for confirmation in session.plan_confirmations:
                if confirmation.id != confirmation_id:
                    continue
                confirmation.status = "approved" if decision == "approve" else "rejected"
                confirmation.resolution_note = note.strip()
                confirmation.resolved_at = resolved_at
                session.updated_at = resolved_at
                resolved = confirmation.model_copy(deep=True)
                return
            raise HTTPException(status_code=404, detail="plan_confirmation_not_found")

        updated = self._mutate(session_id=session_id, mutation=mutation)
        if resolved is None:
            raise RuntimeError("plan_confirmation_resolution_missing")
        return updated, resolved

    def record_question_attempt(
        self,
        *,
        session_id: str,
        turn_id: str,
        expected_session_revision: int,
        client_attempt_id: str,
        submitted_answer: str,
    ) -> StudyQuestionAttemptResponseV1:
        try:
            return self.repository.commit_question_attempt(
                session_id=session_id,
                turn_id=turn_id,
                expected_session_revision=expected_session_revision,
                client_attempt_id=client_attempt_id,
                submitted_answer=submitted_answer,
            )
        except StudySessionNotFound as exc:
            raise HTTPException(status_code=404, detail="session_not_found") from exc
        except StudyQuestionAttemptTurnNotFound as exc:
            raise HTTPException(
                status_code=404,
                detail="study_question_attempt_turn_not_found",
            ) from exc
        except StudyQuestionAttemptRequestMismatch as exc:
            raise HTTPException(
                status_code=409,
                detail="study_question_attempt_request_mismatch",
            ) from exc
        except StudyQuestionAttemptTurnAlreadyAnswered as exc:
            raise HTTPException(
                status_code=409,
                detail="study_question_attempt_turn_already_answered",
            ) from exc
        except StudyQuestionAttemptGradingUnavailable as exc:
            raise HTTPException(
                status_code=409,
                detail="study_question_attempt_grading_unavailable",
            ) from exc
        except StudyQuestionAttemptRevisionConflict as exc:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "study_question_attempt_revision_conflict",
                    "actual_revision": exc.actual_revision,
                },
            ) from exc
        except StudyQuestionAttemptCommitRace as exc:
            raise HTTPException(
                status_code=409,
                detail="study_question_attempt_commit_race",
            ) from exc

    def list_attachments(
        self,
        *,
        session_id: str,
        kind: str | None = None,
        transient_attachments: list[LearnerAttachmentRecord] | None = None,
    ) -> list[LearnerAttachmentRecord]:
        session = self.require_session(session_id)
        attachments: list[LearnerAttachmentRecord] = []
        seen: set[str] = set()
        for turn in session.turns:
            for attachment in turn.learner_attachments:
                if attachment.attachment_id in seen:
                    continue
                seen.add(attachment.attachment_id)
                attachments.append(attachment)
        for attachment in transient_attachments or []:
            if attachment.attachment_id in seen:
                continue
            seen.add(attachment.attachment_id)
            attachments.append(attachment)
        if kind:
            return [item for item in attachments if item.kind == kind]
        return attachments

    def require_attachment(
        self,
        *,
        session_id: str,
        attachment_id: str,
        transient_attachments: list[LearnerAttachmentRecord] | None = None,
    ) -> LearnerAttachmentRecord:
        normalized_id = attachment_id.strip()
        for attachment in self.list_attachments(
            session_id=session_id,
            transient_attachments=transient_attachments,
        ):
            if attachment.attachment_id == normalized_id:
                return attachment
        raise HTTPException(status_code=404, detail="session_attachment_not_found")

    def upsert_projected_pdf(
        self,
        *,
        session_id: str,
        projected_pdf: SessionProjectedPdfRecord,
    ) -> StudySessionRecord:
        updated_at = _now()

        def mutation(session: StudySessionRecord) -> None:
            session.projected_pdf = projected_pdf.model_copy(deep=True)
            session.updated_at = updated_at

        updated = self._mutate(session_id=session_id, mutation=mutation)
        return updated

    def focus_projected_pdf_page(
        self,
        *,
        session_id: str,
        page_number: int,
    ) -> StudySessionRecord:
        updated_at = _now()

        def mutation(session: StudySessionRecord) -> None:
            if session.projected_pdf is None:
                raise HTTPException(status_code=409, detail="projected_pdf_not_set")
            session.projected_pdf.page_number = max(1, int(page_number))
            session.projected_pdf.updated_at = updated_at
            session.updated_at = updated_at

        updated = self._mutate(session_id=session_id, mutation=mutation)
        return updated

    def append_projected_pdf_overlay(
        self,
        *,
        session_id: str,
        overlay: ProjectedPdfOverlayRecord,
        page_number: int | None = None,
    ) -> StudySessionRecord:
        updated_at = _now()

        def mutation(session: StudySessionRecord) -> None:
            if session.projected_pdf is None:
                raise HTTPException(status_code=409, detail="projected_pdf_not_set")
            session.projected_pdf.overlays.append(overlay.model_copy(deep=True))
            session.projected_pdf.overlays = session.projected_pdf.overlays[-24:]
            if page_number:
                session.projected_pdf.page_number = max(1, int(page_number))
            session.projected_pdf.updated_at = updated_at
            session.updated_at = updated_at

        updated = self._mutate(session_id=session_id, mutation=mutation)
        return updated

    def clear_projected_pdf_overlays(
        self,
        *,
        session_id: str,
        page_number: int | None = None,
    ) -> StudySessionRecord:
        updated_at = _now()

        def mutation(session: StudySessionRecord) -> None:
            if session.projected_pdf is None:
                raise HTTPException(status_code=409, detail="projected_pdf_not_set")
            if page_number is None:
                session.projected_pdf.overlays = []
            else:
                normalized_page = max(1, int(page_number))
                session.projected_pdf.overlays = [
                    item
                    for item in session.projected_pdf.overlays
                    if item.page_number != normalized_page
                ]
            session.projected_pdf.updated_at = updated_at
            session.updated_at = updated_at

        updated = self._mutate(session_id=session_id, mutation=mutation)
        return updated

    def require_session(
        self, session_id: str, sessions: list[StudySessionRecord] | None = None
    ) -> StudySessionRecord:
        if sessions is None:
            try:
                return self.repository.require(session_id)
            except StudySessionNotFound as exc:
                raise HTTPException(status_code=404, detail="session_not_found") from exc
        for session in sessions:
            if session.id == session_id:
                return session
        raise HTTPException(status_code=404, detail="session_not_found")

    def list_sessions(
        self,
        *,
        document_id: str | None = None,
        persona_id: str | None = None,
        plan_id: str | None = None,
        scene_id: str | None = None,
        study_unit_id: str | None = None,
    ) -> list[StudySessionRecord]:
        sessions = self._load_sessions()
        result = sessions
        if document_id:
            result = [session for session in result if session.document_id == document_id]
        if persona_id:
            result = [session for session in result if session.persona_id == persona_id]
        if plan_id:
            result = [session for session in result if session.plan_id == plan_id]
        if scene_id:
            result = [
                session
                for session in result
                if session.scene_profile and session.scene_profile.scene_id == scene_id
            ]
        if study_unit_id:
            result = [session for session in result if session.study_unit_id == study_unit_id]
        return result

    def _load_sessions(self) -> list[StudySessionRecord]:
        return self.repository.list()

    def _mutate(
        self,
        *,
        session_id: str,
        mutation,
        committed_turn_policy: Literal["immutable", "answer_patch"] = "immutable",
    ) -> StudySessionRecord:
        try:
            return self.repository.mutate(
                session_id=session_id,
                mutation=mutation,
                committed_turn_policy=committed_turn_policy,
            )
        except StudySessionNotFound as exc:
            raise HTTPException(status_code=404, detail="session_not_found") from exc
        except StudySessionRevisionConflict as exc:
            raise HTTPException(status_code=409, detail="session_revision_conflict") from exc

    def _cancel_pending_follow_ups(
        self,
        session: StudySessionRecord,
        *,
        canceled_at: str | None = None,
    ) -> bool:
        changed = False
        effective_canceled_at = canceled_at or _now()
        for item in session.pending_follow_ups:
            if item.status != "pending":
                continue
            item.status = "canceled"
            item.canceled_at = effective_canceled_at
            changed = True
        return changed


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _affinity_level(score: int) -> str:
    if score >= 60:
        return "trusted"
    if score >= 20:
        return "warm"
    if score <= -40:
        return "strained"
    if score <= -10:
        return "guarded"
    return "neutral"
