from pathlib import Path

from app.services.document_parser import DocumentParser
from app.core.logging import get_logger
from app.core.settings import Settings
from app.services.model_provider import MockModelProvider, OpenAIModelProvider
from app.services.documents import DocumentService
from app.services.local_store import LocalJsonStore
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
from app.services.token_usage import TokenUsageService

logger = get_logger("vibe_learner.bootstrap")


class Container:
    def __init__(self) -> None:
        data_root = Path(__file__).resolve().parents[2] / "data"
        self.base_settings = Settings.from_env()
        self.store = LocalJsonStore(data_root)
        self.document_parser = DocumentParser()
        self.model_tool_config_service = ModelToolConfigService(self.store)
        self.runtime_settings_service = RuntimeSettingsService(self.store, self.base_settings)
        self.token_usage_service = TokenUsageService(data_root)
        self.scene_setup_service = SceneSetupService(self.store)
        self.scene_library_service = SceneLibraryService(self.store)
        self.reusable_scene_node_library_service = ReusableSceneNodeLibraryService(self.store)
        self.persona_card_library_service = PersonaCardLibraryService(self.store)
        self.session_scene_service = SessionSceneService(self.store)
        self.model_provider = self._build_model_provider(self.runtime_settings_service.effective_settings())
        self.performance_mapper = PerformanceMapper()
        self.persona_engine = PersonaEngine(self.store)
        self.study_arrangement_service = StudyArrangementService()
        self.document_service = DocumentService(
            self.store,
            self.document_parser,
            self.study_arrangement_service,
        )
        self.plan_service = LearningPlanService(
            self.store,
            self.study_arrangement_service,
            self.model_provider,
        )
        self.study_session_service = StudySessionService(self.store)
        self.pedagogy_orchestrator = PedagogyOrchestrator(
            model_provider=self.model_provider,
            performance_mapper=self.performance_mapper,
        )

    def update_runtime_settings(self, updates: dict[str, object]) -> None:
        self.runtime_settings_service.update(updates)
        self.model_provider = self._build_model_provider(
            self.runtime_settings_service.effective_settings()
        )
        self.plan_service.model_provider = self.model_provider
        self.pedagogy_orchestrator.model_provider = self.model_provider

    def _build_model_provider(self, settings: Settings):
        if settings.plan_provider == "openai":
            if not (settings.openai_plan_api_key or settings.openai_api_key):
                logger.warning(
                    "bootstrap.model_provider openai requested but OPENAI_PLAN_API_KEY/OPENAI_API_KEY missing; falling back to mock"
                )
                return MockModelProvider()
            logger.info(
                "bootstrap.model_provider provider=openai plan_model=%s base_url=%s",
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
                chat_tools_enabled=settings.openai_chat_tools_enabled,
                chat_memory_tool_enabled=settings.openai_chat_memory_tool_enabled,
                chat_multimodal_enabled=settings.openai_chat_model_multimodal,
                embedding_model=settings.openai_embedding_model,
                timeout_seconds=settings.openai_timeout_seconds,
                multimodal_enabled=settings.openai_plan_model_multimodal,
                plan_tools_enabled=settings.openai_plan_tools_enabled,
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


container = Container()
