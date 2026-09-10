"""Disposable real backend for diagnostic browser acceptance; no user data."""
from pathlib import Path
from tempfile import TemporaryDirectory

import uvicorn

from app.app_factory import create_app
from app.core.settings import Settings
from app.core.bootstrap import Container
from app.models.study_question import StudyQuestionProposalV1
from app.services.model_provider import MockModelProvider


class DiagnosticScenarioProvider(MockModelProvider):
    """Scripted provider output only; production admission/commit/read-back run normally."""
    def generate_tavern_actor_reply(self, **kwargs):
        if kwargs.get("user_message") == "PRIVATE_TAVERN_PARTIAL_TRIGGER":
            self.partial_calls = getattr(self, "partial_calls", 0) + 1
            if self.partial_calls == 2:
                raise RuntimeError("PRIVATE_TAVERN_PARTIAL_FAILURE")
        return super().generate_tavern_actor_reply(**kwargs)

    def generate_chat(self, **kwargs):
        reply = super().generate_chat(**kwargs)
        if kwargs.get("message") == "PRIVATE_DIAGNOSTIC_QUESTION_TRIGGER":
            reply.interactive_question = StudyQuestionProposalV1(
                question_type="multiple_choice", prompt="PRIVATE_DIAGNOSTIC_QUESTION_PROMPT",
                options=[{"key": "A", "text": "Diagnostic first choice"}, {"key": "B", "text": "Diagnostic second choice"}],
                answer_key="A", explanation="PRIVATE_DIAGNOSTIC_GRADING_EXPLANATION", call_back=True,
            )
        return reply


class DiagnosticScenarioContainer(Container):
    def _build_model_provider(self, settings):
        # This module is only a disposable acceptance server, never production bootstrap.
        assert settings.plan_provider == "mock"
        return DiagnosticScenarioProvider()

if __name__ == "__main__":
    with TemporaryDirectory(prefix="diagnostic-browser-") as directory:
        root = Path(directory)
        settings = Settings(database_url=f"sqlite:///{root / 'domain.db'}",
                            storage_root=str(root / "data"), plan_provider="mock",
                            ocr_engine="disabled", allowed_origins=("http://127.0.0.1:3417",))
        uvicorn.run(create_app(settings=settings, container_factory=DiagnosticScenarioContainer), host="127.0.0.1", port=18998)
