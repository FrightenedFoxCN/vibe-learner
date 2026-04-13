from pathlib import Path
from tempfile import TemporaryDirectory
import json
import threading
import unittest
from unittest.mock import patch

import fitz
from fastapi import HTTPException
from app.api.routes import (
    _map_chat_generation_error,
    _map_plan_generation_error,
    _map_setting_generation_error,
    get_document_planning_trace,
)
from app.models.api import CreatePersonaCardRequest, CreatePersonaRequest, DocumentResponse, PersonaCardGenerateRequest
from app.models.domain import (
    ChatToolCallTraceRecord,
    Citation,
    DocumentDebugRecord,
    LearningPlanRecord,
    LearningGoalInput,
    PlanGenerationTraceRecord,
    PlanningQuestionRecord,
    SceneLayerStateRecord,
    SceneObjectStateRecord,
    SceneProfileRecord,
    StudyUnitRecord,
    StudyChatResult,
    StudySessionRecord,
)
from app.services.documents import DocumentService
from app.services.document_parser import DocumentParser, ParsedPage
from app.services.learning_plan_chat_runtime import LearningPlanChatToolRuntime
from app.services.local_store import LocalJsonStore
from app.services.model_provider import (
    MockModelProvider,
    OpenAIModelProvider,
    PlanModelReply,
    PlanScheduleItem,
    CHAT_JSON_SCHEMA,
    _parse_chat_model_reply,
)
from app.services.runtime_settings import RuntimeSettingsService
from app.services.pedagogy import PedagogyOrchestrator
from app.services.performance import PerformanceMapper
from app.services.plan_prompt import build_learning_plan_messages, read_page_range_content
from app.services.plan_prompt import load_learning_plan_prompt_template
from app.services.plans import LearningPlanService
from app.services.persona import PersonaEngine
from app.services.persona_cards import PersonaCardLibraryService
from app.services.persona_runtime import render_persona_runtime_instruction
from app.services.plan_tool_runtime import build_plan_tool_runtime, get_learning_plan_tool_specs
from app.services.prompt_loader import load_prompt_template
from app.services.study_arrangement import StudyArrangementService
from app.services.study_session_prompt import build_study_session_system_prompt
from app.services.stream_reports import (
    DOCUMENT_PROCESS_STREAM_CATEGORY,
    LEARNING_PLAN_STREAM_CATEGORY,
    StreamReportRecorder,
)
from app.services.session_scene import SessionSceneService
from app.services.study_sessions import StudySessionService


class FakeLiteLLMResult:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def model_dump(self, mode: str = "json") -> dict[str, object]:
        return self.payload


class PersonaPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = TemporaryDirectory()
        store = LocalJsonStore(Path(self.temp_dir.name))
        self.store = store
        arrangement_service = StudyArrangementService()
        model_provider = MockModelProvider()
        self.persona_engine = PersonaEngine(store)
        self.persona_card_library = PersonaCardLibraryService(store)
        self.document_service = DocumentService(store, DocumentParser(), arrangement_service)
        self.plan_service = LearningPlanService(store, arrangement_service, model_provider)
        self.study_session_service = StudySessionService(store)
        self.session_scene_service = SessionSceneService(store)
        self.orchestrator = PedagogyOrchestrator(
            model_provider=model_provider,
            performance_mapper=PerformanceMapper(),
        )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_builtin_personas_are_available(self) -> None:
        personas = self.persona_engine.list_personas()
        self.assertGreaterEqual(len(personas), 2)
        self.assertEqual(personas[0].source, "builtin")

    def test_user_persona_creation_preserves_contract_shape(self) -> None:
        from app.models.domain import PersonaSlot
        persona = self.persona_engine.create_persona(
            CreatePersonaRequest(
                name="Sora Guide",
                summary="A sharp but kind mentor.",
                relationship="mentor",
                learner_address="friend",
                system_prompt="Stay grounded in the document.",
                slots=[
                    PersonaSlot(kind="teaching_method", label="教学方法", content="socratic, precise"),
                    PersonaSlot(kind="narrative_mode", label="叙事模式", content="light_story"),
                    PersonaSlot(kind="encouragement_style", label="鼓励策略", content="celebrate effort"),
                    PersonaSlot(kind="correction_style", label="纠错策略", content="direct but supportive"),
                ],
            )
        )
        self.assertEqual(persona.id, "sora-guide")
        self.assertEqual(persona.source, "user")
        self.assertEqual(persona.relationship, "mentor")
        self.assertEqual(persona.learner_address, "friend")
        self.assertIn("playful", persona.available_emotions)

    def test_user_persona_creation_persists_to_local_store(self) -> None:
        self.persona_engine.create_persona(
            CreatePersonaRequest(
                name="Persisted Mentor",
                summary="Stored on disk.",
                system_prompt="Stay grounded.",
                slots=[],
            )
        )
        reloaded = PersonaEngine(self.store)
        persona = reloaded.require_persona("persisted-mentor")
        self.assertEqual(persona.summary, "Stored on disk.")

    def test_user_persona_delete_removes_from_local_store(self) -> None:
        created = self.persona_engine.create_persona(
            CreatePersonaRequest(
                name="Disposable Mentor",
                summary="Will be deleted.",
                system_prompt="Keep it concise.",
                slots=[],
            )
        )

        self.persona_engine.delete_persona(created.id)

        reloaded = PersonaEngine(self.store)
        with self.assertRaises(HTTPException) as ctx:
            reloaded.require_persona(created.id)
        self.assertEqual(ctx.exception.status_code, 404)

    def test_builtin_persona_delete_is_rejected(self) -> None:
        with self.assertRaises(HTTPException) as ctx:
            self.persona_engine.delete_persona("mentor-aurora")
        self.assertEqual(ctx.exception.status_code, 403)
        self.assertEqual(ctx.exception.detail, "persona_readonly_builtin")

    def test_user_persona_delete_is_blocked_when_records_reference_it(self) -> None:
        created = self.persona_engine.create_persona(
            CreatePersonaRequest(
                name="Referenced Mentor",
                summary="Referenced by plan and session.",
                system_prompt="Stay grounded.",
                slots=[],
            )
        )
        self.store.save_list(
            "plans",
            [
                LearningPlanRecord(
                    id="plan-1",
                    document_id="doc-1",
                    persona_id=created.id,
                    course_title="课程标题",
                    objective="完成教材学习",
                    overview="计划概览",
                    study_chapters=["第一章"],
                    today_tasks=["复习核心概念"],
                    study_units=[],
                    schedule=[],
                    created_at="2026-04-12T00:00:00+00:00",
                )
            ],
        )
        self.study_session_service.create_session(
            document_id="doc-1",
            persona_id=created.id,
            section_id="section-1",
        )

        with self.assertRaises(HTTPException) as ctx:
            self.persona_engine.delete_persona(created.id)

        self.assertEqual(ctx.exception.status_code, 409)
        self.assertIn("persona_in_use", ctx.exception.detail)
        self.assertIn("plans=1", ctx.exception.detail)
        self.assertIn("sessions=1", ctx.exception.detail)

    def test_persona_card_library_crud_roundtrip(self) -> None:
        created = self.persona_card_library.create_card(
            CreatePersonaCardRequest(
                title="冷静拆解",
                kind="thinking_style",
                label="思维风格",
                content="先澄清前提，再给出推理链。",
                tags=["理性", "结构化"],
                source="manual",
                source_note="人工整理",
            )
        )
        listed = self.persona_card_library.list_cards()
        self.assertEqual(len(listed), 1)
        self.assertEqual(listed[0].id, created.id)
        self.assertEqual(listed[0].tags, ["理性", "结构化"])
        self.persona_card_library.delete_card(created.id)
        self.assertEqual(self.persona_card_library.list_cards(), [])

    def test_mock_provider_keyword_card_generation_requires_openai(self) -> None:
        with self.assertRaises(RuntimeError) as ctx:
            MockModelProvider().generate_persona_cards_from_keywords(
                keywords="福尔摩斯式导师",
                count=6,
            )
        self.assertEqual(str(ctx.exception), "setting_keyword_generation_requires_openai")

    def test_openai_provider_keyword_card_generation_uses_responses_web_search(self) -> None:
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            setting_model="gpt-setting-test",
            timeout_seconds=3,
        )

        with patch(
            "app.services.model_provider.litellm_responses",
            return_value=FakeLiteLLMResult(
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "summary": "冷静推理型导师，擅长把复杂问题拆成线索链。",
                                            "relationship": "并肩破案的导师",
                                            "learner_address": "搭档",
                                            "cards": [
                                                {
                                                    "title": "冷静推理式教学",
                                                    "kind": "thinking_style",
                                                    "label": "思维风格",
                                                    "content": "先整理线索，再逐步排除错误路径。",
                                                    "tags": ["推理", "克制"],
                                                    "source_note": "参考了公开侦探型角色的推理节奏。",
                                                }
                                            ]
                                        },
                                        ensure_ascii=False,
                                    ),
                                }
                            ],
                        }
                    ]
                }
            ),
        ) as mocked_responses:
            result = provider.generate_persona_cards_from_keywords(
                keywords="侦探导师, 冷静推理",
                count=5,
            )

        payload = mocked_responses.call_args.kwargs
        self.assertEqual(payload["model"], "openai/gpt-setting-test")
        self.assertEqual(payload["api_base"], "https://api.openai.test/v1")
        self.assertEqual(payload["api_key"], "test-key")
        self.assertEqual(payload["tools"][0]["type"], "web_search")
        self.assertIn("侦探导师, 冷静推理", payload["input"])
        self.assertTrue(result["used_web_search"])
        self.assertEqual(result["relationship"], "并肩破案的导师")
        self.assertEqual(result["learner_address"], "搭档")
        self.assertEqual(result["cards"][0]["kind"], "thinking_style")

    def test_openai_provider_keyword_card_generation_falls_back_to_model_only_when_web_disabled(self) -> None:
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            setting_model="gpt-setting-test",
            setting_web_search_enabled=False,
            timeout_seconds=3,
        )

        with patch(
            "app.services.model_provider.litellm_completion",
            return_value=FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "summary": "由关键词直接生成的导学人格。",
                                        "relationship": "耐心导师",
                                        "learner_address": "同学",
                                        "cards": [
                                            {
                                                "title": "结构化导学",
                                                "kind": "teaching_method",
                                                "label": "教学方法",
                                                "content": "先搭框架，再逐步推进例题和反例。",
                                            }
                                        ],
                                    },
                                    ensure_ascii=False,
                                )
                            }
                        }
                    ]
                }
            ),
        ) as mocked_completion:
            result = provider.generate_persona_cards_from_keywords(
                keywords="学院派导师",
                count=4,
            )

        payload = mocked_completion.call_args.kwargs
        self.assertNotIn("tools", payload)
        self.assertEqual(payload["api_base"], "https://api.openai.test/v1")
        self.assertEqual(payload["api_key"], "test-key")
        self.assertFalse(result["used_web_search"])
        self.assertEqual(result["summary"], "由关键词直接生成的导学人格。")

    def test_openai_provider_keyword_card_generation_falls_back_when_web_search_request_is_rejected(self) -> None:
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            setting_model="gpt-setting-test",
            timeout_seconds=3,
        )

        with (
            patch.object(
                provider,
                "_request_openai_response",
                side_effect=RuntimeError("openai_setting_request_failed:400:BadRequestError"),
            ),
            patch.object(
                provider,
                "_request_openai_chat_completion",
                return_value=(
                    {
                        "choices": [
                            {
                                "message": {
                                    "content": json.dumps(
                                        {
                                            "summary": "回退到纯模型生成的人格草稿。",
                                            "relationship": "分析型导师",
                                            "learner_address": "同学",
                                            "cards": [
                                                {
                                                    "title": "结构化引导",
                                                    "kind": "teaching_method",
                                                    "label": "教学方法",
                                                    "content": "先整理线索，再组织解释顺序。",
                                                }
                                            ],
                                        },
                                        ensure_ascii=False,
                                    )
                                }
                            }
                        ]
                    },
                    0,
                ),
            ) as mocked_completion,
        ):
            result = provider.generate_persona_cards_from_keywords(
                keywords="侦探导师, 冷静推理",
                count=4,
            )

        payload = mocked_completion.call_args.kwargs
        self.assertEqual(payload["model"], "gpt-setting-test")
        self.assertFalse(result["used_web_search"])
        self.assertEqual(result["relationship"], "分析型导师")

    def test_persona_card_generate_request_allows_missing_count(self) -> None:
        request = PersonaCardGenerateRequest(mode="keywords", input_text="学院派导师, 冷静推理")
        self.assertIsNone(request.count)

    def test_mock_text_card_generation_no_longer_clamps_to_minimum_count(self) -> None:
        result = MockModelProvider().generate_persona_cards_from_text(
            text="冷静分析。先给框架。",
            count=1,
        )

        self.assertEqual(len(result["cards"]), 1)
        self.assertEqual(result["cards"][0]["content"], "冷静分析")

    def test_openai_provider_keyword_card_generation_uses_soft_count_hint(self) -> None:
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            setting_model="gpt-setting-test",
            timeout_seconds=3,
        )

        with patch(
            "app.services.model_provider.litellm_responses",
            return_value=FakeLiteLLMResult(
                {
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "summary": "冷静推理型导师，擅长把复杂问题拆成线索链。",
                                            "relationship": "并肩破案的导师",
                                            "learner_address": "搭档",
                                            "cards": [
                                                {
                                                    "title": "冷静推理式教学",
                                                    "kind": "thinking_style",
                                                    "label": "思维风格",
                                                    "content": "先整理线索，再逐步排除错误路径。",
                                                }
                                            ],
                                        },
                                        ensure_ascii=False,
                                    ),
                                }
                            ],
                        }
                    ]
                }
            ),
        ) as mocked_responses:
            provider.generate_persona_cards_from_keywords(
                keywords="侦探导师, 冷静推理",
                count=None,
            )

        payload = mocked_responses.call_args.kwargs
        self.assertIn("card_count_hint: 未指定", payload["input"])
        self.assertIn("只是数量偏好", payload["instructions"])

    def test_persona_card_prompt_mentions_soft_count_and_freedom(self) -> None:
        template = load_prompt_template("openai_setting_prompt.txt")
        keywords_system = template.require("generate_keywords_system")
        keywords_user = template.require("generate_keywords_user")
        long_text_system = template.require("generate_long_text_system")

        self.assertIn("只是数量偏好", keywords_system)
        self.assertIn("不要为了凑满类别而生成低价值卡片", keywords_system)
        self.assertIn("card_count_hint", keywords_user)
        self.assertIn("可以更少，也可以更多", keywords_user)
        self.assertIn("允许同一种 kind 拆成多张细分卡片", long_text_system)

    def test_learning_plan_prompt_includes_persona_identity_fields(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        messages = build_learning_plan_messages(
            persona=persona,
            document_title="Physics",
            goal=LearningGoalInput(
                document_id="doc-1",
                persona_id=persona.id,
                objective="掌握牛顿定律",
            ),
            study_units=[
                StudyUnitRecord(
                    id="unit-1",
                    document_id="doc-1",
                    title="牛顿定律",
                    page_start=1,
                    page_end=4,
                    summary="",
                )
            ],
        )
        payload = "\n".join(message["content"] for message in messages)
        self.assertIn(persona.relationship, payload)
        self.assertIn(persona.learner_address, payload)
        self.assertIn("runtime_instruction", payload)

    def test_persona_runtime_instruction_expands_slots_and_additional_instruction(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        prompt = render_persona_runtime_instruction(persona)

        self.assertIn(persona.name, prompt)
        self.assertIn(persona.summary, prompt)
        self.assertIn(persona.system_prompt, prompt)
        self.assertTrue(any(slot.content in prompt for slot in persona.slots if slot.content))

    def test_study_session_prompt_only_adds_session_context(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        prompt = build_study_session_system_prompt(
            persona_name=persona.name,
            persona_relationship=persona.relationship,
            persona_learner_address=persona.learner_address,
            document_title="Physics",
            section_id="chapter-1",
            section_title="Chapter 1",
            theme_hint="牛顿定律",
        )

        self.assertIn("会话运行时上下文", prompt)
        self.assertIn("Chapter 1", prompt)
        self.assertNotIn(persona.system_prompt, prompt)

    def test_chat_reply_returns_character_events(self) -> None:
        persona = self.persona_engine.require_persona("mentor-lyra")
        result = self.orchestrator.generate_chat_reply(
            session_id="session-1",
            persona=persona,
            message="解释牛顿第一定律",
            section_id="chapter-1",
        )
        self.assertTrue(result.reply)
        self.assertEqual(result.citations[0].section_id, "chapter-1")
        self.assertEqual(result.character_events[0].line_segment_id, "session-1:chat:0")

    def test_session_scene_clone_and_mutation_are_isolated(self) -> None:
        source_profile = SceneProfileRecord(
            scene_name="力学教室",
            scene_id="scene-classroom",
            title="力学教室",
            summary="以课堂讲解为中心的基础场景。",
            tags=["classroom"],
            selected_path=["校园", "物理楼", "力学教室"],
            focus_object_names=["黑板"],
            scene_tree=[
                SceneLayerStateRecord(
                    id="scene-campus",
                    title="校园",
                    scope_label="world",
                    summary="学校外景",
                    atmosphere="清晨",
                    rules="安静",
                    entrance="校门",
                    children=[
                        SceneLayerStateRecord(
                            id="scene-classroom",
                            title="力学教室",
                            scope_label="room",
                            summary="用于讲解牛顿定律",
                            atmosphere="明亮",
                            rules="保持专注",
                            entrance="前门",
                            objects=[
                                SceneObjectStateRecord(
                                    id="scene-object-board",
                                    name="黑板",
                                    description="写满受力分析的板书",
                                    interaction="可以在上面推导公式",
                                    tags="board,force",
                                )
                            ],
                            children=[],
                        )
                    ],
                    objects=[],
                )
            ],
        )

        bound_scene = self.session_scene_service.clone_scene_for_session(
            session_id="session-demo",
            document_id="doc-1",
            persona_id="mentor-aurora",
            scene_profile=source_profile,
        )

        self.assertIsNotNone(bound_scene)
        assert bound_scene is not None
        self.assertNotEqual(bound_scene.scene_instance_id, "")
        self.assertEqual(bound_scene.scene_profile.title, "力学教室")

        add_object_result = self.session_scene_service.add_object(
            bound_scene.scene_instance_id,
            scene_id="scene-classroom",
            name="滑块",
            description="放在实验桌上的滑块",
            interaction="用于演示摩擦力",
            tags="experiment,force",
        )
        self.assertTrue(add_object_result["ok"])
        self.assertIn("滑块", add_object_result["summary"])

        updated_scene = self.session_scene_service.require_scene(bound_scene.scene_instance_id)
        selected_layer = updated_scene.scene_profile.scene_tree[0].children[0]
        self.assertEqual(len(selected_layer.objects), 2)
        self.assertEqual(source_profile.scene_tree[0].children[0].objects[0].name, "黑板")

    def test_append_turn_persists_scene_profile_and_tool_traces(self) -> None:
        session = self.study_session_service.create_session(
            document_id="doc-1",
            persona_id="mentor-aurora",
            section_id="chapter-1",
        )
        next_scene_profile = SceneProfileRecord(
            scene_name="力学教室",
            scene_id="scene-classroom",
            title="实验桌前",
            summary="已转移到实验桌附近。",
            tags=["experiment"],
            selected_path=["校园", "物理楼", "实验桌前"],
            focus_object_names=["滑块"],
            scene_tree=[],
        )
        result = StudyChatResult(
            reply="我们现在转到实验桌前观察受力。",
            citations=[
                Citation(
                    section_id="chapter-1",
                    title="第一章",
                    page_start=1,
                    page_end=2,
                )
            ],
            character_events=[],
            tool_calls=[
                ChatToolCallTraceRecord(
                    tool_call_id="call-1",
                    tool_name="move_to_scene",
                    arguments_json='{"scene_id":"scene-classroom"}',
                    result_summary="已切换到场景 校园 / 物理楼 / 实验桌前。",
                    result_json='{"ok":true}',
                )
            ],
            scene_profile=next_scene_profile,
        )

        updated_session = self.study_session_service.append_turn(
            session_id=session.id,
            learner_message="我们切到实验桌前吧",
            result=result,
        )

        self.assertEqual(updated_session.scene_profile.title, "实验桌前")
        self.assertEqual(updated_session.turns[-1].tool_calls[0].tool_name, "move_to_scene")
        self.assertEqual(updated_session.turns[-1].scene_profile.title, "实验桌前")

    def test_local_store_save_list_is_safe_under_concurrent_writes(self) -> None:
        store = LocalJsonStore(Path(self.temp_dir.name))
        barrier = threading.Barrier(4)
        errors: list[Exception] = []

        def writer(index: int) -> None:
            try:
                barrier.wait(timeout=2)
                for turn_index in range(20):
                    session = self.study_session_service.create_session(
                        session_id=f"session-{index}-{turn_index}",
                        document_id=f"doc-{index}",
                        persona_id="mentor-aurora",
                        section_id=f"chapter-{turn_index}",
                    )
                    store.save_list("sessions", [session])
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=writer, args=(index,)) for index in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=5)

        self.assertFalse(errors, msg=str(errors))
        saved_sessions = store.load_list("sessions", StudySessionRecord)
        self.assertTrue(saved_sessions)

    def test_runtime_settings_migrates_missing_fields_from_base_settings(self) -> None:
        store = LocalJsonStore(Path(self.temp_dir.name))
        runtime_dir = Path(self.temp_dir.name) / "runtime_settings"
        runtime_dir.mkdir(parents=True, exist_ok=True)
        (runtime_dir / "default.json").write_text(
            json.dumps(
                {
                    "config_id": "default",
                    "updated_at": "2026-04-11T00:00:00+00:00",
                    "plan_provider": "openai",
                    "openai_api_key": "sk-test",
                    "openai_base_url": "https://example.com/v1",
                    "openai_chat_model": "gemini-2.5-pro",
                },
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )

        from app.core.settings import Settings

        base_settings = Settings(
            plan_provider="openai",
            openai_api_key="sk-test",
            openai_base_url="https://example.com/v1",
            openai_chat_model="gemini-2.5-pro",
            openai_chat_max_tokens=4800,
            openai_timeout_seconds=120,
        )
        service = RuntimeSettingsService(store, base_settings)

        self.assertEqual(service.describe()["openai_chat_max_tokens"], 4800)
        self.assertTrue(service.describe()["openai_setting_web_search_enabled"])
        self.assertEqual(service.effective_settings().openai_chat_max_tokens, 4800)

    def test_parse_chat_model_reply_accepts_plain_text_without_warning_path(self) -> None:
        raw_payload = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {
                        "content": "好的，我们继续！你提到的是定端同伦，也就是固定端点的同伦。"
                    },
                }
            ],
            "usage": {
                "completion_tokens": 64,
                "completion_tokens_details": {
                    "reasoning_tokens": 32,
                },
            },
        }

        with self.assertLogs("vibe_learner.model_provider", level="INFO") as logs:
            result = _parse_chat_model_reply(
                raw_payload=raw_payload,
                tool_results=[],
                fallback_memory_trace=[],
                tool_traces=[],
            )

        self.assertIn("定端同伦", result.text)
        self.assertEqual(result.mood, "calm")
        self.assertEqual(result.action, "point")
        joined = "\n".join(logs.output)
        self.assertIn("model.chat.parse_fallback using_plain_text", joined)

    def test_openai_chat_prompt_includes_explicit_json_schema(self) -> None:
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-plan-test",
            chat_model="gpt-test",
            timeout_seconds=3,
        )

        captured_payloads: list[dict[str, object]] = []

        def fake_completion(**kwargs):
            captured_payloads.append(kwargs)
            return FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "text": "这是一个结构化回答。",
                                        "mood": "calm",
                                        "action": "point",
                                    }
                                )
                            }
                        }
                    ]
                }
            )

        with patch("app.services.model_provider.litellm_completion", side_effect=fake_completion):
            reply = provider.generate_chat(
                persona=self.persona_engine.require_persona("mentor-aurora"),
                section_id="chapter-1",
                message="解释一下这个概念",
                section_context="Section: Chapter 1",
            )

        self.assertEqual(reply.text, "这是一个结构化回答。")
        self.assertTrue(captured_payloads)
        system_content = captured_payloads[0]["messages"][0]["content"]
        self.assertIn("必须严格输出单个 JSON 对象", system_content)
        self.assertIn(CHAT_JSON_SCHEMA, system_content)

    def test_openai_chat_tool_round_appends_json_only_followup(self) -> None:
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-plan-test",
            chat_model="gpt-test",
            timeout_seconds=3,
        )
        captured_payloads: list[dict[str, object]] = []
        responses = [
            FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {
                                            "name": "ask_multiple_choice_question",
                                            "arguments": json.dumps({"topic": "集合", "difficulty": "medium"}),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ),
            FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "text": "先做这道题，再告诉我你的思路。",
                                        "mood": "encouraging",
                                        "action": "lean_in",
                                    }
                                )
                            }
                        }
                    ]
                }
            ),
        ]

        def fake_completion(**kwargs):
            captured_payloads.append(kwargs)
            return responses.pop(0)

        with patch("app.services.model_provider.litellm_completion", side_effect=fake_completion):
            reply = provider.generate_chat(
                persona=self.persona_engine.require_persona("mentor-aurora"),
                section_id="chapter-1",
                message="给我出一道题",
                section_context="Section: Chapter 1",
            )

        self.assertEqual(reply.action, "lean_in")
        self.assertGreaterEqual(len(captured_payloads), 2)
        second_messages = captured_payloads[1]["messages"]
        self.assertTrue(
            any(
                message["role"] == "user"
                and "工具调用已完成。请根据现有上下文判断下一步。" in str(message["content"])
                for message in second_messages
            )
        )
        self.assertTrue(
            any(
                message["role"] == "user" and CHAT_JSON_SCHEMA in str(message["content"])
                for message in second_messages
            )
        )
        self.assertTrue(
            any(
                message["role"] == "user"
                and "与场景互动和读取课本页面相关的工具不受这条抑制" in str(message["content"])
                for message in second_messages
            )
        )

    def test_openai_chat_exempt_tool_rounds_do_not_consume_limit(self) -> None:
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-plan-test",
            chat_model="gpt-test",
            timeout_seconds=3,
            chat_tool_max_rounds=1,
        )
        captured_payloads: list[dict[str, object]] = []
        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-1",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 6,
                "total_characters": 600,
                "extraction_method": "text",
                "ocr_applied": False,
                "pages": [],
                "sections": [],
                "study_units": [],
                "chunks": [
                    {
                        "id": "chunk-1",
                        "document_id": "doc-1",
                        "section_id": "chapter-1",
                        "page_start": 2,
                        "page_end": 2,
                        "char_count": 120,
                        "text_preview": "力的定义",
                        "content": "第 2 页详细解释了力、作用点与方向。",
                    }
                ],
                "warnings": [],
                "dominant_language_hint": "zh",
            }
        )
        scene_profile = SceneProfileRecord(
            scene_name="力学教室",
            scene_id="scene-classroom",
            title="力学教室",
            summary="黑板前摆着实验台。",
            tags=["classroom"],
            selected_path=["校园", "物理楼", "力学教室"],
            focus_object_names=["黑板", "实验台"],
            scene_tree=[
                SceneLayerStateRecord(
                    id="scene-classroom",
                    title="力学教室",
                    scope_label="room",
                    summary="黑板前摆着实验台。",
                    atmosphere="明亮",
                    rules="讲解时保持专注",
                    entrance="教室前门",
                    objects=[],
                    children=[],
                )
            ],
        )
        bound_scene = self.session_scene_service.clone_scene_for_session(
            session_id="session-chat-limit",
            document_id="doc-1",
            persona_id="mentor-aurora",
            scene_profile=scene_profile,
        )
        assert bound_scene is not None
        scene_tool_runtime = self.session_scene_service.build_tool_runtime(bound_scene.scene_instance_id)
        responses = [
            FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call-page-1",
                                        "type": "function",
                                        "function": {
                                            "name": "read_page_range_content",
                                            "arguments": json.dumps({"page_start": 2, "page_end": 2}),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ),
            FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call-scene-1",
                                        "type": "function",
                                        "function": {
                                            "name": "read_scene_overview",
                                            "arguments": json.dumps({}),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ),
            FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "text": "我先对照课本第 2 页，再把黑板前的受力方向和页面定义对齐。",
                                        "mood": "focused",
                                        "action": "翻到第 2 页，抬手指向黑板上的受力箭头",
                                    }
                                )
                            }
                        }
                    ]
                }
            ),
        ]

        def fake_completion(**kwargs):
            captured_payloads.append(kwargs)
            return responses.pop(0)

        with patch("app.services.model_provider.litellm_completion", side_effect=fake_completion):
            reply = provider.generate_chat(
                persona=self.persona_engine.require_persona("mentor-aurora"),
                section_id="chapter-1",
                message="结合场景和课本解释一下力的方向",
                section_context="Section: Chapter 1",
                debug_report=debug_report,
                scene_tool_runtime=scene_tool_runtime,
            )

        self.assertEqual(reply.mood, "focused")
        self.assertEqual(len(captured_payloads), 3)
        second_messages = captured_payloads[1]["messages"]
        third_payload_tools = [tool["function"]["name"] for tool in captured_payloads[2]["tools"]]
        self.assertTrue(
            any(
                message["role"] == "user"
                and "这类轮次不计入常规工具调用限制，也允许重复调用" in str(message["content"])
                for message in second_messages
            )
        )
        self.assertIn("read_page_range_content", third_payload_tools)
        self.assertIn("read_scene_overview", third_payload_tools)

    def test_grading_changes_based_on_answer_length(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        short = self.orchestrator.grade_submission(
            persona=persona, exercise_id="exercise-1", answer="太短了"
        )
        long = self.orchestrator.grade_submission(
            persona=persona,
            exercise_id="exercise-1",
            answer="这是一个相对完整的回答，包含概念解释、教材例子以及一点自己的复述。",
        )
        self.assertLess(short.score, long.score)
        self.assertEqual(long.character_events[0].action, "smile")

    def test_plan_and_session_can_be_persisted(self) -> None:
        from fastapi import UploadFile

        sample_pdf = Path(self.temp_dir.name) / "physics-notes.pdf"
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Chapter 1 Mechanics", fontsize=24)
        page.insert_text(
            (72, 120),
            "Newton's first law explains inertia and stable motion.\n"
            "A body stays at rest or in uniform motion unless acted upon by a force.",
            fontsize=12,
        )
        second_page = pdf.new_page()
        second_page.insert_text((72, 72), "1.1 Inertia", fontsize=20)
        second_page.insert_text(
            (72, 120),
            "Inertia describes resistance to changes in motion.\n"
            "Use textbook examples to compare rest and constant velocity.",
            fontsize=12,
        )
        pdf.save(sample_pdf)
        pdf.close()

        upload = UploadFile(
            filename="physics-notes.pdf",
            file=open(sample_pdf, "rb"),
        )
        try:
            document = self.document_service.create_document(upload)
        finally:
            upload.file.close()

        processed = self.document_service.process_document(document.id)
        persona = self.persona_engine.require_persona("mentor-aurora")
        plan = self.plan_service.create_plan(
            goal=LearningGoalInput(
                document_id=processed.id,
                persona_id=persona.id,
                objective="掌握第一章",
            ),
            document=processed,
            persona_name=persona.name,
            persona=persona,
        )
        session = self.study_session_service.create_session(
            document_id=processed.id,
            persona_id=persona.id,
            section_id=processed.sections[0].id,
        )

        reply = self.orchestrator.generate_chat_reply(
            session_id=session.id,
            persona=persona,
            message="解释本章核心定义",
            section_id=processed.sections[0].id,
        )
        updated_session = self.study_session_service.append_turn(
            session_id=session.id,
            learner_message="解释本章核心定义",
            result=reply,
        )
        debug = self.document_service.require_debug_report(processed.id)

        self.assertTrue(plan.overview)
        self.assertGreaterEqual(processed.page_count, 2)
        self.assertGreaterEqual(processed.chunk_count, 1)
        self.assertTrue(debug.pages[0].text_preview)
        self.assertTrue(debug.sections)
        self.assertTrue(processed.study_units)
        self.assertTrue(plan.schedule)
        self.assertTrue(any(saved_plan.id == plan.id for saved_plan in self.plan_service.list_plans()))
        self.assertEqual(updated_session.turns[0].assistant_reply, reply.reply)
        self.assertEqual(updated_session.section_id, processed.sections[0].id)
        self.assertTrue(any(item.title.endswith("精读") for item in plan.schedule))

    def test_api_response_model_accepts_domain_dump(self) -> None:
        from fastapi import UploadFile

        sample_pdf = Path(self.temp_dir.name) / "response-shape.pdf"
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Section 1", fontsize=24)
        page.insert_text((72, 120), "This is enough text to build a parsed document.", fontsize=12)
        pdf.save(sample_pdf)
        pdf.close()

        upload = UploadFile(filename="response-shape.pdf", file=open(sample_pdf, "rb"))
        try:
            document = self.document_service.create_document(upload)
        finally:
            upload.file.close()

        processed = self.document_service.process_document(document.id)
        response = DocumentResponse.model_validate(processed.model_dump())

        self.assertEqual(response.id, processed.id)
        self.assertEqual(response.page_count, processed.page_count)

    def test_learning_plan_prompt_template_loads_from_text_file(self) -> None:
        template = load_learning_plan_prompt_template()

        self.assertIn("必须严格输出单个 JSON 对象", template.system_prompt)
        self.assertIn('"course_title": string', template.system_prompt)
        self.assertGreaterEqual(len(template.user_instructions), 3)
        self.assertIn("study_units", template.user_instructions[0])

    def test_learning_plan_tool_specs_filter_by_context(self) -> None:
        all_specs = get_learning_plan_tool_specs()
        self.assertEqual(
            [spec["name"] for spec in all_specs],
            [
                "get_study_unit_detail",
                "ask_planning_question",
                "estimate_plan_completion",
                "revise_study_units",
                "read_page_range_content",
                "read_page_range_images",
            ],
        )

        contextual_specs = get_learning_plan_tool_specs(
            detail_map={"unit-1": {"unit_id": "unit-1"}},
            debug_report=None,
        )
        self.assertEqual(
            [spec["name"] for spec in contextual_specs],
            ["get_study_unit_detail", "ask_planning_question", "estimate_plan_completion"],
        )

        multimodal_specs = get_learning_plan_tool_specs(
            study_units=[
                StudyUnitRecord(
                    id="unit-1",
                    document_id="doc-1",
                    title="Chapter 1",
                    page_start=1,
                    page_end=4,
                )
            ],
            detail_map={"unit-1": {"unit_id": "unit-1"}},
            debug_report=DocumentDebugRecord.model_validate(
                {
                    "document_id": "doc-1",
                    "parser_name": "parser",
                    "processed_at": "2026-04-09T00:00:00+00:00",
                    "page_count": 1,
                    "total_characters": 100,
                    "extraction_method": "text",
                    "ocr_applied": False,
                    "pages": [],
                    "sections": [],
                    "study_units": [],
                    "chunks": [],
                    "warnings": [],
                    "dominant_language_hint": "en",
                }
            ),
            document_path="/tmp/doc-1.pdf",
            multimodal_enabled=True,
        )
        self.assertEqual(
            [spec["name"] for spec in multimodal_specs],
            [
                "get_study_unit_detail",
                "ask_planning_question",
                "estimate_plan_completion",
                "revise_study_units",
                "read_page_range_content",
                "read_page_range_images",
            ],
        )

    def test_planning_question_tool_emits_follow_up_prompt(self) -> None:
        runtime = build_plan_tool_runtime()

        execution = runtime.execute_tool_call(
            {
                "id": "call-question-1",
                "type": "function",
                "function": {
                    "name": "ask_planning_question",
                    "arguments": json.dumps(
                        {
                            "question": "这次学习更想追求考试提分还是概念打底？",
                            "reason": "目标描述还不够具体。",
                            "assumptions": ["先按概念打底来规划", "把今日任务控制在 3 步以内"],
                        }
                    ),
                },
            }
        )

        self.assertTrue(execution.result["ok"])
        self.assertEqual(execution.result["tool_name"], "ask_planning_question")
        self.assertEqual(len(execution.follow_up_messages), 1)
        self.assertIn("需要向学习者确认", execution.follow_up_messages[0]["content"])

    def test_plan_completion_tool_scores_coarse_structure(self) -> None:
        runtime = build_plan_tool_runtime(
            study_units=[
                StudyUnitRecord(
                    id="unit-1",
                    document_id="doc-1",
                    title="Combined Unit",
                    page_start=1,
                    page_end=100,
                    summary="过宽的学习单元。",
                    confidence=0.5,
                )
            ]
        )

        execution = runtime.execute_tool_call(
            {
                "id": "call-completion-1",
                "type": "function",
                "function": {
                    "name": "estimate_plan_completion",
                    "arguments": json.dumps({"focus": "目录细度"}),
                },
            }
        )

        self.assertTrue(execution.result["ok"])
        self.assertIn("completion_score", execution.result)
        self.assertLessEqual(int(execution.result["completion_score"]), 50)
        self.assertIn("目录细度", execution.result["focus"])

    def test_mock_provider_prioritizes_learning_goal_in_plan_summary(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        provider = MockModelProvider()
        goal = LearningGoalInput(
            document_id="doc-1",
            persona_id=persona.id,
            objective="先把集合与命题逻辑的基础概念讲清楚",
        )

        reply = provider.generate_learning_plan(
            persona=persona,
            document_title="Discrete Mathematics",
            goal=goal,
            study_units=[
                StudyUnitRecord(
                    id="unit-1",
                    document_id="doc-1",
                    title="Chapter 1 Foundations",
                    page_start=1,
                    page_end=18,
                    summary="聚焦集合与命题逻辑。",
                    confidence=0.9,
                )
            ],
        )

        self.assertIn("目标优先", reply.overview)
        self.assertIn("先把集合与命题逻辑的基础概念讲清楚", reply.today_tasks[0])

    def test_multimodal_page_image_tool_creates_follow_up_message(self) -> None:
        runtime = build_plan_tool_runtime(
            document_path="/tmp/discrete-math.pdf",
            multimodal_enabled=True,
        )

        with patch(
            "app.services.plan_tool_runtime.read_page_range_images",
            return_value={
                "page_start": 4,
                "page_end": 5,
                "image_count": 2,
                "images": [
                    {
                        "page_number": 4,
                        "mime_type": "image/png",
                        "image_url": "data:image/png;base64,AAA",
                    },
                    {
                        "page_number": 5,
                        "mime_type": "image/png",
                        "image_url": "data:image/png;base64,BBB",
                    },
                ],
            },
        ):
            execution = runtime.execute_tool_call(
                {
                    "id": "call-image-1",
                    "type": "function",
                    "function": {
                        "name": "read_page_range_images",
                        "arguments": json.dumps(
                            {
                                "page_start": 4,
                                "page_end": 5,
                                "max_images": 2,
                            }
                        ),
                    },
                }
            )

        self.assertEqual(execution.tool_name, "read_page_range_images")
        self.assertEqual(execution.result["image_count"], 2)
        self.assertEqual(execution.result["page_numbers"], [4, 5])
        self.assertEqual(len(execution.follow_up_messages), 1)
        follow_up_content = execution.follow_up_messages[0]["content"]
        self.assertEqual(follow_up_content[0]["type"], "text")
        self.assertEqual(follow_up_content[1]["type"], "image_url")
        self.assertEqual(follow_up_content[1]["image_url"]["url"], "data:image/png;base64,AAA")

    def test_revise_study_units_tool_updates_active_segmentation(self) -> None:
        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-1",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 20,
                "total_characters": 1200,
                "extraction_method": "text",
                "ocr_applied": False,
                "pages": [],
                "sections": [
                    {
                        "id": "raw-1",
                        "document_id": "doc-1",
                        "title": "Chapter 1",
                        "page_start": 1,
                        "page_end": 10,
                        "level": 1,
                    },
                    {
                        "id": "raw-2",
                        "document_id": "doc-1",
                        "title": "Chapter 2",
                        "page_start": 11,
                        "page_end": 20,
                        "level": 1,
                    },
                ],
                "study_units": [],
                "chunks": [],
                "warnings": [],
                "dominant_language_hint": "en",
            }
        )
        runtime = build_plan_tool_runtime(
            study_units=[
                StudyUnitRecord(
                    id="unit-1",
                    document_id="doc-1",
                    title="Combined Unit",
                    page_start=1,
                    page_end=20,
                    summary="旧划分。",
                    confidence=0.6,
                )
            ],
            debug_report=debug_report,
            detail_map={
                "unit-1": {
                    "unit_id": "unit-1",
                    "title": "Combined Unit",
                    "page_start": 1,
                    "page_end": 20,
                    "summary": "旧划分。",
                    "unit_kind": "chapter",
                    "include_in_plan": True,
                    "related_section_ids": ["raw-1", "raw-2"],
                    "subsection_titles": [],
                    "related_sections": [],
                    "chunk_count": 0,
                    "chunk_excerpts": [],
                }
            },
        )

        execution = runtime.execute_tool_call(
            {
                "id": "call-revise-1",
                "type": "function",
                "function": {
                    "name": "revise_study_units",
                    "arguments": json.dumps(
                        {
                            "study_units": [
                                {
                                    "title": "Chapter 1 Foundations",
                                    "page_start": 1,
                                    "page_end": 10,
                                },
                                {
                                    "title": "Chapter 2 Practice",
                                    "page_start": 11,
                                    "page_end": 20,
                                },
                            ],
                            "rationale": "The original segmentation merged two chapters.",
                        }
                    ),
                },
            }
        )

        self.assertTrue(execution.result["ok"])
        self.assertEqual(execution.result["study_unit_count"], 2)
        self.assertEqual(
            [unit.id for unit in runtime.current_study_units()],
            ["doc-1:study-unit:llm:1", "doc-1:study-unit:llm:2"],
        )
        self.assertIn("doc-1:study-unit:llm:1", runtime.context.detail_map)

    def test_document_planning_trace_route_wraps_trace_payload(self) -> None:
        trace = PlanGenerationTraceRecord.model_validate(
            {
                "document_id": "doc-1",
                "plan_id": "plan-1",
                "model": "gpt-test",
                "created_at": "2026-04-10T00:00:00+00:00",
                "rounds": [
                    {
                        "round_index": 0,
                        "finish_reason": "tool_calls",
                        "assistant_content": "",
                        "thinking": "Need more detail.",
                        "elapsed_ms": 120,
                        "timeout_seconds": 3,
                        "tool_calls": [
                            {
                                "tool_call_id": "call-1",
                                "tool_name": "get_study_unit_detail",
                                "arguments_json": "{\"study_unit_id\":\"unit-1\"}",
                                "result_json": "{\"ok\":true}",
                            }
                        ],
                    }
                ],
            }
        )

        with patch("app.api.routes.container.store.load_item", return_value=trace):
            response = get_document_planning_trace("doc-1")

        self.assertTrue(response.has_trace)
        self.assertIsNotNone(response.trace)
        self.assertEqual(response.summary.round_count, 1)
        self.assertEqual(response.summary.tool_call_count, 1)
        self.assertEqual(response.trace.model, "gpt-test")

    def test_document_process_stream_report_can_be_replayed_after_sync_processing(self) -> None:
        from fastapi import UploadFile

        sample_pdf = Path(self.temp_dir.name) / "stream-process.pdf"
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Chapter 1", fontsize=24)
        page.insert_text((72, 120), "Enough text to produce chunks and study units.", fontsize=12)
        pdf.save(sample_pdf)
        pdf.close()

        upload = UploadFile(filename="stream-process.pdf", file=open(sample_pdf, "rb"))
        try:
            document = self.document_service.create_document(upload)
        finally:
            upload.file.close()

        recorder = StreamReportRecorder(
            store=self.document_service.store,
            category=DOCUMENT_PROCESS_STREAM_CATEGORY,
            document_id=document.id,
            stream_kind="document_process",
        )
        processed = self.document_service.process_document(
            document.id,
            progress_callback=recorder.callback,
        )
        recorder.emit(
            "stream_completed",
            {
                "document_id": processed.id,
                "status": processed.status,
            },
        )

        report = StreamReportRecorder.load(
            store=self.document_service.store,
            category=DOCUMENT_PROCESS_STREAM_CATEGORY,
            document_id=document.id,
            stream_kind="document_process",
        )

        self.assertEqual(report.status, "completed")
        self.assertTrue(report.events)
        self.assertIn("document_processing_started", [event.stage for event in report.events])
        self.assertIn("stream_completed", [event.stage for event in report.events])

    def test_learning_plan_stream_report_can_be_replayed_after_sync_generation(self) -> None:
        from fastapi import UploadFile

        sample_pdf = Path(self.temp_dir.name) / "stream-plan.pdf"
        pdf = fitz.open()
        page = pdf.new_page()
        page.insert_text((72, 72), "Chapter 1", fontsize=24)
        page.insert_text((72, 120), "Enough text to support a simple study plan.", fontsize=12)
        pdf.save(sample_pdf)
        pdf.close()

        upload = UploadFile(filename="stream-plan.pdf", file=open(sample_pdf, "rb"))
        try:
            document = self.document_service.create_document(upload)
        finally:
            upload.file.close()

        processed = self.document_service.process_document(document.id)
        persona = self.persona_engine.require_persona("mentor-aurora")
        recorder = StreamReportRecorder(
            store=self.plan_service.store,
            category=LEARNING_PLAN_STREAM_CATEGORY,
            document_id=processed.id,
            stream_kind="learning_plan",
        )
        recorder.emit(
            "learning_plan_started",
            {
                "document_id": processed.id,
                "persona_id": persona.id,
            },
        )
        plan = self.plan_service.create_plan(
            goal=LearningGoalInput(
                document_id=processed.id,
                persona_id=persona.id,
                objective="掌握第一章",
            ),
            document=processed,
            persona_name=persona.name,
            persona=persona,
            progress_callback=recorder.callback,
        )
        recorder.emit(
            "stream_completed",
            {
                "document_id": processed.id,
                "plan_id": plan.id,
            },
        )

        report = StreamReportRecorder.load(
            store=self.plan_service.store,
            category=LEARNING_PLAN_STREAM_CATEGORY,
            document_id=processed.id,
            stream_kind="learning_plan",
        )

        stages = [event.stage for event in report.events]
        self.assertEqual(report.status, "completed")
        self.assertIn("learning_plan_started", stages)
        self.assertIn("heuristic_plan_built", stages)
        self.assertIn("model_plan_applied", stages)
        self.assertIn("stream_completed", stages)

    def test_parser_force_ocr_can_recover_blank_page(self) -> None:
        sample_pdf = Path(self.temp_dir.name) / "blank-scan.pdf"
        pdf = fitz.open()
        pdf.new_page()
        pdf.save(sample_pdf)
        pdf.close()

        parser = DocumentParser()
        with patch.object(
            parser,
            "_ocr_page",
            return_value="Chapter 1 Recovered\nThis page was recovered through OCR fallback.",
        ):
            report = parser.parse(
                document_id="doc-ocr",
                title="Recovered Scan",
                stored_path=str(sample_pdf),
                force_ocr=True,
            )

        self.assertTrue(report.ocr_applied)
        self.assertEqual(report.extraction_method, "ocr_forced")
        self.assertEqual(report.pages[0].extraction_source, "ocr")
        self.assertGreaterEqual(len(report.chunks), 1)

    def test_parser_filters_noisy_heading_candidates(self) -> None:
        sample_pdf = Path(self.temp_dir.name) / "heading-filter.pdf"
        pdf = fitz.open()
        page1 = pdf.new_page()
        page1.insert_text((72, 72), "nff= {x:VYEff(XEY)};", fontsize=24)
        page1.insert_text((72, 120), "Body text for the page.", fontsize=12)
        page2 = pdf.new_page()
        page2.insert_text((72, 72), "Chapter 1 Introduction", fontsize=24)
        page2.insert_text((72, 120), "A legitimate heading should survive filtering.", fontsize=12)
        pdf.save(sample_pdf)
        pdf.close()

        parser = DocumentParser()
        report = parser.parse(
            document_id="doc-heading",
            title="Heading Filter",
            stored_path=str(sample_pdf),
        )

        titles = [section.title for section in report.sections]
        self.assertTrue(any("Chapter 1 Introduction" in title for title in titles))
        self.assertFalse(any("VYEff" in title for title in titles))

    def test_parser_extracts_bridge_style_ocr_header(self) -> None:
        parser = DocumentParser()
        candidates = parser._extract_ocr_heading_candidates(
            page_number=40,
            page_text=(
                "2. Computable Partial Functions 29 is primitive recursive. "
                "Does power(m,n)=m^n define a primitive recursive function?"
            ),
        )

        self.assertTrue(candidates)
        self.assertEqual(candidates[0].text, "2. Computable Partial Functions")

    def test_parser_rejects_sentence_like_ocr_header(self) -> None:
        parser = DocumentParser()
        candidates = parser._extract_ocr_heading_candidates(
            page_number=84,
            page_text=(
                "2 <). = A, then there is a K-Aronszajn tree (Exercise 37). Thus, under GCH, "
                "we continue the proof on this page."
            ),
        )

        self.assertEqual(candidates, [])

    def test_parser_rejects_exercise_prompts_as_headings(self) -> None:
        parser = DocumentParser()

        self.assertTrue(parser._looks_like_noisy_heading("Exercises"))
        self.assertTrue(parser._looks_like_noisy_heading("2 Design a Turing machine, with input alphabet {0,1}"))
        self.assertTrue(parser._looks_like_noisy_heading("3 For this exercise we recall the Goldbach Conjecture"))
        self.assertFalse(parser._looks_like_noisy_heading("2. Computable Partial Functions"))

    def test_parser_normalizes_solution_heading_prefix(self) -> None:
        parser = DocumentParser()

        self.assertEqual(
            parser._normalize_heading_text("130 — Solutions to Exercises 117"),
            "Solutions to Exercises",
        )

    def test_parser_detects_and_strips_recurrent_headers_and_footers(self) -> None:
        parser = DocumentParser()
        pages = [
            ParsedPage(
                page_number=index,
                line_entries=[
                    (f"1. What Is a Turing Machine? {index + 4}", 0.0),
                    ("Core body text for this page.", 0.0),
                    (str(index + 4), 0.0),
                ],
                dominant_font_size=0.0,
                extraction_source="ocr",
                warnings=[],
                used_ocr=True,
            )
            for index in range(1, 5)
        ]

        top_patterns, bottom_patterns = parser._detect_margin_patterns(pages)
        stripped, stripped_count = parser._strip_margin_lines(
            pages[0].line_entries,
            top_patterns=top_patterns,
            bottom_patterns=bottom_patterns,
        )

        self.assertTrue(any("what is a turing machine" in pattern for pattern in top_patterns))
        self.assertIn("#", bottom_patterns)
        self.assertEqual(stripped_count, 2)
        self.assertEqual([text for text, _font_size in stripped], ["Core body text for this page."])

    def test_parser_builds_dual_sections_from_toc_and_assigns_chunk_targets(self) -> None:
        sample_pdf = Path(self.temp_dir.name) / "toc-dual.pdf"
        pdf = fitz.open()
        for index in range(1, 9):
            page = pdf.new_page()
            page.insert_text((72, 72), f"Page {index}", fontsize=12)
            page.insert_text(
                (72, 120),
                (
                    f"Body text for page {index}. "
                    "This section includes enough explanatory prose to produce stable chunking. "
                    "We repeat this sentence to ensure the parser has usable material. "
                )
                * 6,
                fontsize=12,
            )
        pdf.set_toc(
            [
                [1, "Chapter 1", 1],
                [2, "1.1 Basics", 2],
                [2, "1.2 Advanced", 4],
                [1, "Chapter 2", 6],
                [2, "2.1 Review", 7],
                [1, "Appendix", 8],
            ]
        )
        pdf.save(sample_pdf)
        pdf.close()

        parser = DocumentParser()
        report = parser.parse(
            document_id="doc-toc-dual",
            title="Dual TOC",
            stored_path=str(sample_pdf),
        )

        level_1 = [section for section in report.sections if section.level == 1]
        level_2 = [section for section in report.sections if section.level == 2]
        chunk_section_ids = {chunk.section_id for chunk in report.chunks}

        self.assertGreaterEqual(len(level_1), 3)
        self.assertGreaterEqual(len(level_2), 3)
        self.assertTrue(any(section.title == "1.1 Basics" for section in level_2))
        self.assertTrue(any(section.title == "2.1 Review" for section in level_2))
        self.assertTrue(any(section_id.startswith("doc-toc-dual:section:l1:") for section_id in chunk_section_ids))
        self.assertTrue(any(section_id.startswith("doc-toc-dual:section:l2:") for section_id in chunk_section_ids))

    def test_study_arrangement_cleans_exercise_like_sections_before_plan(self) -> None:
        arranger = StudyArrangementService()
        document = DocumentResponse.model_validate(
            {
                "id": "doc-arrange",
                "title": "Computability",
                "original_filename": "computability.pdf",
                "stored_path": "/tmp/computability.pdf",
                "status": "processed",
                "ocr_status": "fallback_used",
                "created_at": "2026-04-09T00:00:00+00:00",
                "updated_at": "2026-04-09T00:00:00+00:00",
                "sections": [],
                "study_units": [],
                "study_unit_count": 0,
                "page_count": 30,
                "chunk_count": 12,
                "preview_excerpt": "sample",
                "debug_ready": True,
            }
        )
        from app.models.domain import DocumentDebugRecord

        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-arrange",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 30,
                "total_characters": 3000,
                "extraction_method": "ocr",
                "ocr_applied": True,
                "ocr_language": "eng",
                "pages": [
                    {
                        "page_number": 1,
                        "char_count": 200,
                        "word_count": 30,
                        "text_preview": "1\nWhat Is a Turing Machine?\nIntro body text",
                        "dominant_font_size": 0.0,
                        "extraction_source": "ocr",
                        "heading_candidates": [],
                    },
                    {
                        "page_number": 10,
                        "char_count": 200,
                        "word_count": 30,
                        "text_preview": "2 Design a Turing machine, with input alphabet {0,1}\nBody text",
                        "dominant_font_size": 0.0,
                        "extraction_source": "ocr",
                        "heading_candidates": [],
                    },
                    {
                        "page_number": 12,
                        "char_count": 200,
                        "word_count": 30,
                        "text_preview": "2. Computable Partial Functions\nBody text",
                        "dominant_font_size": 0.0,
                        "extraction_source": "ocr",
                        "heading_candidates": [],
                    },
                ],
                "sections": [
                    {
                        "id": "raw-1",
                        "document_id": "doc-arrange",
                        "title": "1 What Is a Turing Machine?",
                        "page_start": 1,
                        "page_end": 9,
                        "level": 1,
                    },
                    {
                        "id": "raw-2",
                        "document_id": "doc-arrange",
                        "title": "2 Design a Turing machine, with input alphabet {0,1}",
                        "page_start": 10,
                        "page_end": 11,
                        "level": 1,
                    },
                    {
                        "id": "raw-3",
                        "document_id": "doc-arrange",
                        "title": "2. Computable Partial Functions",
                        "page_start": 12,
                        "page_end": 30,
                        "level": 1,
                    },
                ],
                "study_units": [],
                "chunks": [],
                "warnings": [],
                "dominant_language_hint": "en",
            }
        )

        units = arranger.build_study_units(document=document, debug_report=debug_report)

        self.assertEqual([unit.title for unit in units if unit.include_in_plan], [
            "1 What Is a Turing Machine?",
            "2. Computable Partial Functions",
        ])
        self.assertEqual(units[0].page_end, 11)

    def test_learning_plan_prompt_uses_cleaned_study_units_and_constraints(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        goal = LearningGoalInput(
            document_id="doc-1",
            persona_id=persona.id,
            objective="掌握第一章",
        )
        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-1",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 18,
                "total_characters": 2000,
                "extraction_method": "ocr",
                "ocr_applied": True,
                "ocr_language": "eng",
                "pages": [],
                "sections": [
                    {
                        "id": "raw-1",
                        "document_id": "doc-1",
                        "title": "Chapter 1 Foundations",
                        "page_start": 1,
                        "page_end": 18,
                        "level": 1,
                    },
                    {
                        "id": "raw-1-1",
                        "document_id": "doc-1",
                        "title": "1.1 Sets",
                        "page_start": 1,
                        "page_end": 8,
                        "level": 2,
                    },
                ],
                "study_units": [],
                "chunks": [],
                "warnings": [],
                "dominant_language_hint": "en",
            }
        )
        messages = build_learning_plan_messages(
            persona=persona,
            document_title="Discrete Mathematics",
            goal=goal,
            study_units=[
                StudyUnitRecord(
                    id="unit-1",
                    document_id="doc-1",
                    title="Chapter 1 Foundations",
                    page_start=1,
                    page_end=18,
                    source_section_ids=["raw-1"],
                    summary="聚焦集合与命题逻辑。",
                    confidence=0.9,
                )
            ],
            debug_report=debug_report,
        )

        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("必须严格输出单个 JSON 对象", messages[0]["content"])
        self.assertIn('"course_title": string', messages[0]["content"])
        self.assertNotIn("course_outline", messages[0]["content"])
        self.assertIn("Chapter 1 Foundations", messages[1]["content"])
        self.assertIn('"detail_tool_target_id": "unit-1"', messages[1]["content"])
        self.assertIn('"study_units"', messages[1]["content"])
        self.assertIn('"course_outline"', messages[1]["content"])
        self.assertIn('"segmentation_hints"', messages[1]["content"])
        self.assertIn('"recommend_continue_tool_calls": true', messages[1]["content"])
        self.assertIn("掌握第一章", messages[1]["content"])

    def test_openai_provider_parses_json_learning_plan_response(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        goal = LearningGoalInput(
            document_id="doc-1",
            persona_id=persona.id,
            objective="掌握第一章",
        )
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            timeout_seconds=3,
        )

        with patch(
            "app.services.model_provider.litellm_completion",
            return_value=FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "course_title": "Discrete Mathematics / Chapter 1 Foundations",
                                        "overview": "LLM plan overview",
                                        "study_chapters": ["Chapter 1 Foundations"],
                                        "today_tasks": ["Read Chapter 1 carefully."],
                                        "schedule": [
                                            {
                                                "unit_id": "unit-1",
                                                "title": "Chapter 1 Foundations 精读",
                                                "focus": "理解定义与例题。",
                                                "activity_type": "learn",
                                            }
                                        ],
                                    }
                                )
                            }
                        }
                    ]
                }
            ),
        ) as mocked_completion:
            reply = provider.generate_learning_plan(
                persona=persona,
                document_title="Discrete Mathematics",
                goal=goal,
                study_units=[
                    StudyUnitRecord(
                        id="unit-1",
                        document_id="doc-1",
                        title="Chapter 1 Foundations",
                        page_start=1,
                        page_end=18,
                        summary="聚焦集合与命题逻辑。",
                        confidence=0.9,
                    )
                ],
            )

        payload = mocked_completion.call_args.kwargs
        self.assertEqual(payload["model"], "openai/gpt-test")
        self.assertEqual(reply.course_title, "Discrete Mathematics / Chapter 1 Foundations")
        self.assertEqual(reply.overview, "LLM plan overview")
        self.assertEqual(reply.schedule[0].unit_id, "unit-1")

    def test_openai_provider_can_handle_plan_tool_call_roundtrip(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        goal = LearningGoalInput(
            document_id="doc-1",
            persona_id=persona.id,
            objective="掌握第一章",
        )
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            timeout_seconds=3,
        )
        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-1",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 18,
                "total_characters": 2000,
                "extraction_method": "ocr",
                "ocr_applied": True,
                "ocr_language": "eng",
                "pages": [],
                "sections": [
                    {
                        "id": "raw-1",
                        "document_id": "doc-1",
                        "title": "Chapter 1 Foundations",
                        "page_start": 1,
                        "page_end": 18,
                        "level": 1,
                    },
                    {
                        "id": "raw-1-1",
                        "document_id": "doc-1",
                        "title": "1.1 Sets",
                        "page_start": 1,
                        "page_end": 8,
                        "level": 2,
                    },
                ],
                "study_units": [],
                "chunks": [
                    {
                        "id": "chunk-1",
                        "document_id": "doc-1",
                        "section_id": "raw-1-1",
                        "page_start": 1,
                        "page_end": 3,
                        "char_count": 320,
                        "text_preview": "Sets, subsets, and membership.",
                        "content": "Sets, subsets, membership, extensionality, and simple examples.",
                    }
                ],
                "warnings": [],
                "dominant_language_hint": "en",
            }
        )

        responses = [
            FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "reasoning_content": "I should inspect the subsection structure first.",
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {
                                            "name": "get_study_unit_detail",
                                            "arguments": json.dumps(
                                                {
                                                    "study_unit_id": "unit-1",
                                                    "focus": "inspect subsection coverage",
                                                }
                                            ),
                                        },
                                    },
                                    {
                                        "id": "call-2",
                                        "type": "function",
                                        "function": {
                                            "name": "read_page_range_content",
                                            "arguments": json.dumps(
                                                {
                                                    "page_start": 1,
                                                    "page_end": 3,
                                                    "max_chars": 1200,
                                                }
                                            ),
                                        },
                                    },
                                ],
                            }
                        }
                    ]
                }
            ),
            FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "reasoning_content": "I now have enough evidence to write the plan.",
                                "content": json.dumps(
                                    {
                                        "course_title": "Discrete Mathematics / Chapter 1 Foundations",
                                        "overview": "Tool-assisted plan overview",
                                        "study_chapters": ["Chapter 1 Foundations"],
                                        "today_tasks": ["Read sets and extensionality."],
                                        "schedule": [
                                            {
                                                "unit_id": "unit-1",
                                                "title": "Chapter 1 Foundations 精读",
                                                "focus": "Cover sets, subsets, and extensionality.",
                                                "activity_type": "learn",
                                            }
                                        ],
                                    }
                                )
                            }
                        }
                    ]
                }
            ),
        ]
        progress_events: list[tuple[str, dict[str, object]]] = []

        with patch("app.services.model_provider.litellm_completion", side_effect=responses) as mocked_completion:
            reply = provider.generate_learning_plan(
                persona=persona,
                document_title="Discrete Mathematics",
                goal=goal,
                study_units=[
                    StudyUnitRecord(
                        id="unit-1",
                        document_id="doc-1",
                        title="Chapter 1 Foundations",
                        page_start=1,
                        page_end=18,
                        source_section_ids=["raw-1"],
                        summary="聚焦集合与命题逻辑。",
                        confidence=0.9,
                    )
                ],
                debug_report=debug_report,
            )

        first_payload = mocked_completion.call_args_list[0].kwargs
        second_payload = mocked_completion.call_args_list[1].kwargs
        self.assertIn("tools", first_payload)
        self.assertIn(
            "get_study_unit_detail",
            [tool["function"]["name"] for tool in first_payload["tools"]],
        )
        self.assertIn(
            "read_page_range_content",
            [tool["function"]["name"] for tool in first_payload["tools"]],
        )
        tool_messages = [message for message in second_payload["messages"] if message["role"] == "tool"]
        self.assertEqual(len(tool_messages), 2)
        self.assertIn("extensionality", tool_messages[0]["content"])
        self.assertIn("membership", tool_messages[1]["content"])
        self.assertIsNotNone(reply.debug_trace)
        self.assertEqual(reply.debug_trace.model, "gpt-test")
        self.assertEqual(len(reply.debug_trace.rounds), 2)
        self.assertIn("inspect the subsection structure", reply.debug_trace.rounds[0].thinking)
        self.assertGreaterEqual(reply.debug_trace.rounds[0].elapsed_ms, 0)
        self.assertEqual(reply.debug_trace.rounds[0].timeout_seconds, 3)
        self.assertEqual(len(reply.debug_trace.rounds[0].tool_calls), 2)
        self.assertIn("enough evidence", reply.debug_trace.rounds[1].thinking)
        self.assertEqual(reply.course_title, "Discrete Mathematics / Chapter 1 Foundations")
        self.assertEqual(reply.overview, "Tool-assisted plan overview")
        self.assertEqual(reply.schedule[0].unit_id, "unit-1")

    def test_openai_provider_retries_same_context_after_plan_content_filter(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        goal = LearningGoalInput(
            document_id="doc-1",
            persona_id=persona.id,
            objective="掌握第一章",
        )
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            timeout_seconds=3,
        )
        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-1",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 18,
                "total_characters": 2000,
                "extraction_method": "ocr",
                "ocr_applied": True,
                "ocr_language": "eng",
                "pages": [],
                "sections": [
                    {
                        "id": "raw-1",
                        "document_id": "doc-1",
                        "title": "Chapter 1 Foundations",
                        "page_start": 1,
                        "page_end": 18,
                        "level": 1,
                    }
                ],
                "study_units": [],
                "chunks": [
                    {
                        "id": "chunk-1",
                        "document_id": "doc-1",
                        "section_id": "raw-1",
                        "page_start": 1,
                        "page_end": 3,
                        "char_count": 320,
                        "text_preview": "Sets, subsets, and membership.",
                        "content": "Sets, subsets, membership, extensionality, and simple examples.",
                    }
                ],
                "warnings": [],
                "dominant_language_hint": "en",
            }
        )

        responses = [
            FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call-1",
                                        "type": "function",
                                        "function": {
                                            "name": "read_page_range_content",
                                            "arguments": json.dumps(
                                                {
                                                    "page_start": 1,
                                                    "page_end": 3,
                                                    "max_chars": 1200,
                                                }
                                            ),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ]
                }
            ),
            FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                            },
                            "finish_reason": "content_filter",
                        }
                    ]
                }
            ),
            FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "course_title": "Discrete Mathematics / Chapter 1 Foundations",
                                        "overview": "Recovered after transparent regeneration.",
                                        "study_chapters": ["Chapter 1 Foundations"],
                                        "today_tasks": ["Read sets and extensionality."],
                                        "schedule": [
                                            {
                                                "unit_id": "unit-1",
                                                "title": "Chapter 1 Foundations 精读",
                                                "focus": "Cover sets, subsets, and extensionality.",
                                                "activity_type": "learn",
                                            }
                                        ],
                                    }
                                )
                            },
                            "finish_reason": "stop",
                        }
                    ]
                }
            ),
        ]
        progress_events: list[tuple[str, dict[str, object]]] = []

        with patch("app.services.model_provider.litellm_completion", side_effect=responses) as mocked_completion:
            reply = provider.generate_learning_plan(
                persona=persona,
                document_title="Discrete Mathematics",
                goal=goal,
                study_units=[
                    StudyUnitRecord(
                        id="unit-1",
                        document_id="doc-1",
                        title="Chapter 1 Foundations",
                        page_start=1,
                        page_end=18,
                        source_section_ids=["raw-1"],
                        summary="聚焦集合与命题逻辑。",
                        confidence=0.9,
                    )
                ],
                debug_report=debug_report,
                progress_callback=lambda stage, payload: progress_events.append((stage, payload)),
            )

        second_payload = mocked_completion.call_args_list[1].kwargs
        third_payload = mocked_completion.call_args_list[2].kwargs
        started_round_indexes = [
            int(payload["round_index"])
            for stage, payload in progress_events
            if stage == "model_round_started"
        ]
        self.assertEqual(second_payload["messages"], third_payload["messages"])
        self.assertEqual(started_round_indexes, [0, 1, 1])
        self.assertEqual([round_record.round_index for round_record in reply.debug_trace.rounds], [0, 1])
        self.assertEqual(reply.overview, "Recovered after transparent regeneration.")
        self.assertEqual(reply.schedule[0].unit_id, "unit-1")

    def test_openai_provider_can_revise_study_units_before_planning(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        goal = LearningGoalInput(
            document_id="doc-1",
            persona_id=persona.id,
            objective="纠正章节划分",
        )
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            timeout_seconds=3,
        )
        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-1",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 20,
                "total_characters": 2000,
                "extraction_method": "ocr",
                "ocr_applied": True,
                "ocr_language": "eng",
                "pages": [],
                "sections": [
                    {
                        "id": "raw-1",
                        "document_id": "doc-1",
                        "title": "Chapter 1",
                        "page_start": 1,
                        "page_end": 10,
                        "level": 1,
                    },
                    {
                        "id": "raw-2",
                        "document_id": "doc-1",
                        "title": "Chapter 2",
                        "page_start": 11,
                        "page_end": 20,
                        "level": 1,
                    },
                ],
                "study_units": [],
                "chunks": [],
                "warnings": [],
                "dominant_language_hint": "en",
            }
        )

        responses = [
            FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call-revise-1",
                                        "type": "function",
                                        "function": {
                                            "name": "revise_study_units",
                                            "arguments": json.dumps(
                                                {
                                                    "study_units": [
                                                        {
                                                            "title": "Chapter 1 Foundations",
                                                            "page_start": 1,
                                                            "page_end": 10,
                                                        },
                                                        {
                                                            "title": "Chapter 2 Practice",
                                                            "page_start": 11,
                                                            "page_end": 20,
                                                        },
                                                    ]
                                                }
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ),
            FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "course_title": "Discrete Mathematics / Revised",
                                        "overview": "Use the revised segmentation.",
                                        "study_chapters": ["Chapter 1 Foundations", "Chapter 2 Practice"],
                                        "today_tasks": ["Start with the corrected first chapter."],
                                        "schedule": [
                                            {
                                                "unit_id": "doc-1:study-unit:llm:1",
                                                "title": "Chapter 1 Foundations 精读",
                                                "focus": "Study the corrected first chapter.",
                                                "activity_type": "learn",
                                            }
                                        ],
                                    }
                                )
                            }
                        }
                    ]
                }
            ),
        ]

        with patch("app.services.model_provider.litellm_completion", side_effect=responses):
            reply = provider.generate_learning_plan(
                persona=persona,
                document_title="Discrete Mathematics",
                goal=goal,
                study_units=[
                    StudyUnitRecord(
                        id="unit-1",
                        document_id="doc-1",
                        title="Wrong Combined Unit",
                        page_start=1,
                        page_end=20,
                        summary="旧划分。",
                        confidence=0.7,
                    )
                ],
                debug_report=debug_report,
            )

        self.assertIsNotNone(reply.revised_study_units)
        self.assertEqual(
            [unit.id for unit in reply.revised_study_units or []],
            ["doc-1:study-unit:llm:1", "doc-1:study-unit:llm:2"],
        )
        self.assertEqual(reply.schedule[0].unit_id, "doc-1:study-unit:llm:1")

    def test_openai_provider_multimodal_tool_call_appends_page_images(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        goal = LearningGoalInput(
            document_id="doc-1",
            persona_id=persona.id,
            objective="理解图表与公式",
        )
        provider = OpenAIModelProvider(
            api_key="test-key",
            base_url="https://api.openai.test/v1",
            plan_model="gpt-test",
            timeout_seconds=3,
            multimodal_enabled=True,
        )

        responses = [
            FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": "",
                                "tool_calls": [
                                    {
                                        "id": "call-image-1",
                                        "type": "function",
                                        "function": {
                                            "name": "read_page_range_images",
                                            "arguments": json.dumps(
                                                {
                                                    "page_start": 2,
                                                    "page_end": 2,
                                                    "max_images": 1,
                                                }
                                            ),
                                        },
                                    }
                                ],
                            }
                        }
                    ]
                }
            ),
            FakeLiteLLMResult(
                {
                    "choices": [
                        {
                            "message": {
                                "content": json.dumps(
                                    {
                                        "course_title": "Physics / Chapter 2 Graphs",
                                        "overview": "Use the page image to understand the diagram-heavy unit.",
                                        "study_chapters": ["Chapter 2 Graphs"],
                                        "today_tasks": ["Inspect the textbook figure and summarize it."],
                                        "schedule": [
                                            {
                                                "unit_id": "unit-graph",
                                                "title": "Chapter 2 Graphs 精读",
                                                "focus": "Interpret the chart and connect it with the surrounding explanation.",
                                                "activity_type": "learn",
                                            }
                                        ],
                                    }
                                )
                            }
                        }
                    ]
                }
            ),
        ]

        with (
            patch("app.services.model_provider.litellm_completion", side_effect=responses) as mocked_completion,
            patch(
                "app.services.plan_tool_runtime.read_page_range_images",
                return_value={
                    "page_start": 2,
                    "page_end": 2,
                    "image_count": 1,
                    "images": [
                        {
                            "page_number": 2,
                            "mime_type": "image/png",
                            "image_url": "data:image/png;base64,AAA",
                        }
                    ],
                },
            ),
        ):
            reply = provider.generate_learning_plan(
                persona=persona,
                document_title="Physics",
                goal=goal,
                study_units=[
                    StudyUnitRecord(
                        id="unit-graph",
                        document_id="doc-1",
                        title="Chapter 2 Graphs",
                        page_start=2,
                        page_end=4,
                        summary="聚焦图表与相关解释。",
                        confidence=0.8,
                    )
                ],
                document_path="/tmp/physics.pdf",
            )

        first_payload = mocked_completion.call_args_list[0].kwargs
        second_payload = mocked_completion.call_args_list[1].kwargs
        self.assertIn(
            "read_page_range_images",
            [tool["function"]["name"] for tool in first_payload["tools"]],
        )
        image_follow_up_messages = [
            message
            for message in second_payload["messages"]
            if message["role"] == "user" and isinstance(message["content"], list)
        ]
        self.assertEqual(len(image_follow_up_messages), 1)
        self.assertEqual(image_follow_up_messages[0]["content"][1]["type"], "image_url")
        self.assertEqual(
            image_follow_up_messages[0]["content"][1]["image_url"]["url"],
            "data:image/png;base64,AAA",
        )
        tool_messages = [message for message in second_payload["messages"] if message["role"] == "tool"]
        self.assertEqual(tool_messages[0]["name"], "read_page_range_images")
        self.assertIn('"page_numbers": [2]', tool_messages[0]["content"])
        self.assertEqual(reply.schedule[0].unit_id, "unit-graph")

    def test_read_page_range_content_joins_overlapping_chunks(self) -> None:
        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-1",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 20,
                "total_characters": 1200,
                "extraction_method": "ocr",
                "ocr_applied": True,
                "ocr_language": "eng",
                "pages": [],
                "sections": [],
                "study_units": [],
                "chunks": [
                    {
                        "id": "chunk-1",
                        "document_id": "doc-1",
                        "section_id": "raw-1",
                        "page_start": 2,
                        "page_end": 3,
                        "char_count": 200,
                        "text_preview": "first preview",
                        "content": "First detailed excerpt.",
                    },
                    {
                        "id": "chunk-2",
                        "document_id": "doc-1",
                        "section_id": "raw-1",
                        "page_start": 4,
                        "page_end": 5,
                        "char_count": 200,
                        "text_preview": "second preview",
                        "content": "Second detailed excerpt.",
                    },
                ],
                "warnings": [],
                "dominant_language_hint": "en",
            }
        )

        content = read_page_range_content(
            debug_report=debug_report,
            page_start=3,
            page_end=4,
            max_chars=1000,
        )

        self.assertEqual(content["chunk_count"], 2)
        self.assertIn("First detailed excerpt.", content["content"])
        self.assertIn("Second detailed excerpt.", content["content"])

    def test_route_maps_rate_limit_to_service_unavailable(self) -> None:
        error = _map_plan_generation_error(RuntimeError("openai_plan_request_rate_limit"))

        self.assertIsInstance(error, HTTPException)
        self.assertEqual(error.status_code, 503)
        self.assertEqual(error.detail, "plan_model_rate_limited")

    def test_route_maps_network_error_to_bad_gateway(self) -> None:
        error = _map_plan_generation_error(RuntimeError("openai_plan_request_network_error"))

        self.assertEqual(error.status_code, 502)
        self.assertEqual(error.detail, "plan_model_network_error")

    def test_route_maps_timeout_to_gateway_timeout(self) -> None:
        error = _map_plan_generation_error(RuntimeError("openai_plan_request_timeout"))

        self.assertEqual(error.status_code, 504)
        self.assertEqual(error.detail, "plan_model_timeout")

    def test_route_maps_upstream_plan_error_to_bad_gateway(self) -> None:
        error = _map_plan_generation_error(
            RuntimeError("openai_plan_request_failed:500:rate_limit")
        )

        self.assertEqual(error.status_code, 502)
        self.assertEqual(error.detail, "plan_model_upstream_error:500:rate_limit")

    def test_route_maps_upstream_chat_error_with_detail(self) -> None:
        error = _map_chat_generation_error(RuntimeError("openai_chat_request_failed:503:overloaded"))

        self.assertEqual(error.status_code, 502)
        self.assertEqual(error.detail, "chat_model_upstream_error:503:overloaded")

    def test_route_maps_upstream_setting_error_with_detail(self) -> None:
        error = _map_setting_generation_error(
            RuntimeError("openai_setting_request_failed:401:invalid_api_key")
        )

        self.assertEqual(error.status_code, 502)
        self.assertEqual(error.detail, "setting_model_upstream_error:401:invalid_api_key")

    def test_plan_service_uses_model_provider_output_for_plan(self) -> None:
        arrangement_service = StudyArrangementService()
        store = LocalJsonStore(Path(self.temp_dir.name) / "plan-provider-case")
        provider = MockModelProvider()
        service = LearningPlanService(store, arrangement_service, provider)
        persona = self.persona_engine.require_persona("mentor-aurora")
        document = DocumentResponse.model_validate(
            {
                "id": "doc-plan",
                "title": "Linear Algebra",
                "original_filename": "linear-algebra.pdf",
                "stored_path": "/tmp/linear.pdf",
                "status": "processed",
                "ocr_status": "completed",
                "created_at": "2026-04-09T00:00:00+00:00",
                "updated_at": "2026-04-09T00:00:00+00:00",
                "sections": [
                    {
                        "id": "doc-plan:study-unit:1",
                        "document_id": "doc-plan",
                        "title": "Chapter 1 Vectors",
                        "page_start": 1,
                        "page_end": 20,
                        "level": 1,
                    }
                ],
                "study_units": [
                    {
                        "id": "doc-plan:study-unit:1",
                        "document_id": "doc-plan",
                        "title": "Chapter 1 Vectors",
                        "page_start": 1,
                        "page_end": 20,
                        "unit_kind": "chapter",
                        "include_in_plan": True,
                        "source_section_ids": ["raw-1"],
                        "summary": "聚焦向量基础。",
                        "confidence": 0.9,
                    }
                ],
                "study_unit_count": 1,
                "page_count": 20,
                "chunk_count": 5,
                "preview_excerpt": "sample",
                "debug_ready": True,
            }
        )

        with patch.object(
            provider,
            "generate_learning_plan",
            return_value=PlanModelReply(
                course_title="Linear Algebra / Chapter 1 Vectors",
                overview="Model-crafted overview",
                study_chapters=["Chapter 1 Vectors"],
                today_tasks=["完成向量定义与例题梳理。"],
                schedule=[
                    PlanScheduleItem(
                        unit_id="doc-plan:study-unit:1",
                        title="Chapter 1 Vectors 精读",
                        focus="完成向量定义与例题梳理。",
                        activity_type="learn",
                    )
                ],
            ),
        ) as mocked_plan_call:
            plan = service.create_plan(
                goal=LearningGoalInput(
                    document_id=document.id,
                    persona_id=persona.id,
                    objective="掌握向量基础",
                ),
                document=document,
                persona_name=persona.name,
                persona=persona,
            )

        mocked_plan_call.assert_called_once()
        self.assertEqual(plan.course_title, "Linear Algebra / Chapter 1 Vectors")
        self.assertEqual(plan.overview, "Model-crafted overview")
        self.assertEqual(plan.schedule[0].title, "Chapter 1 Vectors 精读")

    def test_plan_service_persists_model_revised_study_units(self) -> None:
        arrangement_service = StudyArrangementService()
        store = LocalJsonStore(Path(self.temp_dir.name) / "plan-revision-case")
        provider = MockModelProvider()
        service = LearningPlanService(store, arrangement_service, provider)
        persona = self.persona_engine.require_persona("mentor-aurora")
        document = DocumentResponse.model_validate(
            {
                "id": "doc-revise",
                "title": "Discrete Mathematics",
                "original_filename": "discrete.pdf",
                "stored_path": "/tmp/discrete.pdf",
                "status": "processed",
                "ocr_status": "completed",
                "created_at": "2026-04-09T00:00:00+00:00",
                "updated_at": "2026-04-09T00:00:00+00:00",
                "sections": [],
                "study_units": [
                    {
                        "id": "doc-revise:study-unit:1",
                        "document_id": "doc-revise",
                        "title": "Wrong Combined Unit",
                        "page_start": 1,
                        "page_end": 20,
                        "unit_kind": "chapter",
                        "include_in_plan": True,
                        "source_section_ids": ["raw-1"],
                        "summary": "旧划分。",
                        "confidence": 0.7,
                    }
                ],
                "study_unit_count": 1,
                "page_count": 20,
                "chunk_count": 5,
                "preview_excerpt": "sample",
                "debug_ready": True,
            }
        )
        store.save_list("documents", [document])
        debug_report = DocumentDebugRecord.model_validate(
            {
                "document_id": "doc-revise",
                "parser_name": "parser",
                "processed_at": "2026-04-09T00:00:00+00:00",
                "page_count": 20,
                "total_characters": 2000,
                "extraction_method": "text",
                "ocr_applied": False,
                "pages": [],
                "sections": [],
                "study_units": document.study_units,
                "chunks": [],
                "warnings": [],
                "dominant_language_hint": "en",
            }
        )

        with patch.object(
            provider,
            "generate_learning_plan",
            return_value=PlanModelReply(
                course_title="Discrete Mathematics / Revised",
                overview="Model-crafted revised overview",
                study_chapters=["Chapter 1 Foundations", "Chapter 2 Practice"],
                today_tasks=["从修正后的第一章开始。"],
                schedule=[
                    PlanScheduleItem(
                        unit_id="doc-revise:study-unit:llm:1",
                        title="Chapter 1 Foundations 精读",
                        focus="修正后的第一章。",
                        activity_type="learn",
                    )
                ],
                revised_study_units=[
                    StudyUnitRecord(
                        id="doc-revise:study-unit:llm:1",
                        document_id="doc-revise",
                        title="Chapter 1 Foundations",
                        page_start=1,
                        page_end=10,
                        summary="第一章",
                        confidence=0.95,
                    ),
                    StudyUnitRecord(
                        id="doc-revise:study-unit:llm:2",
                        document_id="doc-revise",
                        title="Chapter 2 Practice",
                        page_start=11,
                        page_end=20,
                        summary="第二章",
                        confidence=0.95,
                    ),
                ],
            ),
        ):
            plan = service.create_plan(
                goal=LearningGoalInput(
                    document_id=document.id,
                    persona_id=persona.id,
                    objective="纠正章节划分",
                ),
                document=document,
                persona_name=persona.name,
                persona=persona,
                debug_report=debug_report,
            )

        saved_document = store.load_list("documents", DocumentResponse)[0]
        saved_debug = store.load_item("document_debug", "doc-revise", DocumentDebugRecord)
        self.assertEqual([unit.id for unit in plan.study_units], ["doc-revise:study-unit:llm:1", "doc-revise:study-unit:llm:2"])
        self.assertEqual(plan.schedule[0].unit_id, "doc-revise:study-unit:llm:1")
        self.assertEqual(saved_document.sections[0].id, "doc-revise:study-unit:llm:1")
        self.assertIsNotNone(saved_debug)
        self.assertEqual(saved_debug.study_units[1].id, "doc-revise:study-unit:llm:2")


    def test_plan_service_updates_plan_title(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        document = DocumentResponse.model_validate(
            {
                "id": "doc-update-plan",
                "title": "Calculus",
                "original_filename": "calculus.pdf",
                "stored_path": "/tmp/calculus.pdf",
                "status": "processed",
                "ocr_status": "completed",
                "created_at": "2026-04-09T00:00:00+00:00",
                "updated_at": "2026-04-09T00:00:00+00:00",
                "sections": [
                    {
                        "id": "doc-update-plan:study-unit:1",
                        "document_id": "doc-update-plan",
                        "title": "Limits",
                        "page_start": 1,
                        "page_end": 12,
                        "level": 1,
                    }
                ],
                "study_units": [
                    {
                        "id": "doc-update-plan:study-unit:1",
                        "document_id": "doc-update-plan",
                        "title": "Limits",
                        "page_start": 1,
                        "page_end": 12,
                        "unit_kind": "chapter",
                        "include_in_plan": True,
                        "source_section_ids": ["raw-1"],
                        "summary": "极限基础。",
                        "confidence": 0.92,
                    }
                ],
                "study_unit_count": 1,
                "page_count": 12,
                "chunk_count": 3,
                "preview_excerpt": "sample",
                "debug_ready": True,
            }
        )

        plan = self.plan_service.create_plan(
            goal=LearningGoalInput(
                document_id=document.id,
                persona_id=persona.id,
                objective="掌握极限",
            ),
            document=document,
            persona_name=persona.name,
            persona=persona,
        )

        updated = self.plan_service.update_plan(
            plan_id=plan.id,
            course_title="Calculus / Limits Sprint",
        )

        self.assertEqual(updated.course_title, "Calculus / Limits Sprint")
        persisted = self.plan_service.require_plan(plan.id)
        self.assertEqual(persisted.course_title, "Calculus / Limits Sprint")

    def test_plan_service_updates_study_chapters(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        document = DocumentResponse.model_validate(
            {
                "id": "doc-update-focus",
                "title": "Geometry",
                "original_filename": "geometry.pdf",
                "stored_path": "/tmp/geometry.pdf",
                "status": "processed",
                "ocr_status": "completed",
                "created_at": "2026-04-09T00:00:00+00:00",
                "updated_at": "2026-04-09T00:00:00+00:00",
                "sections": [
                    {
                        "id": "doc-update-focus:study-unit:1",
                        "document_id": "doc-update-focus",
                        "title": "Triangles",
                        "page_start": 1,
                        "page_end": 18,
                        "level": 1,
                    }
                ],
                "study_units": [
                    {
                        "id": "doc-update-focus:study-unit:1",
                        "document_id": "doc-update-focus",
                        "title": "Triangles",
                        "page_start": 1,
                        "page_end": 18,
                        "unit_kind": "chapter",
                        "include_in_plan": True,
                        "source_section_ids": ["raw-1"],
                        "summary": "三角形基础。",
                        "confidence": 0.92,
                    }
                ],
                "study_unit_count": 1,
                "page_count": 18,
                "chunk_count": 3,
                "preview_excerpt": "sample",
                "debug_ready": True,
            }
        )

        plan = self.plan_service.create_plan(
            goal=LearningGoalInput(
                document_id=document.id,
                persona_id=persona.id,
                objective="掌握三角形基础",
            ),
            document=document,
            persona_name=persona.name,
            persona=persona,
        )

        updated = self.plan_service.update_plan(
            plan_id=plan.id,
            study_chapters=["图形基础", "三角形证明"],
        )

        self.assertEqual(updated.study_chapters, ["图形基础", "三角形证明"])
        persisted = self.plan_service.require_plan(plan.id)
        self.assertEqual(persisted.study_chapters, ["图形基础", "三角形证明"])

    def test_plan_service_can_create_goal_only_plan(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")

        plan = self.plan_service.create_plan(
            goal=LearningGoalInput(
                document_id="",
                persona_id=persona.id,
                objective="先掌握极限的定义，再补上左右极限与连续性的联系",
            ),
            document=None,
            persona_name=persona.name,
            persona=persona,
        )

        self.assertEqual(plan.creation_mode, "goal_only")
        self.assertEqual(plan.document_id, "")
        self.assertGreaterEqual(len(plan.study_units), 3)
        self.assertTrue(plan.schedule)
        self.assertEqual(plan.progress_summary.total_schedule_count, len(plan.schedule))

    def test_plan_service_updates_progress_summary_and_events(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        document = DocumentResponse.model_validate(
            {
                "id": "doc-progress-plan",
                "title": "Statistics",
                "original_filename": "statistics.pdf",
                "stored_path": "/tmp/statistics.pdf",
                "status": "processed",
                "ocr_status": "completed",
                "created_at": "2026-04-09T00:00:00+00:00",
                "updated_at": "2026-04-09T00:00:00+00:00",
                "sections": [],
                "study_units": [
                    {
                        "id": "doc-progress-plan:study-unit:1",
                        "document_id": "doc-progress-plan",
                        "title": "Distributions",
                        "page_start": 1,
                        "page_end": 16,
                        "unit_kind": "chapter",
                        "include_in_plan": True,
                        "source_section_ids": [],
                        "summary": "分布概念。",
                        "confidence": 0.9,
                    }
                ],
                "study_unit_count": 1,
                "page_count": 16,
                "chunk_count": 4,
                "preview_excerpt": "sample",
                "debug_ready": True,
            }
        )

        plan = self.plan_service.create_plan(
            goal=LearningGoalInput(
                document_id=document.id,
                persona_id=persona.id,
                objective="理解离散分布",
            ),
            document=document,
            persona_name=persona.name,
            persona=persona,
        )

        updated = self.plan_service.update_progress(
            plan_id=plan.id,
            schedule_ids=[plan.schedule[0].id],
            status="completed",
            note="Learner finished the first reading cycle.",
            actor="user",
            source="ui",
        )

        self.assertEqual(updated.schedule[0].status, "completed")
        self.assertEqual(updated.progress_summary.completed_schedule_count, 1)
        self.assertGreaterEqual(updated.progress_summary.completion_percent, 50)
        self.assertEqual(updated.progress_events[-1].actor, "user")
        self.assertEqual(updated.progress_events[-1].source, "ui")

    def test_plan_service_persists_planning_questions_from_model(self) -> None:
        arrangement_service = StudyArrangementService()
        store = LocalJsonStore(Path(self.temp_dir.name) / "plan-question-case")
        provider = MockModelProvider()
        service = LearningPlanService(store, arrangement_service, provider)
        persona = self.persona_engine.require_persona("mentor-aurora")
        document = DocumentResponse.model_validate(
            {
                "id": "doc-question-plan",
                "title": "Calculus",
                "original_filename": "calculus.pdf",
                "stored_path": "/tmp/calculus.pdf",
                "status": "processed",
                "ocr_status": "completed",
                "created_at": "2026-04-09T00:00:00+00:00",
                "updated_at": "2026-04-09T00:00:00+00:00",
                "sections": [],
                "study_units": [
                    {
                        "id": "doc-question-plan:study-unit:1",
                        "document_id": "doc-question-plan",
                        "title": "Limits",
                        "page_start": 1,
                        "page_end": 10,
                        "unit_kind": "chapter",
                        "include_in_plan": True,
                        "source_section_ids": [],
                        "summary": "极限基础。",
                        "confidence": 0.9,
                    }
                ],
                "study_unit_count": 1,
                "page_count": 10,
                "chunk_count": 3,
                "preview_excerpt": "sample",
                "debug_ready": True,
            }
        )

        with patch.object(
            provider,
            "generate_learning_plan",
            return_value=PlanModelReply(
                course_title="Calculus / Limits",
                overview="Need one clarification.",
                study_chapters=["Limits"],
                today_tasks=["Clarify the learner preference."],
                schedule=[],
                planning_questions=[
                    PlanningQuestionRecord(
                        id="planning-question-1",
                        question="这次更偏向概念打底还是刷题提分？",
                        reason="学习目标需要进一步聚焦。",
                        assumptions=["先按概念打底推进。"],
                        created_at="2026-04-09T00:00:00+00:00",
                    )
                ],
            ),
        ):
            plan = service.create_plan(
                goal=LearningGoalInput(
                    document_id=document.id,
                    persona_id=persona.id,
                    objective="掌握极限",
                ),
                document=document,
                persona_name=persona.name,
                persona=persona,
            )

        self.assertEqual(len(plan.planning_questions), 1)
        self.assertEqual(plan.planning_questions[0].status, "pending")
        persisted = service.require_plan(plan.id)
        self.assertEqual(persisted.planning_questions[0].question, "这次更偏向概念打底还是刷题提分？")

    def test_learning_plan_chat_tool_runtime_updates_progress(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        document = DocumentResponse.model_validate(
            {
                "id": "doc-plan-runtime",
                "title": "Algebra",
                "original_filename": "algebra.pdf",
                "stored_path": "/tmp/algebra.pdf",
                "status": "processed",
                "ocr_status": "completed",
                "created_at": "2026-04-09T00:00:00+00:00",
                "updated_at": "2026-04-09T00:00:00+00:00",
                "sections": [],
                "study_units": [
                    {
                        "id": "doc-plan-runtime:study-unit:1",
                        "document_id": "doc-plan-runtime",
                        "title": "Matrices",
                        "page_start": 1,
                        "page_end": 12,
                        "unit_kind": "chapter",
                        "include_in_plan": True,
                        "source_section_ids": [],
                        "summary": "矩阵基础。",
                        "confidence": 0.9,
                    }
                ],
                "study_unit_count": 1,
                "page_count": 12,
                "chunk_count": 3,
                "preview_excerpt": "sample",
                "debug_ready": True,
            }
        )

        plan = self.plan_service.create_plan(
            goal=LearningGoalInput(
                document_id=document.id,
                persona_id=persona.id,
                objective="掌握矩阵基础",
            ),
            document=document,
            persona_name=persona.name,
            persona=persona,
        )

        runtime = LearningPlanChatToolRuntime(self.plan_service, plan.id)
        payload = runtime.execute_tool(
            "update_learning_plan_progress",
            {
                "schedule_id": plan.schedule[0].id,
                "status": "completed",
                "note": "The learner finished the first task.",
            },
        )

        self.assertEqual(payload["tool_name"], "update_learning_plan_progress")
        self.assertEqual(payload["progress_summary"]["completed_schedule_count"], 1)
        refreshed = self.plan_service.require_plan(plan.id)
        self.assertEqual(refreshed.schedule[0].status, "completed")

    def test_plan_service_deletes_plan(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        document = DocumentResponse.model_validate(
            {
                "id": "doc-delete-plan",
                "title": "Probability",
                "original_filename": "probability.pdf",
                "stored_path": "/tmp/probability.pdf",
                "status": "processed",
                "ocr_status": "completed",
                "created_at": "2026-04-09T00:00:00+00:00",
                "updated_at": "2026-04-09T00:00:00+00:00",
                "sections": [
                    {
                        "id": "doc-delete-plan:study-unit:1",
                        "document_id": "doc-delete-plan",
                        "title": "Random Variables",
                        "page_start": 1,
                        "page_end": 15,
                        "level": 1,
                    }
                ],
                "study_units": [
                    {
                        "id": "doc-delete-plan:study-unit:1",
                        "document_id": "doc-delete-plan",
                        "title": "Random Variables",
                        "page_start": 1,
                        "page_end": 15,
                        "unit_kind": "chapter",
                        "include_in_plan": True,
                        "source_section_ids": ["raw-1"],
                        "summary": "随机变量基础。",
                        "confidence": 0.9,
                    }
                ],
                "study_unit_count": 1,
                "page_count": 15,
                "chunk_count": 4,
                "preview_excerpt": "sample",
                "debug_ready": True,
            }
        )

        plan = self.plan_service.create_plan(
            goal=LearningGoalInput(
                document_id=document.id,
                persona_id=persona.id,
                objective="理解随机变量",
            ),
            document=document,
            persona_name=persona.name,
            persona=persona,
        )

        self.plan_service.delete_plan(plan.id)

        self.assertFalse(any(saved_plan.id == plan.id for saved_plan in self.plan_service.list_plans()))
        with self.assertRaises(HTTPException) as context:
            self.plan_service.require_plan(plan.id)
        self.assertEqual(context.exception.status_code, 404)

    def test_study_unit_title_update_syncs_document_debug_and_plans(self) -> None:
        persona = self.persona_engine.require_persona("mentor-aurora")
        document = DocumentResponse.model_validate(
            {
                "id": "doc-unit-rename",
                "title": "Mechanics",
                "original_filename": "mechanics.pdf",
                "stored_path": "/tmp/mechanics.pdf",
                "status": "processed",
                "ocr_status": "completed",
                "created_at": "2026-04-09T00:00:00+00:00",
                "updated_at": "2026-04-09T00:00:00+00:00",
                "sections": [
                    {
                        "id": "doc-unit-rename:study-unit:1",
                        "document_id": "doc-unit-rename",
                        "title": "Vectors",
                        "page_start": 1,
                        "page_end": 16,
                        "level": 1,
                    }
                ],
                "study_units": [
                    {
                        "id": "doc-unit-rename:study-unit:1",
                        "document_id": "doc-unit-rename",
                        "title": "Vectors",
                        "page_start": 1,
                        "page_end": 16,
                        "unit_kind": "chapter",
                        "include_in_plan": True,
                        "source_section_ids": ["raw-1"],
                        "summary": "向量基础。",
                        "confidence": 0.91,
                    }
                ],
                "study_unit_count": 1,
                "page_count": 16,
                "chunk_count": 4,
                "preview_excerpt": "sample",
                "debug_ready": True,
            }
        )
        self.document_service.store.save_list("documents", [document])
        self.document_service.store.save_item(
            "document_debug",
            document.id,
            DocumentDebugRecord.model_validate(
                {
                    "document_id": document.id,
                    "parser_name": "parser",
                    "processed_at": "2026-04-09T00:00:00+00:00",
                    "page_count": 16,
                    "total_characters": 1600,
                    "extraction_method": "text",
                    "ocr_applied": False,
                    "pages": [],
                    "sections": [],
                    "study_units": document.study_units,
                    "chunks": [],
                    "warnings": [],
                    "dominant_language_hint": "en",
                }
            ),
        )

        plan = self.plan_service.create_plan(
            goal=LearningGoalInput(
                document_id=document.id,
                persona_id=persona.id,
                objective="理解向量",
            ),
            document=document,
            persona_name=persona.name,
            persona=persona,
        )

        updated_document = self.document_service.update_study_unit_title(
            document_id=document.id,
            study_unit_id="doc-unit-rename:study-unit:1",
            title="Vector Foundations",
        )
        updated_plans = self.plan_service.update_study_unit_title(
            document_id=document.id,
            study_unit_id="doc-unit-rename:study-unit:1",
            title="Vector Foundations",
        )

        self.assertEqual(updated_document.study_units[0].title, "Vector Foundations")
        self.assertEqual(updated_document.sections[0].title, "Vector Foundations")
        self.assertEqual(updated_plans[0].id, plan.id)
        self.assertEqual(updated_plans[0].study_units[0].title, "Vector Foundations")

        saved_document = self.document_service.require_document(document.id)
        saved_debug = self.document_service.require_debug_report(document.id)
        saved_plan = self.plan_service.require_plan(plan.id)

        self.assertEqual(saved_document.study_units[0].title, "Vector Foundations")
        self.assertEqual(saved_debug.study_units[0].title, "Vector Foundations")
        self.assertEqual(saved_plan.study_units[0].title, "Vector Foundations")


if __name__ == "__main__":
    unittest.main()
