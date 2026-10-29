"""Actual production adapter cancellation plus wire/worker/domain fences."""

from __future__ import annotations

import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, enumerate as threads
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import FastAPI, HTTPException

from app.api import tavern_routes
from app.models.api import CreatePersonaRequest
from app.models.tavern import CreateTavernRoomRequest, TavernTurnRequest
from app.persistence.tavern_repository import TavernRepository
from app.services.local_store import LocalJsonStore
from app.services.model_provider import OpenAIModelProvider
from app.services.persona import PersonaEngine
from app.services.provider_capabilities import TavernModelCapability
from app.services.provider_cancellation import ProviderRequestCanceled
from app.services.provider_sdk import ProviderSDK
from app.services.provider_transport import ProviderTransport
from app.services.provider_transport import ModelRequestError
from app.services.tavern import TavernService
from tests.support.api import isolated_client
from tests.support.compatible_chat_upstream import CompatibleChatUpstream
from tests.support.study_chat_samples import study_persona

EVIDENCE = []


def generate(provider, should_continue=None):
    return provider.generate_tavern_actor_reply(
        persona=study_persona(),
        participants=[],
        scene_profile=None,
        recent_messages=[],
        user_message="Discuss a choice",
        guidance="",
        allowed_target_ids=[],
        should_continue=should_continue,
    )


class ProviderCancellationTests(unittest.TestCase):
    def test_native_adapter_keeps_schema_fallback_semantic_repair_and_network_retry_bounded(
        self,
    ):
        for plans, formats in [
            (
                ("schema_reject", "invalid_actor", "reply"),
                ["json_schema", "json_object", "json_object"],
            ),
            (("disconnect", "reply"), ["json_schema", "json_schema"]),
        ]:
            with self.subTest(plans=plans), CompatibleChatUpstream(*plans) as peer:
                provider = OpenAIModelProvider(
                    api_key="fixture",
                    base_url=peer.url,
                    plan_model="fixture",
                    timeout_seconds=5,
                )
                self.assertEqual(
                    generate(provider, lambda: True).text,
                    "I can help examine this choice.",
                )
                self.assertEqual(
                    [
                        request["payload"]["response_format"]["type"]
                        for request in peer.requests
                    ],
                    formats,
                )
        with CompatibleChatUpstream("unauthorized") as peer:
            provider = OpenAIModelProvider(
                api_key="fixture",
                base_url=peer.url,
                plan_model="fixture",
                timeout_seconds=5,
            )
            with (
                self.assertLogs("vibe_learner.provider_transport"),
                self.assertRaisesRegex(
                    ModelRequestError, "openai_chat_request_failed:401:invalid_key"
                ),
            ):
                generate(provider, lambda: True)
            self.assertEqual(len(peer.requests), 1)

    def test_capability_routes_only_reviewed_compatible_calls_and_keeps_endpoint_snapshot(
        self,
    ):
        native, synchronous = (
            Mock(return_value={"choices": []}),
            Mock(return_value={"choices": []}),
        )
        sdk = ProviderSDK(completion=synchronous, cancellable_chat=native)
        provider = OpenAIModelProvider(
            api_key="fixture",
            base_url="https://base.invalid/v1",
            chat_base_url="https://chat.invalid/v1",
            chat_api_key="chat-fixture",
            plan_model="gpt-5-mini",
            sdk=sdk,
        )
        adapter = provider._sdk_adapter()
        capability = provider.tavern_cancellation_capability()
        self.assertTrue(capability.local_transport)
        self.assertFalse(capability.upstream_execution)
        self.assertFalse(capability.upstream_billing)
        provider.chat_base_url = "https://changed.invalid/v1"
        adapter.request_tavern_completion(
            {
                "model": "gpt-5-mini",
                "messages": [],
                "temperature": 0.4,
                "max_tokens": 32,
            },
            request_kind="chat",
            model="gpt-5-mini",
            should_continue=lambda: True,
        )
        self.assertEqual(native.call_args.kwargs["api_base"], "https://chat.invalid/v1")
        self.assertEqual(native.call_args.kwargs["api_key"], "chat-fixture")
        self.assertEqual(native.call_args.kwargs["payload"]["model"], "gpt-5-mini")
        self.assertEqual(
            native.call_args.kwargs["payload"]["max_completion_tokens"], 32
        )
        self.assertNotIn("temperature", native.call_args.kwargs["payload"])
        adapter.request_tavern_completion(
            {"model": "anthropic/test", "messages": []},
            request_kind="chat",
            model="anthropic/test",
        )
        synchronous.assert_called_once()
        self.assertFalse(
            adapter.tavern_cancellation_capability("anthropic/test").local_transport
        )
        self.assertFalse(
            TavernModelCapability().tavern_cancellation_capability().local_transport
        )

    def test_canceled_operation_never_starts_a_transport_or_retries_during_backoff(
        self,
    ):
        native = Mock()
        provider = OpenAIModelProvider(
            api_key="fixture",
            base_url="http://127.0.0.1/v1",
            plan_model="fixture",
            sdk=ProviderSDK(cancellable_chat=native),
        )
        with self.assertRaisesRegex(RuntimeError, "tavern_actor_generation_canceled"):
            generate(provider, lambda: False)
        native.assert_not_called()

        class Transient(Exception):
            status_code = 503

        alive = [True]
        invoke = Mock(side_effect=Transient("temporary"))
        with (
            self.assertLogs("vibe_learner.provider_transport"),
            self.assertRaises(ProviderRequestCanceled),
        ):
            ProviderTransport(
                timeout_seconds=30, sleep=lambda _seconds: alive.__setitem__(0, False)
            ).execute(
                request_kind="chat",
                model="fixture",
                invoke=invoke,
                should_continue=lambda: alive[0],
            )
        invoke.assert_called_once()

    def test_issued_http_request_cancels_before_headers_and_mid_body_and_releases_single_worker(
        self,
    ):
        for mode in ["hold_headers", "hold_body"]:
            with self.subTest(mode=mode), CompatibleChatUpstream(mode, "reply") as peer:
                usage = Mock()
                provider = OpenAIModelProvider(
                    api_key="fixture",
                    base_url=peer.url,
                    plan_model="fixture",
                    timeout_seconds=30,
                    token_usage_service=usage,
                )
                canceled = Event()
                with ThreadPoolExecutor(max_workers=1) as executor:
                    worker = executor.submit(
                        generate, provider, lambda: not canceled.is_set()
                    )
                    request = peer.wait_request()
                    self.assertTrue(request["holding"].wait(timeout=2))
                    started = time.perf_counter()
                    canceled.set()
                    with self.assertRaisesRegex(
                        RuntimeError, "tavern_actor_generation_canceled"
                    ):
                        worker.result(timeout=2)
                    elapsed_ms = (time.perf_counter() - started) * 1000
                    self.assertTrue(
                        request["closed"].wait(timeout=2),
                        "upstream socket remains open",
                    )
                    self.assertEqual(
                        len(peer.requests), 1, "cancellation retried a provider call"
                    )
                    usage.record.assert_not_called()
                    result = executor.submit(generate, provider).result(timeout=3)
                    self.assertEqual(result.text, "I can help examine this choice.")
                self.assertEqual(len(peer.requests), 2)
                usage.record.assert_called_once()
                EVIDENCE.append(
                    {
                        "case": mode,
                        "adapter": provider.tavern_cancellation_capability().adapter,
                        "issued_path": request["path"],
                        "local_socket_eof": request["closed"].is_set(),
                        "worker_return_ms": elapsed_ms,
                        "same_worker_pool_completed_next_request": True,
                        "requests_before_next_operation": 1,
                        "upstream_execution_stopped": None,
                        "upstream_billing_stopped": None,
                    }
                )

    def test_real_tavern_cancel_releases_transport_and_preserves_atomic_no_message_boundary(
        self,
    ):
        with (
            TemporaryDirectory() as folder,
            CompatibleChatUpstream("hold_body", "reply") as peer,
        ):
            store = LocalJsonStore(Path(folder))
            self.addCleanup(store.close)
            repository = TavernRepository(store.database)
            personas = PersonaEngine(
                store, tavern_reference_counter=repository.count_persona_references
            )
            persona = personas.create_persona(
                CreatePersonaRequest(
                    name="Cancelable Actor",
                    summary="synthetic fixture",
                    system_prompt="Speak only as yourself",
                    slots=[],
                )
            )
            provider = OpenAIModelProvider(
                api_key="fixture",
                base_url=peer.url,
                plan_model="fixture",
                timeout_seconds=30,
            )
            service = TavernService(
                repository=repository, persona_engine=personas, model_provider=provider
            )
            app = FastAPI()
            app.include_router(tavern_routes.router)
            client = isolated_client(app, SimpleNamespace(tavern_service=service))
            self.addCleanup(client.close)
            room = service.create_room(
                CreateTavernRoomRequest(
                    title="Cancellation fixture",
                    persona_ids=[persona.id],
                    idempotency_key="cancel-room",
                )
            ).room
            payload = TavernTurnRequest.model_validate(
                dict(
                    input={"kind": "user_message", "content": "Hold this actor"},
                    mode="direct",
                    target_persona_ids=[persona.id],
                    expected_room_revision=0,
                    idempotency_key="cancel-original",
                )
            )
            with ThreadPoolExecutor(max_workers=1) as executor:
                worker = executor.submit(
                    service.run_turn, room_id=room.id, payload=payload
                )
                request = peer.wait_request()
                self.assertTrue(request["holding"].wait(timeout=2))
                run = repository.get_run_by_idempotency_key(
                    room_id=room.id, idempotency_key="cancel-original"
                )
                started = time.perf_counter()
                response = client.post(f"/tavern/rooms/{room.id}/runs/{run.id}/cancel")
                self.assertEqual(response.status_code, 200, response.text)
                with self.assertRaises(HTTPException) as canceled:
                    worker.result(timeout=3)
                elapsed_ms = (time.perf_counter() - started) * 1000
                self.assertEqual(canceled.exception.status_code, 409)
                self.assertTrue(request["closed"].wait(timeout=2))
                terminal = repository.get_run(run.id)
                self.assertEqual(terminal.status.value, "canceled")
                self.assertIsNotNone(terminal.speaker_steps[0].harness_trace)
                saved_trace = terminal.speaker_steps[0].harness_trace
                repository.record_terminal_step_trace(
                    run_id=run.id,
                    step_index=0,
                    harness_trace=saved_trace.model_copy(
                        update={"error_code": "stale_claim_evidence"}
                    ),
                    claim_count=terminal.speaker_steps[0].claim_count + 1,
                )
                self.assertEqual(
                    repository.get_run(run.id).speaker_steps[0].harness_trace,
                    saved_trace,
                )
                self.assertEqual(
                    terminal.speaker_steps[
                        0
                    ].harness_trace.commit_evidence.status.value,
                    "not_committed",
                )
                self.assertEqual(repository.list_run_messages(run.id), [])
                self.assertEqual(len(peer.requests), 1)
                self.assertFalse(
                    any(
                        thread.name == f"tavern-lease-{run.id[-8:]}-0"
                        for thread in threads()
                    )
                )
                duplicate = client.post(f"/tavern/rooms/{room.id}/runs/{run.id}/cancel")
                self.assertEqual(duplicate.status_code, 200)
                self.assertEqual(
                    client.post(f"/tavern/rooms/{room.id}/runs/{run.id}/resume").json()[
                        "run"
                    ]["status"],
                    "canceled",
                )
                current = repository.require_room(room.id).room
                next_payload = payload.model_copy(
                    update={
                        "idempotency_key": "cancel-next",
                        "expected_room_revision": current.revision,
                    }
                )
                result = executor.submit(
                    service.run_turn, room_id=room.id, payload=next_payload
                ).result(timeout=3)
                self.assertEqual(result.run.status.value, "completed")
            self.assertEqual(len(peer.requests), 2)
            EVIDENCE.append(
                {
                    "case": "tavern_cancel",
                    "run_status": terminal.status.value,
                    "cancel_http_status": response.status_code,
                    "original_worker_http_status": canceled.exception.status_code,
                    "local_socket_eof": request["closed"].is_set(),
                    "worker_return_ms": elapsed_ms,
                    "canceled_actor_messages": 0,
                    "lease_thread_stopped": True,
                    "resume_replayed_provider": False,
                    "same_worker_pool_completed_next_operation": True,
                    "upstream_execution_stopped": None,
                    "upstream_billing_stopped": None,
                }
            )
