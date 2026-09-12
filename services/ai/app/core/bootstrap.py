from pathlib import Path
from threading import RLock

from app.services.document_parser import DocumentParser
from app.core.logging import configure_logging, get_logger
from app.core.settings import Settings
from app.persistence.database import Database
from app.persistence.harness_artifact_repository import HarnessArtifactRepository
from app.persistence.harness_effect_repository import HarnessEffectJournalRepository
from app.services.harness_effect_scanner import scan_harness_effect_journal
from app.services.study_v3 import StudyV3SnapshotService
from app.persistence.harness_runtime_repository import HarnessRuntimeRepository
from app.persistence.harness_workflow_operation_repository import HarnessWorkflowOperationRepository
from app.services.harness_runtime import HarnessOperationRuntime
from app.services.harness_broad_adoption import (
    HarnessProposalRuntimeService,
)
from app.persistence.storage import StorageManager
from app.persistence.study_session_repository import StudySessionRepository
from app.persistence.study_chat_operation_repository import StudyChatOperationRepository
from app.persistence.tavern_repository import TavernRepository
from app.persistence.migrate_local_data import migrate_from_legacy_store
from app.services.model_provider import MockModelProvider, OpenAIModelProvider
from app.services.documents import DocumentService
from app.services.local_store import LegacyLocalJsonStore, LocalJsonStore
from app.services.pedagogy import PedagogyOrchestrator
from app.services.performance import PerformanceMapper
from app.services.plans import LearningPlanService
from app.services.persona_cards import PersonaCardLibraryService
from app.services.persona import PersonaEngine
from app.services.reusable_scene_nodes import ReusableSceneNodeLibraryService
from app.services.model_tool_config import CHAT_STAGE, PLAN_STAGE, ModelToolConfigService
from app.services.runtime_settings import RuntimeSettingsService
from app.services.scene_library import SceneLibraryService
from app.services.scene_setup import SceneSetupService
from app.services.session_scene import SessionSceneService
from app.services.study_arrangement import StudyArrangementService
from app.services.study_sessions import StudySessionService
from app.services.storage_lifecycle import StorageLifecycleService
from app.services.stream_interrupts import StreamInterruptRegistry
from app.services.token_usage import TokenUsageService
from app.services.tavern import TavernService

logger = get_logger("vibe_learner.bootstrap")


class Container:
    def __init__(self, settings: Settings | None = None) -> None:
        configure_logging()
        self.base_settings = settings if settings is not None else Settings.from_env()
        self._provider_lock = RLock()
        self._started = False
        self._closed = False
        try:
            self._initialize()
        except BaseException:
            self.close()
            raise

    def _initialize(self) -> None:
        data_root = self.base_settings.resolved_storage_root
        self.storage = StorageManager(data_root)
        self.database = Database(self.base_settings.database_url)
        self.database.create_schema()
        self.harness_artifact_repository = HarnessArtifactRepository(self.database)
        self.harness_workflow_operations = HarnessWorkflowOperationRepository(self.database)
        self.harness_proposal_runtime = HarnessProposalRuntimeService(
            self.database,
            self.harness_artifact_repository,
            self.harness_workflow_operations,
        )
        self.study_v3_snapshot_service = StudyV3SnapshotService(self.harness_artifact_repository)
        self.harness_runtime = HarnessOperationRuntime(
            repository=HarnessRuntimeRepository(self.database)
        )
        self.harness_effect_journal = HarnessEffectJournalRepository(self.database)
        self.harness_effect_scanner = lambda: scan_harness_effect_journal(self.database)
        self.tavern_repository = TavernRepository(self.database)
        self.store = LocalJsonStore(self.database, self.storage)
        self.document_parser = DocumentParser(
            self.storage.ensure_runtime_temp_root(),
            ocr_engine_name=self.base_settings.ocr_engine,
            onnxtr_model_dir=self.base_settings.onnxtr_model_dir,
        )
        from app.services.document_layout import DocumentLayoutService
        self.document_layout_service = DocumentLayoutService(
            engine=self.base_settings.document_layout_engine,
            python_executable=self.base_settings.document_layout_python,
            model_path=self.base_settings.document_layout_model_path,
            model_sha256=self.base_settings.document_layout_model_sha256,
            runtime_temp_root=self.storage.ensure_runtime_temp_root(),
            timeout_seconds=self.base_settings.document_layout_timeout_seconds,
        )
        if self.base_settings.auto_migrate_local_data and self.store.count_bucket("documents") == 0:
            migrate_from_legacy_store(
                LegacyLocalJsonStore(data_root),
                self.store,
                TokenUsageService(self.database),
                data_root,
            )
        self.model_tool_config_service = ModelToolConfigService(self.store)
        self.runtime_settings_service = RuntimeSettingsService(self.store, self.base_settings)
        self.token_usage_service = TokenUsageService(self.database)
        self.stream_interrupt_registry = StreamInterruptRegistry()
        self.scene_setup_service = SceneSetupService(self.store)
        self.scene_library_service = SceneLibraryService(self.store)
        self.reusable_scene_node_library_service = ReusableSceneNodeLibraryService(self.store)
        self.persona_card_library_service = PersonaCardLibraryService(self.store)
        self.session_scene_service = SessionSceneService(self.store)
        self.model_provider = self._build_model_provider(self.runtime_settings_service.effective_settings())
        self.performance_mapper = PerformanceMapper()
        self.persona_engine = PersonaEngine(
            self.store,
            tavern_reference_counter=self.tavern_repository.count_persona_references,
        )
        self.study_arrangement_service = StudyArrangementService()
        self.document_service = DocumentService(
            self.store,
            self.document_parser,
            self.study_arrangement_service,
            harness_service=self.harness_proposal_runtime,
        )
        self.plan_service = LearningPlanService(
            self.store,
            self.study_arrangement_service,
            self.model_provider,
            harness_service=self.harness_proposal_runtime,
        )
        self.study_session_repository = StudySessionRepository(
            self.database,
            effect_journal=self.harness_effect_journal,
        )
        self.study_chat_operation_repository = StudyChatOperationRepository(
            self.database,
            chat_attachment_root=self.storage.chat_attachment_root,
        )
        self.study_session_service = StudySessionService(
            self.store,
            repository=self.study_session_repository,
        )
        self.storage_lifecycle_service = StorageLifecycleService(
            self.store,
            self.token_usage_service,
        )
        self.pedagogy_orchestrator = PedagogyOrchestrator(
            model_provider=self.model_provider,
            performance_mapper=self.performance_mapper,
        )
        self.tavern_service = TavernService(
            repository=self.tavern_repository,
            persona_engine=self.persona_engine,
            model_provider=self.model_provider,
        )

    def start(self) -> None:
        """Recover durable operations only at the explicit application start."""
        if self._closed:
            raise RuntimeError("container_closed")
        if self._started:
            return
        recovered_workflow_operations = self.harness_workflow_operations.recover_abandoned_operations()
        if recovered_workflow_operations:
            logger.warning(
                "bootstrap.harness_workflow_operations recovered=%s",
                recovered_workflow_operations,
            )
        self.document_service.recover_abandoned_operations()
        self.plan_service.recover_abandoned_operations()
        self._started = True

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        registry = getattr(self, "stream_interrupt_registry", None)
        if registry is not None:
            registry.close()
        database = getattr(self, "database", None)
        if database is not None:
            database.dispose()

    def study_chat_application(self):
        # Capture the operation's provider and settings together. Runtime
        # Settings replacement must not switch a running chat's provider.
        with self._provider_lock:
            from copy import copy
            from app.services.study_chat_application import StudyChatApplication, StudyChatDependencies

            provider = self.model_provider
            orchestrator = copy(self.pedagogy_orchestrator)
            if hasattr(orchestrator, "model_provider"):
                orchestrator.model_provider = provider
            return StudyChatApplication(StudyChatDependencies(
                study_chat_operation_repository=self.study_chat_operation_repository,
                study_session_repository=self.study_session_repository,
                study_session_service=self.study_session_service,
                store=self.store,
                model_provider=provider,
                runtime_settings=self.runtime_settings_service.effective_settings(),
                persona_engine=self.persona_engine,
                plan_service=self.plan_service,
                document_service=self.document_service,
                session_scene_service=self.session_scene_service,
                pedagogy_orchestrator=orchestrator,
                document_layout_service=self.document_layout_service,
            ))

    def update_runtime_settings(self, updates: dict[str, object]) -> None:
        with self._provider_lock:
            self.runtime_settings_service.update(updates)
            self.model_provider = self._build_model_provider(
                self.runtime_settings_service.effective_settings()
            )
            self.plan_service.model_provider = self.model_provider
            self.pedagogy_orchestrator.model_provider = self.model_provider
            self.tavern_service.model_provider = self.model_provider

    def apply_runtime_session_secrets(self, updates: dict[str, object]) -> None:
        with self._provider_lock:
            self.runtime_settings_service.apply_session_secrets(updates)
            self.model_provider = self._build_model_provider(
                self.runtime_settings_service.effective_settings()
            )
            self.plan_service.model_provider = self.model_provider
            self.pedagogy_orchestrator.model_provider = self.model_provider
            self.tavern_service.model_provider = self.model_provider

    def clear_runtime_session_secrets(self) -> None:
        with self._provider_lock:
            self.runtime_settings_service.clear_session_secrets()
            self.model_provider = self._build_model_provider(
                self.runtime_settings_service.effective_settings()
            )
            self.plan_service.model_provider = self.model_provider
            self.pedagogy_orchestrator.model_provider = self.model_provider
            self.tavern_service.model_provider = self.model_provider

    def _build_model_provider(self, settings: Settings):
        if settings.plan_provider in {"openai", "litellm"}:
            if not settings.has_any_runtime_api_key():
                logger.warning(
                    "bootstrap.model_provider litellm requested but all OPENAI runtime API keys are missing; falling back to mock"
                )
                return MockModelProvider()
            if not settings.has_plan_api_key():
                logger.warning(
                    "bootstrap.model_provider litellm enabled without plan API key; learning plan generation will stay unavailable until OPENAI_PLAN_API_KEY or OPENAI_API_KEY is configured"
                )
            if not settings.has_setting_api_key():
                logger.warning(
                    "bootstrap.model_provider litellm enabled without setting API key; persona and scene setting features will stay unavailable until OPENAI_SETTING_API_KEY or OPENAI_API_KEY is configured"
                )
            if not settings.has_chat_api_key():
                logger.warning(
                    "bootstrap.model_provider litellm enabled without chat API key; study chat features will stay unavailable until OPENAI_CHAT_API_KEY or OPENAI_API_KEY is configured"
                )
            logger.info(
                "bootstrap.model_provider provider=litellm plan_model=%s base_url=%s",
                settings.openai_plan_model,
                settings.openai_plan_base_url,
            )
            return OpenAIModelProvider(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                plan_api_key=settings.openai_plan_api_key,
                plan_base_url=settings.openai_plan_base_url,
                plan_model=settings.openai_plan_model,
                setting_api_key=settings.openai_setting_api_key,
                setting_base_url=settings.openai_setting_base_url,
                setting_model=settings.openai_setting_model,
                setting_web_search_enabled=settings.openai_setting_web_search_enabled,
                chat_api_key=settings.openai_chat_api_key,
                chat_base_url=settings.openai_chat_base_url,
                chat_model=settings.openai_chat_model,
                chat_temperature=settings.openai_chat_temperature,
                setting_temperature=settings.openai_setting_temperature,
                setting_max_tokens=settings.openai_setting_max_tokens,
                chat_max_tokens=settings.openai_chat_max_tokens,
                chat_history_messages=settings.openai_chat_history_messages,
                chat_tool_max_rounds=settings.openai_chat_tool_max_rounds,
                chat_multimodal_enabled=settings.openai_chat_model_multimodal,
                embedding_model=settings.openai_embedding_model,
                timeout_seconds=settings.openai_timeout_seconds,
                multimodal_enabled=settings.openai_plan_model_multimodal,
                fallback_plan_model=settings.openai_plan_fallback_model,
                fallback_disable_tools=settings.openai_plan_fallback_disable_tools,
                plan_disabled_tools_provider=(
                    lambda: self.model_tool_config_service.disabled_tools_for_stage(PLAN_STAGE)
                ),
                chat_disabled_tools_provider=(
                    lambda: self.model_tool_config_service.disabled_tools_for_stage(CHAT_STAGE)
                ),
                token_usage_service=self.token_usage_service,
            )

        logger.info("bootstrap.model_provider provider=mock")
        return MockModelProvider()
