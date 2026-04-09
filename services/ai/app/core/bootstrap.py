from pathlib import Path

from app.services.model_provider import MockModelProvider
from app.services.documents import DocumentService
from app.services.local_store import LocalJsonStore
from app.services.pedagogy import PedagogyOrchestrator
from app.services.performance import PerformanceMapper
from app.services.plans import LearningPlanService
from app.services.persona import PersonaEngine
from app.services.study_sessions import StudySessionService


class Container:
    def __init__(self) -> None:
        data_root = Path(__file__).resolve().parents[2] / "data"
        self.store = LocalJsonStore(data_root)
        self.model_provider = MockModelProvider()
        self.performance_mapper = PerformanceMapper()
        self.persona_engine = PersonaEngine()
        self.document_service = DocumentService(self.store)
        self.plan_service = LearningPlanService(self.store)
        self.study_session_service = StudySessionService(self.store)
        self.pedagogy_orchestrator = PedagogyOrchestrator(
            model_provider=self.model_provider,
            performance_mapper=self.performance_mapper,
        )


container = Container()
