"""Disposable mock-provider backend for independent Plan revision browser checks."""
from pathlib import Path
from tempfile import TemporaryDirectory
import uvicorn
from app.app_factory import create_app
from app.core.settings import Settings
from app.core.bootstrap import Container
from app.services.model_provider import MockModelProvider
from app.models.domain import ScheduleChapterRecord, ScheduleChapterContentSliceRecord
from app.persistence.learning_plan_repository import LearningPlanRepository
from tests.test_plan_revision import fixture_plan

class RevisionBrowserContainer(Container):
    def _build_model_provider(self, settings):
        assert settings.plan_provider == "mock"
        return MockModelProvider()

    def _initialize(self):
        super()._initialize()
        plan = fixture_plan()
        plan.schedule = plan.schedule[:1]
        plan.persona_id = self.persona_engine.list_personas()[0].id
        unit = plan.study_units[0]
        unit.document_id = "goal-only:independent"
        unit.id = "goal-only:independent:study-unit:1"
        for item in plan.schedule:
            item.unit_id = unit.id
            item.activity_type = "learn"
            item.schedule_chapters = [ScheduleChapterRecord(id=f"{unit.id}:schedule-chapter:1", title=unit.title,
                anchor_page_start=1, anchor_page_end=1, content_slices=[ScheduleChapterContentSliceRecord(page_start=1, page_end=1)])]
        LearningPlanRepository(self.database).import_legacy([plan])

if __name__ == "__main__":
    with TemporaryDirectory(prefix="plan-revision-browser-") as directory:
        root = Path(directory)
        settings = Settings(database_url=f"sqlite:///{root / 'domain.db'}", storage_root=str(root / "data"),
            plan_provider="mock", ocr_engine="disabled", allowed_origins=("http://127.0.0.1:3417",))
        uvicorn.run(create_app(settings=settings, container_factory=RevisionBrowserContainer), host="127.0.0.1", port=18997)
