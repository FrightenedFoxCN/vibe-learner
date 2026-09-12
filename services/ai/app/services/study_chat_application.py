from __future__ import annotations

from datetime import UTC, datetime
from fastapi import HTTPException
from app.models.harness import (
    HarnessCommitEvidenceV3,
    HarnessCommitStatus,
    HarnessCheckStatus,
    HarnessCheckV2,
    HarnessCommittedResourceRefV3,
    HarnessContractRef,
    HarnessDigestAlgorithm,
    HarnessDigestScope,
    HarnessResourceRefV3,
    HarnessResourceType,
    HarnessStage,
    canonical_harness_digest,
)
from app.models.study_chat_operation import (
    StudyChatAttachmentManifestEntry,
    StudyChatOperationRequestPayload,
    StudyChatOperationStatus,
)
from app.persistence.study_chat_operation_repository import (
    StudyChatOperationAlreadyActive,
    StudyChatOperationRequestMismatch,
    StudyChatOperationRevisionConflict,
    StudyChatOperationSessionNotFound,
)
from app.persistence.harness_artifact_repository import HarnessArtifactRepository
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.services.learning_plan_chat_runtime import LearningPlanChatToolRuntime
from app.services.model_recovery import consume_model_recovery_state, reset_model_recovery_state
from app.services.study_chat_attachments import StudyChatAttachmentService
from app.services.study_chat_preflight import StudyChatPreflightError, validate_study_chat_preclaim
from app.models.study_chat_effect import StudyMemoryUpsertEffectProposalV1
from app.services.study_grounding import parse_verbatim_memory
from app.services.study_session_chat_runtime import StudySessionChatToolRuntime
from app.services.study_v3 import (
    StudyChatInputManifest,
    StudyChatRuntimeOutputV1,
    StudyHarnessArtifactResolver,
    StudyV3ReplyAdapter,
    build_study_context,
    decode_study_snapshot,
    StudyV3SnapshotService,
)
from app.services.harness_runtime import (
    HarnessOperationRuntime,
    HarnessRuntimeGenerationError,
    HarnessRuntimeRequest,
    HarnessRuntimeStageAdapter,
)
from app.models.study_chat_commit import (
    build_study_chat_operation_binding,
    build_study_session_turn_committed_projection,
    validate_study_chat_operation_commit,
)
from app.persistence.models import StudyChatOperationRow

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from app.core.settings import Settings
from app.core.logging import get_logger
from app.models.study_chat_operation import StudyChatMessageKind
from app.models.study_chat_operation import StudyChatOperationReceipt
from app.services.study_chat_errors import StudyChatApplicationError, map_chat_generation_error
from app.services.study_chat_context import (
    _compose_hidden_prefixed_message, _resolve_session_state_context,
    _compose_session_prompt, _merge_chat_citations, _resolve_session_document,
    _scene_profile_summary,
)

if TYPE_CHECKING:
    from app.persistence.study_chat_operation_repository import StudyChatOperationRepository
    from app.persistence.study_session_repository import StudySessionRepository
    from app.services.local_store import LocalJsonStore
    from app.services.model_provider import ModelProvider
    from app.services.study_sessions import StudySessionService
    from app.services.persona import PersonaEngine
    from app.services.plans import LearningPlanService
    from app.services.documents import DocumentService
    from app.services.session_scene import SessionSceneService
    from app.services.pedagogy import PedagogyOrchestrator


@dataclass(frozen=True)
class StudyChatDependencies:
    study_chat_operation_repository: StudyChatOperationRepository
    study_session_repository: StudySessionRepository
    study_session_service: StudySessionService
    store: LocalJsonStore
    model_provider: ModelProvider
    runtime_settings: Settings
    persona_engine: PersonaEngine
    plan_service: LearningPlanService
    document_service: DocumentService
    session_scene_service: SessionSceneService
    pedagogy_orchestrator: PedagogyOrchestrator
    attachments: StudyChatAttachmentService = field(default_factory=StudyChatAttachmentService)


@dataclass(frozen=True)
class StudyChatExecutionContext:
    session_id: str
    message: str
    message_kind: StudyChatMessageKind
    follow_up_id: str
    hidden_message_prefix: str
    learner_attachments: tuple
    attachment_context: str
    learner_multimodal_parts: tuple
    operation_id: str
    execution_token: str

    def __post_init__(self):
        object.__setattr__(self, "learner_attachments", tuple(self.learner_attachments))
        object.__setattr__(self, "learner_multimodal_parts", tuple(self.learner_multimodal_parts))


class StudyChatApplication:
    def __init__(self, dependencies: StudyChatDependencies):
        self.dependencies = dependencies

    def admit(
        self, *, session_id: str, client_request_id: str,
        expected_session_revision: int, message: str, message_kind: str,
        follow_up_id: str, hidden_message_prefix: str, attachment_inputs=None,
    ) -> StudyChatOperationReceipt:
        try:
            return _admit_and_run_study_chat(
                session_id=session_id, client_request_id=client_request_id,
                expected_session_revision=expected_session_revision,
                message=message, message_kind=message_kind,
                follow_up_id=follow_up_id, hidden_message_prefix=hidden_message_prefix,
                attachment_inputs=attachment_inputs,
                dependencies=self.dependencies, execute=self.execute,
            )
        except HTTPException as exc:
            # Existing domain adapters still use HTTPException; contain that
            # compatibility here and expose only application errors to callers.
            raise StudyChatApplicationError(exc.status_code, exc.detail) from exc

    def execute(self, context: StudyChatExecutionContext) -> dict[str, object]:
        return _run_study_chat(context, dependencies=self.dependencies)

    def get_receipt(self, *, session_id: str, client_request_id: str) -> StudyChatOperationReceipt:
        operation = self.dependencies.study_chat_operation_repository.require(
            session_id=session_id, client_request_id=client_request_id,
        )
        _cleanup_terminal_study_chat_staging(operation, dependencies=self.dependencies)
        return _receipt(operation, dependencies=self.dependencies)


logger = get_logger("vibe_learner.study_chat_application")


def _runtime_error_retry_attempts(exc: RuntimeError) -> int:
    attempts = getattr(exc, "attempts", 1)
    return attempts if isinstance(attempts, int) and attempts > 0 else 1


def _admit_and_run_study_chat(
    *,
    session_id: str,
    client_request_id: str,
    expected_session_revision: int,
    message: str,
    message_kind: str,
    follow_up_id: str,
    hidden_message_prefix: str,
    attachment_inputs=None,
    execute,
    dependencies: StudyChatDependencies,
) -> StudyChatOperationReceipt:
    try:
        parse_verbatim_memory(message, (message_kind or "learner").strip() or "learner")
    except ValueError as exc:
        raise StudyChatApplicationError(status_code=422, detail=str(exc)) from exc
    request_payload = StudyChatOperationRequestPayload(
        message=message,
        message_kind=(message_kind or "learner").strip() or "learner",
        follow_up_id=follow_up_id,
        hidden_message_prefix=hidden_message_prefix,
        expected_session_revision=expected_session_revision,
        attachments=[
            StudyChatAttachmentManifestEntry.model_validate(item)
            for item in dependencies.attachments.manifest(attachment_inputs or [])
        ],
    )
    try:
        operation = dependencies.study_chat_operation_repository.admit(
            session_id=session_id,
            client_request_id=client_request_id,
            request_payload=request_payload,
        )
    except StudyChatOperationSessionNotFound as exc:
        raise StudyChatApplicationError(status_code=404, detail="session_not_found") from exc
    except StudyChatOperationRevisionConflict as exc:
        raise StudyChatApplicationError(
            status_code=409,
            detail={
                "code": "study_chat_session_revision_conflict",
                "actual_revision": exc.actual_revision,
            },
        ) from exc
    except StudyChatOperationRequestMismatch as exc:
        raise StudyChatApplicationError(status_code=409, detail="study_chat_request_id_reused") from exc
    except StudyChatOperationAlreadyActive as exc:
        raise StudyChatApplicationError(status_code=409, detail="study_chat_operation_already_active") from exc

    if operation.status != StudyChatOperationStatus.ADMITTED:
        _cleanup_terminal_study_chat_staging(operation, dependencies=dependencies)
        return _receipt(operation, dependencies=dependencies)
    try:
        validate_study_chat_preclaim(
            session=dependencies.study_session_service.require_session(session_id),
            request_payload=operation.request_payload,
        )
        dependencies.attachments.validate(
            attachment_inputs or [],
            allow_image_input=dependencies.model_provider.supports_chat_page_image_tools(),
        )
    except (HTTPException, StudyChatPreflightError) as exc:
        detail = exc.detail if isinstance(exc, HTTPException) else exc.code
        not_committed = dependencies.study_chat_operation_repository.mark_not_committed(
            operation_id=operation.operation_id,
            error_code=f"study_chat_not_committed_{str(detail)}"[:128],
        )
        return _receipt(not_committed, dependencies=dependencies)

    runtime_settings = dependencies.runtime_settings
    operation, claimed = dependencies.study_chat_operation_repository.claim(
        operation_id=operation.operation_id,
        timeout_seconds=runtime_settings.openai_timeout_seconds
        * (runtime_settings.openai_chat_tool_max_rounds + 2),
    )
    if not claimed:
        return _receipt(operation, dependencies=dependencies)
    try:
        prepared = dependencies.attachments.prepare(
            store=dependencies.store,
            session_id=session_id,
            files=[],
            allow_image_input=dependencies.model_provider.supports_chat_page_image_tools(),
            inputs=attachment_inputs or [],
            operation_id=operation.operation_id,
            inputs_validated=True,
        )
        response_payload = execute(StudyChatExecutionContext(
            session_id=session_id,
            message=message,
            message_kind=operation.request_payload.message_kind,
            follow_up_id=follow_up_id,
            hidden_message_prefix=hidden_message_prefix,
            learner_attachments=prepared.records,
            attachment_context=prepared.attachment_context,
            learner_multimodal_parts=prepared.multimodal_parts,
            operation_id=operation.operation_id,
            execution_token=operation.execution_token,
        ))
        committed = dependencies.study_chat_operation_repository.require(
            session_id=session_id,
            client_request_id=client_request_id,
        )
        if committed.response_payload != response_payload:
            raise RuntimeError("study_chat_committed_response_mismatch")
        return _receipt(committed, dependencies=dependencies)
    except Exception as exc:
        error_code = _study_chat_uncertain_error_code(exc)
        harness_trace = _study_chat_terminal_harness_trace(operation.operation_id, dependencies=dependencies)
        terminal = dependencies.study_chat_operation_repository.mark_uncertain(
            operation_id=operation.operation_id,
            execution_token=operation.execution_token,
            error_code=error_code,
            harness_trace=harness_trace,
        )
        if terminal.status != StudyChatOperationStatus.COMMITTED:
            try:
                dependencies.attachments.cleanup(
                    store=dependencies.store,
                    session_id=session_id,
                    operation_id=operation.operation_id,
                )
            except Exception:
                logger.exception(
                    "study_chat.attachment_cleanup_failed session_id=%s operation_id=%s",
                    session_id,
                    operation.operation_id,
                )
        logger.exception(
            "study_chat.operation_uncertain session_id=%s operation_id=%s error_code=%s",
            session_id,
            operation.operation_id,
            error_code,
        )
        return _receipt(terminal, dependencies=dependencies)


def _cleanup_terminal_study_chat_staging(operation, *, dependencies: StudyChatDependencies) -> None:
    if operation.status not in {
        StudyChatOperationStatus.NOT_COMMITTED,
        StudyChatOperationStatus.UNCERTAIN,
    }:
        return
    try:
        dependencies.attachments.cleanup(
            store=dependencies.store,
            session_id=operation.session_id,
            operation_id=operation.operation_id,
        )
    except Exception:
        logger.exception(
            "study_chat.attachment_recovery_cleanup_failed session_id=%s operation_id=%s",
            operation.session_id,
            operation.operation_id,
        )


def _study_chat_uncertain_error_code(exc: Exception) -> str:
    if isinstance(exc, (HTTPException, StudyChatApplicationError)):
        detail = exc.detail if isinstance(exc.detail, str) else "http_error"
        return f"study_chat_uncertain_{detail}"[:128]
    return "study_chat_execution_uncertain"


def _study_chat_terminal_harness_trace(operation_id: str, *, dependencies: StudyChatDependencies):
    """Return the terminal reply trace without exposing it on the public receipt."""

    try:
        binding = dependencies.study_chat_operation_repository.require_harness_operation(
            operation_id
        )
    except Exception:
        return None
    runtime_repository = HarnessRuntimeRepository(
        dependencies.study_chat_operation_repository.database
    )
    traces = runtime_repository.list_operation_traces(binding.harness_operation_id)
    terminal = [
        item.terminal_trace
        for item in traces
        if item.stage == HarnessStage.STUDY_CHAT_REPLY
        and item.trace_slot == 0
        and item.terminal_trace is not None
    ]
    return terminal[-1] if terminal else None


def _run_study_chat(context: StudyChatExecutionContext, *, dependencies: StudyChatDependencies) -> dict[str, object]:
    session_id = context.session_id
    message = context.message
    message_kind = context.message_kind
    follow_up_id = context.follow_up_id
    hidden_message_prefix = context.hidden_message_prefix
    learner_attachments = list(context.learner_attachments)
    attachment_context = context.attachment_context
    learner_multimodal_parts = list(context.learner_multimodal_parts)
    operation_id = context.operation_id
    execution_token = context.execution_token
    reset_model_recovery_state()
    session = dependencies.study_session_service.require_session(session_id)
    if session.scene_profile is not None and not session.scene_instance_id:
        raise StudyChatApplicationError(status_code=409, detail="session_scene_binding_required")
    normalized_message_kind = message_kind
    normalized_follow_up_id = follow_up_id.strip()
    if normalized_message_kind == "scheduled_follow_up" and normalized_follow_up_id:
        target_follow_up = next(
            (
                item
                for item in session.pending_follow_ups
                if item.id == normalized_follow_up_id and item.status == "pending"
            ),
            None,
        )
        if target_follow_up is None:
            raise StudyChatApplicationError(status_code=409, detail="follow_up_not_pending")
    persona = dependencies.persona_engine.require_persona(session.persona_id)
    active_plan = None
    if session.plan_id:
        try:
            active_plan = dependencies.plan_service.require_plan(session.plan_id)
        except HTTPException:
            active_plan = None
    bound_session_plan = active_plan
    memory_sessions = (
        dependencies.study_session_service.list_sessions(
            plan_id=session.plan_id,
            persona_id=session.persona_id,
        )
        if session.plan_id and not session.document_id
        else dependencies.study_session_service.list_sessions(
            document_id=session.document_id,
            persona_id=session.persona_id,
        )
    )
    document = _resolve_session_document(session.document_id, active_plan, document_service=dependencies.document_service)
    debug_report = None
    if document is not None:
        try:
            debug_report = dependencies.document_service.require_debug_report(document.id)
        except HTTPException:
            debug_report = None

    if active_plan is None:
        active_plan = dependencies.plan_service.find_latest_plan(
            document_id=session.document_id,
            persona_id=session.persona_id,
        )
    plan_tool_runtime = (
        LearningPlanChatToolRuntime(dependencies.plan_service, active_plan.id)
        if active_plan is not None
        else None
    )
    from app.services.study_chat_effects import StudyChatEffectCollector
    from app.models.study_chat_effect import (
        StudyFollowUpEffectAction,
        StudyFollowUpEffectProposalV1,
    )

    effect_operation_binding = (
        dependencies.study_chat_operation_repository.require_harness_operation(operation_id)
    )
    study_input_manifest = StudyChatInputManifest(
        session_id=session_id,
        document_id=session.document_id,
        plan_id=session.plan_id,
        scene_id=session.scene_instance_id,
        session_revision=session.revision,
        attachment_count=len(learner_attachments or []),
    )
    effect_collector = StudyChatEffectCollector(
        operation_id=operation_id,
        session_id=session_id,
        plan_id=bound_session_plan.id if bound_session_plan is not None else None,
        allowed_schedule_ids={
            item.id for item in bound_session_plan.schedule
        } if bound_session_plan is not None else set(),
        operation_binding=effect_operation_binding,
        effect_journal=dependencies.study_session_repository.effect_journal,
    )
    scene_tool_runtime = (
        dependencies.session_scene_service.build_tool_runtime(
            session.scene_instance_id,
            effect_collector=effect_collector,
        )
        if session.scene_instance_id
        else None
    )
    if normalized_follow_up_id:
        effect_collector.prepare_follow_up(
            StudyFollowUpEffectProposalV1(
                action=StudyFollowUpEffectAction.COMPLETE,
                follow_up_id=normalized_follow_up_id,
            )
        )
    if normalized_message_kind == "learner":
        effect_collector.prepare_follow_up(
            StudyFollowUpEffectProposalV1(
                action=StudyFollowUpEffectAction.CANCEL_PENDING,
            )
        )
    session_tool_runtime = StudySessionChatToolRuntime(
        session_service=dependencies.study_session_service,
        plan_service=dependencies.plan_service,
        session_id=session_id,
        plan_id=bound_session_plan.id if bound_session_plan is not None else None,
        transient_attachments=learner_attachments or [],
        multimodal_enabled=dependencies.model_provider.supports_chat_page_image_tools(),
        model_provider=dependencies.model_provider,
        effect_collector=effect_collector,
    )
    session_state_context = _resolve_session_state_context(
        session_tool_runtime=session_tool_runtime,
        follow_up_id=normalized_follow_up_id,
    )
    session_prompt = _compose_session_prompt(
        session=session,
        session_state_context=session_state_context,
    )
    model_message = _compose_hidden_prefixed_message(
        message=message,
        hidden_message_prefix=hidden_message_prefix,
    )
    active_plan_context = plan_tool_runtime.plan_context() if plan_tool_runtime else ""
    active_scene_summary = _scene_profile_summary(session)
    active_scene_context = (
        scene_tool_runtime.scene_context() if scene_tool_runtime else ""
    )
    protected_snapshot_payload = {
        "schema_name": "StudyChatProtectedSnapshot",
        "schema_version": "study-chat-protected-snapshot-v2",
        "dependencies": {
            "input": {
                **study_input_manifest.model_dump(mode="json"),
                "message_kind": normalized_message_kind,
                "follow_up_id": normalized_follow_up_id,
            },
            "session": session.model_dump(mode="json", exclude_none=False),
            "persona": persona.model_dump(mode="json", exclude_none=False),
            "bound_plan": (
                bound_session_plan.model_dump(mode="json", exclude_none=False)
                if bound_session_plan is not None
                else None
            ),
            "active_plan": (
                active_plan.model_dump(mode="json", exclude_none=False)
                if active_plan is not None
                else None
            ),
            "document": (
                document.model_dump(mode="json", exclude_none=False)
                if document is not None
                else None
            ),
            "document_debug": (
                debug_report.model_dump(mode="json", exclude_none=False)
                if debug_report is not None
                else None
            ),
            "memory_sessions": [
                item.model_dump(mode="json", exclude_none=False)
                for item in memory_sessions
            ],
            "session_prompt": session_prompt,
            "model_message": model_message,
            "learner_message": message,
            "active_plan_context": active_plan_context,
            "attachment_context": attachment_context,
            "learner_multimodal_parts": learner_multimodal_parts or [],
            "session_state_context": session_state_context,
            "active_scene_summary": active_scene_summary,
            "active_scene_context": active_scene_context,
            "learner_attachments": [
                item.model_dump(mode="json", exclude_none=False)
                for item in (learner_attachments or [])
            ],
        },
    }
    study_database = dependencies.study_chat_operation_repository.database
    study_artifacts = HarnessArtifactRepository(study_database)
    study_snapshot_service = StudyV3SnapshotService(study_artifacts)
    study_runtime_repository = HarnessRuntimeRepository(study_database)
    study_snapshot, study_grant_id = (
        study_snapshot_service.register_session_snapshot(
            operation_binding=effect_operation_binding,
            payload=protected_snapshot_payload,
        )
    )
    study_harness_context = build_study_context(
        operation_binding=effect_operation_binding,
        manifest=study_input_manifest,
        snapshots=(study_snapshot,),
    )
    study_runtime = HarnessOperationRuntime(
        repository=study_runtime_repository,
        artifact_resolver=StudyHarnessArtifactResolver(
            study_artifacts,
            {study_snapshot.artifact_id: study_grant_id},
        ),
    )
    reply_adapter = StudyV3ReplyAdapter()

    def generate_study_reply(_context, artifacts):
        if set(artifacts) != {study_snapshot.artifact_id}:
            raise ValueError("study_snapshot_artifact_set_mismatch")
        resolved = decode_study_snapshot(artifacts[study_snapshot.artifact_id])
        source = parse_verbatim_memory(
            resolved["dependencies"]["learner_message"],
            resolved["dependencies"]["input"]["message_kind"],
        )
        session_tool_runtime.verbatim_memory_source = source
        dependencies.study_chat_operation_repository.mark_provider_started(
            operation_id=operation_id,
            execution_token=execution_token,
        )
        try:
            result = dependencies.pedagogy_orchestrator.generate_chat_reply(
                session_id=session_id,
                persona=persona,
                message=model_message,
                message_kind=normalized_message_kind,
                study_unit_id=session.study_unit_id,
                study_unit_title=session.study_unit_title,
                theme_hint=session.theme_hint,
                active_plan=active_plan,
                session_system_prompt=session_prompt + (
                    "\n当前学习者明确请求原文保存。调用 write_session_memory，key="
                    + source.key + "；服务器从当前操作授权来源绑定原文。仅在工具成功后确认，禁止声称已提交。"
                    if source is not None else ""
                ),
                debug_report=debug_report,
                document_path=(
                    document.stored_path if document is not None else None
                ),
                previous_turns=session.turns,
                memory_sessions=memory_sessions,
                active_plan_context=active_plan_context,
                attachment_context=attachment_context,
                learner_multimodal_parts=learner_multimodal_parts or [],
                session_state_context=session_state_context,
                active_scene_summary=active_scene_summary,
                active_scene_context=active_scene_context,
                session_tool_runtime=session_tool_runtime,
                plan_tool_runtime=plan_tool_runtime,
                scene_tool_runtime=scene_tool_runtime,
            )
        except Exception as exc:
            recoveries = consume_model_recovery_state()
            if not recoveries:
                raise
            strategy = "+".join(
                dict.fromkeys(item.strategy for item in recoveries)
            )[:320]
            checks = tuple(
                HarnessCheckV2(
                    name="study_chat_model_recovery",
                    status=HarnessCheckStatus.WARNING,
                    code=f"{item.category}:{item.reason}"[:160],
                    message=item.strategy[:320],
                )
                for item in recoveries
            )
            raise HarnessRuntimeGenerationError(
                str(exc),
                checks,
                strategy or "provider_bounded_recovery",
            ) from exc
        if source is not None:
            batch = effect_collector.prepared_batch()
            writes = [effect.proposal for effect in batch.effects
                      if isinstance(effect.proposal, StudyMemoryUpsertEffectProposalV1)] if batch else []
            if not writes or writes[-1].key != source.key or writes[-1].content != source.content:
                raise RuntimeError("verbatim_memory_effect_missing")
        result.citations = _merge_chat_citations(
            result.citations,
            session_tool_runtime.response_citations(),
        )
        result.model_recoveries = consume_model_recovery_state()
        return StudyChatRuntimeOutputV1(result=result)

    try:
        runtime_adapter = HarnessRuntimeStageAdapter(
            adapter_contract=HarnessContractRef(
                name="StudyChatWorkflowAdapter",
                version="study-chat-workflow-adapter-v1",
            ),
            trace_contract=HarnessContractRef(
                name="StudyChatReply",
                version="study-chat-reply-trace-v1",
            ),
            generate=generate_study_reply,
            decode=reply_adapter.decode,
            validate=reply_adapter.validate,
        )
        runtime_prepared = study_runtime.prepare_output(
            request=HarnessRuntimeRequest(
                operation_binding=effect_operation_binding,
                stage=HarnessStage.STUDY_CHAT_REPLY,
                trace_slot=0,
                context=study_harness_context,
            ),
            adapter=runtime_adapter,
            claim_owner=f"study-chat-{operation_id}",
        )
    except RuntimeError as exc:
        terminal = next(
            (
                item.terminal_trace
                for item in reversed(
                    study_runtime_repository.list_operation_traces(
                        effect_operation_binding.harness_operation_id
                    )
                )
                if item.trace_slot == 0 and item.terminal_trace is not None
            ),
            None,
        )
        mapped_error = (
            RuntimeError(terminal.error_code)
            if terminal is not None and terminal.error_code
            else exc
        )
        http_error = map_chat_generation_error(mapped_error)
        logger.exception(
            "study_chat.error session_id=%s public_detail=%s internal_error_code=%s retry_attempts=%s",
            session_id,
            http_error.detail,
            str(exc),
            _runtime_error_retry_attempts(exc),
        )
        raise http_error from exc
    if not isinstance(runtime_prepared.output, StudyChatRuntimeOutputV1):
        raise RuntimeError("study_chat_runtime_output_invalid")
    response = runtime_prepared.output.result.model_copy(deep=True)

    def build_exchange_payload(committed_session):
        # This is a server-only committed projection used for durable operation
        # read-back. Public receipts independently project it through
        # StudyChatExchangeResponse so private grading material never crosses
        # the API boundary.
        return {
            **response.model_dump(mode="json"),
            "session": committed_session.model_dump(mode="json"),
        }

    def finalize_study_runtime(
        db_session,
        committed_session,
        committed_turn_id,
        committed_sequence,
    ):
        read_back_session, _read_back_turn = (
            dependencies.study_session_repository.get_chat_commit_read_back_in_session(
                db_session,
                session_id=session_id,
                turn_id=committed_turn_id,
            )
        )
        projection = build_study_session_turn_committed_projection(
            operation_id=effect_operation_binding.harness_operation_id,
            session=read_back_session,
            expected_session_revision=study_input_manifest.session_revision,
            turn_id=committed_turn_id,
            turn_sequence=committed_sequence,
        )
        digest = canonical_harness_digest(projection)
        effect_batch_id = f"study-turn-{committed_turn_id}"
        evidence = HarnessCommitEvidenceV3(
            status=HarnessCommitStatus.COMMITTED,
            effect_batch_id=effect_batch_id,
            payload_contract=HarnessContractRef(
                name="StudySessionTurnCommittedProjection",
                version="study-chat-turn-committed-projection-v1",
            ),
            digest_algorithm=HarnessDigestAlgorithm.SHA256,
            digest_scope=HarnessDigestScope.COMMITTED_PROJECTION,
            attempted_resource_refs=[
                HarnessResourceRefV3(
                    resource_type=HarnessResourceType.STUDY_SESSION,
                    resource_id=session_id,
                    revision=study_input_manifest.session_revision,
                )
            ],
            committed_resources=[
                HarnessCommittedResourceRefV3(
                    resource_type=HarnessResourceType.STUDY_SESSION,
                    resource_id=session_id,
                    expected_revision=study_input_manifest.session_revision,
                    committed_revision=read_back_session.revision,
                    payload_digest=digest,
                )
            ],
            payload_digest=digest,
            committed_at=datetime.now(UTC),
            rollback_reason_code="",
        )
        finalized = study_runtime.finalize_prepared_in_session(
            db_session,
            prepared=runtime_prepared,
            commit_evidence=evidence,
        )
        validate_study_chat_operation_commit(
            trace=finalized.trace,
            binding=build_study_chat_operation_binding(projection),
            projection=projection,
        )
        operation_row = db_session.get(StudyChatOperationRow, operation_id)
        if operation_row is not None:
            operation_row.harness_trace = finalized.trace.model_dump(mode="json")

    try:
        session, response_payload = (
            dependencies.study_session_repository.commit_chat_operation_turn(
                operation_id=operation_id,
                execution_token=execution_token,
                learner_message=message,
                learner_message_kind=normalized_message_kind,
                learner_attachments=learner_attachments or [],
                result=response,
                prepared_study_unit_id=(
                    session.study_unit_id
                    if normalized_message_kind == "session_prelude"
                    else None
                ),
                completed_follow_up_id="",
                cancel_pending_follow_ups=False,
                prepared_effect_batch=effect_collector.prepared_batch(),
                build_response_payload=build_exchange_payload,
                runtime_commit_callback=finalize_study_runtime,
            )
        )
    except Exception as exc:
        error_code = (str(exc).split(":", 1)[0] or type(exc).__name__)[:160]
        not_committed = HarnessCommitEvidenceV3(
            status=HarnessCommitStatus.NOT_COMMITTED,
            effect_batch_id=f"study-turn-{operation_id}",
            payload_contract=HarnessContractRef(
                name="StudySessionTurnCommittedProjection",
                version="study-chat-turn-committed-projection-v1",
            ),
            digest_algorithm=HarnessDigestAlgorithm.SHA256,
            digest_scope=HarnessDigestScope.COMMITTED_PROJECTION,
            attempted_resource_refs=[
                HarnessResourceRefV3(
                    resource_type=HarnessResourceType.STUDY_SESSION,
                    resource_id=session_id,
                    revision=study_input_manifest.session_revision,
                )
            ],
            rollback_reason_code="",
        )
        try:
            study_runtime.fail_prepared(
                prepared=runtime_prepared,
                commit_evidence=not_committed,
                error_code=error_code,
            )
        except Exception:
            logger.exception(
                "study_chat.runtime_commit_failure_terminalization_failed "
                "session_id=%s operation_id=%s",
                session_id,
                operation_id,
            )
        raise
    return response_payload

def _receipt(operation, *, dependencies: StudyChatDependencies) -> StudyChatOperationReceipt:
    return dependencies.study_chat_operation_repository.receipt(operation)

