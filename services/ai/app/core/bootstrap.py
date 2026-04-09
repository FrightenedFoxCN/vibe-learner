from app.services.model_provider import MockModelProvider
from app.services.pedagogy import PedagogyOrchestrator
from app.services.performance import PerformanceMapper
from app.services.persona import PersonaEngine


class Container:
    def __init__(self) -> None:
        self.model_provider = MockModelProvider()
        self.performance_mapper = PerformanceMapper()
        self.persona_engine = PersonaEngine()
        self.pedagogy_orchestrator = PedagogyOrchestrator(
            model_provider=self.model_provider,
            performance_mapper=self.performance_mapper,
        )


container = Container()
