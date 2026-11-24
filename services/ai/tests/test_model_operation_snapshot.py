from types import SimpleNamespace
from unittest.mock import patch

from fastapi import FastAPI, HTTPException

from app.api import tavern_routes
from app.api.routers.persona_scene import assist_persona_setting, assist_persona_slot
from app.core.bootstrap import Container
from app.models.api import (
    CreatePersonaRequest,
    PersonaSettingAssistRequest,
    PersonaSlotAssistRequest,
)
from app.models.domain import LearningGoalInput, PersonaSlot
from app.models.tavern import (
    CreateTavernRoomRequest,
    RetryTavernRunRequest,
    TavernTurnRequest,
)
from app.services.model_provider import MockModelProvider, OpenAIModelProvider
from app.services.model_tool_config import CHAT_STAGE, PLAN_STAGE
from tests.support.api import ContainerTestCase, isolated_client
from tests.support.tavern_provider import SequencedTavernProvider


class ModelOperationSnapshotTests(ContainerTestCase):
    def _tavern(self):
        personas = [
            self.container.persona_engine.create_persona(
                CreatePersonaRequest(
                    name=name,
                    summary="倾听并独立回应。",
                    system_prompt="只说自己的话。",
                )
            )
            for name in ("阿澜", "柏舟", "长风")
        ]
        ids = [persona.id for persona in personas]
        room = self.container.tavern_service.create_room(
            CreateTavernRoomRequest(
                title="群星酒馆", persona_ids=ids, idempotency_key="model-capture-room"
            )
        )
        request = TavernTurnRequest.model_validate(
            {
                "input": {"kind": "user_message", "content": "请大家依次谈谈。"},
                "mode": "facilitated",
                "target_persona_ids": ids,
                "idempotency_key": "model-capture-turn",
                "expected_room_revision": 0,
            }
        )
        return room.room.id, request

    def _abandon_before_execution(self, room_id, request):
        service = self.container.tavern_service
        with patch.object(
            service, "_execute_run", side_effect=SystemExit("test crash")
        ):
            with self.assertRaises(SystemExit):
                service.run_turn(room_id=room_id, payload=request)
        run = service.repository.get_run_by_idempotency_key(
            room_id=room_id, idempotency_key=request.idempotency_key
        )
        assert run is not None
        self.assertTrue(run.execution_config_binding)
        self.assertNotIn("execution_config_binding", run.model_dump(mode="json"))
        return run

    def test_tavern_facilitated_run_pins_provider_through_hot_switch(self):
        room_id, request = self._tavern()
        old_capture = self.container.capture_model_provider()
        served = SequencedTavernProvider()
        seen = []

        def generate(provider, **kwargs):
            seen.append(provider)
            if len(seen) == 1:
                self.container.update_runtime_settings(
                    {"openai_chat_model": "later-model"}
                )
                self.assertIsNot(self.container.capture_model_provider(), old_capture)
            return served.generate_tavern_actor_reply(**kwargs)

        with patch.object(
            MockModelProvider,
            "generate_tavern_actor_reply",
            autospec=True,
            side_effect=generate,
        ):
            result = self.container.tavern_service.run_turn(
                room_id=room_id, payload=request
            )
        self.assertEqual(result.run.status.value, "completed")
        self.assertEqual(seen, [old_capture] * 3)
        self.assertEqual(len(result.generated_messages), 3)

    def test_tavern_resume_and_duplicate_reject_new_database_generation(self):
        room_id, request = self._tavern()
        run = self._abandon_before_execution(room_id, request)
        other = Container(self.container.base_settings)
        self.addCleanup(other.close)
        other.update_runtime_settings({"openai_chat_model": "different-worker-update"})
        app = FastAPI()
        app.include_router(tavern_routes.router)
        with isolated_client(app, self.container) as client:
            with patch.object(
                MockModelProvider, "generate_tavern_actor_reply"
            ) as generate:
                response = client.post(f"/tavern/rooms/{room_id}/runs/{run.id}/resume")
                self.assertEqual(response.status_code, 409, response.text)
                self.assertEqual(
                    response.json()["detail"]["code"],
                    "tavern_run_model_configuration_unavailable",
                )
                self.assertEqual(response.json()["detail"]["run_id"], run.id)
                with self.assertRaisesRegex(
                    HTTPException, "tavern_run_model_configuration_unavailable"
                ):
                    self.container.tavern_service.run_turn(
                        room_id=room_id, payload=request
                    )
                generate.assert_not_called()
            chains = self.container.tavern_service.list_run_recovery(room_id)
            self.assertEqual(chains[0].recovery_action.value, "none")
            canceled = client.post(f"/tavern/rooms/{room_id}/runs/{run.id}/cancel")
        self.assertEqual(canceled.status_code, 200, canceled.text)
        self.assertEqual(canceled.json()["run"]["status"], "canceled")

    def test_tavern_unchanged_web_generation_can_resume_on_new_container(self):
        room_id, request = self._tavern()
        run = self._abandon_before_execution(room_id, request)
        other = Container(self.container.base_settings)
        self.addCleanup(other.close)
        other.update_model_tool_config(
            [
                {
                    "stage_name": CHAT_STAGE,
                    "tool_name": "read_system_time",
                    "enabled": False,
                },
            ]
        )
        with patch.object(
            other.capture_model_provider(),
            "generate_tavern_actor_reply",
            side_effect=SequencedTavernProvider().generate_tavern_actor_reply,
        ):
            result = other.tavern_service.resume_run(room_id=room_id, run_id=run.id)
        self.assertEqual(result.run.status.value, "completed")
        self.assertEqual(result.run.id, run.id)

    def test_tavern_changed_session_secret_cannot_resume(self):
        room_id, request = self._tavern()
        run = self._abandon_before_execution(room_id, request)
        self.container.apply_runtime_session_secrets(
            {"openai_chat_api_key": "synthetic-test-only"}
        )
        with self.assertRaisesRegex(
            HTTPException, "tavern_run_model_configuration_unavailable"
        ):
            self.container.tavern_service.resume_run(room_id=room_id, run_id=run.id)

    def test_tavern_retry_is_new_run_using_fresh_configuration(self):
        room_id, request = self._tavern()
        service = self.container.tavern_service
        old_provider = self.container.capture_model_provider()
        first = SequencedTavernProvider(fail_calls={2})
        with patch.object(
            old_provider,
            "generate_tavern_actor_reply",
            side_effect=first.generate_tavern_actor_reply,
        ):
            with self.assertRaisesRegex(HTTPException, "tavern_run_failed"):
                service.run_turn(room_id=room_id, payload=request)
        self.container.update_runtime_settings({"openai_chat_model": "retry-new-model"})
        # A terminal receipt remains readable even under a new configuration.
        partial = service.run_turn(room_id=room_id, payload=request)
        self.assertEqual(partial.run.status.value, "partial")
        new_provider = self.container.capture_model_provider()
        self.assertIsNot(old_provider, new_provider)
        retry = SequencedTavernProvider()
        with patch.object(
            new_provider,
            "generate_tavern_actor_reply",
            side_effect=retry.generate_tavern_actor_reply,
        ):
            result = service.retry_run(
                room_id=room_id,
                source_run_id=partial.run.id,
                payload=RetryTavernRunRequest(
                    idempotency_key="model-capture-retry",
                    expected_room_revision=partial.room_state.revision,
                ),
            )
        self.assertEqual(result.run.status.value, "completed")
        self.assertEqual(result.run.parent_run_id, partial.run.id)
        self.assertNotEqual(
            result.run.execution_config_binding, partial.run.execution_config_binding
        )
        self.assertEqual(len(retry.calls), 2)

    def test_plan_captures_provider_before_operation_admission_callback(self):
        persona = self.container.persona_engine.create_persona(
            CreatePersonaRequest(name="Mira", summary="Tutor", system_prompt="Teach.")
        )
        old_provider = self.container.capture_model_provider()
        generate = old_provider.generate_learning_plan

        def update(_operation_id):
            self.container.update_runtime_settings(
                {"openai_plan_model": "future-plan-model"}
            )

        with patch.object(
            old_provider, "generate_learning_plan", side_effect=generate
        ) as old_call:
            self.container.plan_service.create_plan(
                goal=LearningGoalInput(
                    persona_id=persona.id, objective="Learn basic probability."
                ),
                client_request_id="plan-model-capture",
                expected_document_updated_at="",
                persona=persona,
                operation_admitted_callback=update,
            )
        old_call.assert_called_once()
        self.assertIsNot(old_provider, self.container.capture_model_provider())

    def test_study_chat_configuration_and_both_tool_policies_are_frozen(self):
        self.container.update_runtime_settings(
            {
                "plan_provider": "litellm",
                "openai_api_key": "synthetic-test-only",
                "openai_chat_model": "first-chat-model",
            }
        )
        old_action = self.container.study_chat_application().dependencies
        old_provider = old_action.model_provider
        assert isinstance(old_provider, OpenAIModelProvider)
        self.assertIs(self.container.capture_model_provider(), old_provider)
        other = Container(self.container.base_settings)
        self.addCleanup(other.close)
        other.update_model_tool_config(
            [
                {
                    "stage_name": CHAT_STAGE,
                    "tool_name": "read_system_time",
                    "enabled": False,
                },
                {
                    "stage_name": PLAN_STAGE,
                    "tool_name": "read_page_range_content",
                    "enabled": False,
                },
            ]
        )
        other.update_runtime_settings({"openai_chat_model": "second-chat-model"})
        fresh_action = self.container.study_chat_application().dependencies
        fresh_provider = fresh_action.model_provider
        assert isinstance(fresh_provider, OpenAIModelProvider)
        self.assertIsNot(old_provider, fresh_provider)
        self.assertIs(old_action.pedagogy_orchestrator.model_provider, old_provider)
        self.assertIs(fresh_action.pedagogy_orchestrator.model_provider, fresh_provider)
        self.assertEqual(
            old_action.runtime_settings.openai_chat_model, "first-chat-model"
        )
        self.assertEqual(
            fresh_action.runtime_settings.openai_chat_model, "second-chat-model"
        )
        self.assertEqual(old_provider.chat_disabled_tools_provider(), set())
        self.assertEqual(old_provider.plan_disabled_tools_provider(), set())
        self.assertEqual(
            fresh_provider.chat_disabled_tools_provider(), {"read_system_time"}
        )
        self.assertEqual(
            fresh_provider.plan_disabled_tools_provider(), {"read_page_range_content"}
        )

    def test_persona_assist_uses_calling_provider_for_attribution(self):
        slot = PersonaSlot(kind="teaching_method", label="Method", content="Observe.")
        runtime = self.container.harness_proposal_runtime
        captured = []
        original_run = runtime.run_persona

        def run_persona(**kwargs):
            proposal, trace = original_run(**kwargs)
            captured.append(proposal.used_model)
            return proposal, trace

        for operation in ("setting", "slot"):
            with self.subTest(operation=operation):

                def swap_provider(**kwargs):
                    self.container.update_runtime_settings(
                        {"openai_setting_model": f"new-{operation}"}
                    )
                    return (
                        {"slots": [slot], "system_prompt_suggestion": "Observe."}
                        if operation == "setting"
                        else {"slot": slot}
                    )

                self.container.model_provider = SimpleNamespace(
                    setting_model=f"old-{operation}",
                    assist_persona_setting=swap_provider,
                    assist_persona_slot=swap_provider,
                )
                with patch.object(runtime, "run_persona", side_effect=run_persona):
                    if operation == "setting":
                        assist_persona_setting(
                            PersonaSettingAssistRequest(
                                name="Mira", summary="Tutor", slots=[slot]
                            ),
                            container=self.container,
                        )
                    else:
                        assist_persona_slot(
                            PersonaSlotAssistRequest(
                                name="Mira", summary="Tutor", slot=slot
                            ),
                            container=self.container,
                        )
        self.assertEqual(captured, ["old-setting", "old-slot"])
