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
from app.services.persona import PersonaEngine
from app.services.study_arrangement import StudyArrangementService
from app.services.study_sessions import StudySessionService

logger = get_logger("gal_learner.bootstrap")


class Container:
    def __init__(self) -> None:
        data_root = Path(__file__).resolve().parents[2] / "data"
        settings = Settings.from_env()
        self.store = LocalJsonStore(data_root)
        self.document_parser = DocumentParser()
        self.model_provider = self._build_model_provider(settings)
        self.performance_mapper = PerformanceMapper()
        self.persona_engine = PersonaEngine()
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

    def _build_model_provider(self, settings: Settings):
        if settings.plan_provider == "openai":
            if not settings.openai_api_key:
                logger.warning("bootstrap.model_provider openai requested but OPENAI_API_KEY is missing; falling back to mock")
                return MockModelProvider()
            logger.info(
                "bootstrap.model_provider provider=openai plan_model=%s base_url=%s",
                settings.openai_plan_model,
                settings.openai_base_url,
            )
            return OpenAIModelProvider(
                api_key=settings.openai_api_key,
                base_url=settings.openai_base_url,
                plan_model=settings.openai_plan_model,
                timeout_seconds=settings.openai_timeout_seconds,
                multimodal_enabled=settings.openai_plan_model_multimodal,
            )

        logger.info("bootstrap.model_provider provider=mock")
        return MockModelProvider()


container = Container()
