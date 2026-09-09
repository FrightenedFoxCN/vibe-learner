from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from app.models.api import CreatePersonaRequest
from app.models.domain import (
    PersonaProfile,
    SceneLayerStateRecord,
    SceneProfileRecord,
)
from app.models.harness import HarnessStatus, HarnessTraceRecord
from app.models.tavern import (
    CreateTavernRoomRequest,
    TavernActorReply,
    TavernAuthorKind,
    TavernHarnessPolicy,
    TavernMessageRecord,
    TavernParticipantRecord,
    TavernTurnRequest,
)
from app.models.tavern_integrity import persona_prompt_hash
from app.persistence.database import Database
from app.persistence.storage import StorageManager
from app.persistence.tavern_repository import TavernRepository
from app.services.local_store import LocalJsonStore
from app.services.model_provider import MockModelProvider
from app.services.persona import PersonaEngine
from app.services.tavern import TavernService
from app.services.tavern_harness import (
    TAVERN_SPEAKER_IDENTITY_POLICY_VERSION,
    TavernActorHarness,
    TavernHarnessViolation,
    build_speaker_identity_markers,
    find_cross_speaker_impersonation,
)
from app.services.tavern_prompt import (
    TAVERN_PROMPT_MAX_CANONICAL_BYTES,
    TAVERN_PROMPT_MAX_CAST_BYTES,
    TAVERN_PROMPT_MAX_INPUT_TOKEN_ESTIMATE,
    TAVERN_PROMPT_MAX_PERSONA_INSTRUCTION_BYTES,
    TAVERN_PROMPT_MAX_SCENE_BYTES,
    TAVERN_PROMPT_MAX_SCENE_DEPTH,
    TAVERN_PROMPT_MAX_TRANSCRIPT_BYTES,
    TavernPromptBudgetError,
    _require_partition_bytes,
    preflight_tavern_actor_prompt,
)


NOW = "2026-08-25T00:00:00+00:00"


def _persona(
    persona_id: str,
    name: str,
    *,
    summary: str = "",
    system_prompt: str = "保持角色身份稳定。",
) -> PersonaProfile:
    return PersonaProfile(
        id=persona_id,
        name=name,
        source="user",
        summary=summary or f"{name} 的角色摘要",
        relationship="同行者",
        learner_address="你",
        system_prompt=system_prompt,
        reference_hints=[],
        slots=[],
        available_emotions=["calm"],
        available_actions=["pause"],
        default_speech_style="warm",
    )


def _participant(
    persona: PersonaProfile,
    *,
    display_order: int,
    room_id: str = "room-1",
) -> TavernParticipantRecord:
    return TavernParticipantRecord(
        room_id=room_id,
        persona_id=persona.id,
        display_order=display_order,
        display_name=persona.name,
        persona_snapshot=persona,
        prompt_hash=persona_prompt_hash(persona.model_dump(mode="json")),
        joined_at=NOW,
    )


def _message(sequence: int, content: str) -> TavernMessageRecord:
    return TavernMessageRecord(
        id=f"message-{sequence:02d}",
        room_id="room-1",
        sequence=sequence,
        author_kind=TavernAuthorKind.USER,
        content=content,
        created_at=NOW,
    )


def _scene(depth: int, *, summary: str = "场景摘要") -> SceneProfileRecord:
    children: list[SceneLayerStateRecord] = []
    for level in range(depth, 0, -1):
        children = [
            SceneLayerStateRecord(
                id=f"layer-{level}",
                title=f"层 {level}",
                scope_label="space",
                summary=f"第 {level} 层",
                atmosphere="安静",
                rules="保持连续",
                entrance="入口",
                children=children,
            )
        ]
    return SceneProfileRecord(
        scene_name="预算场景",
        scene_id="scene-budget",
        title="预算场景",
        summary=summary,
        scene_tree=children,
    )


def _preflight(
    participants: list[TavernParticipantRecord],
    *,
    scene_profile: SceneProfileRecord | None = None,
    recent_messages: list[TavernMessageRecord] | None = None,
    user_message: str = "你好。",
):
    return preflight_tavern_actor_prompt(
        persona=participants[0].persona_snapshot,
        participants=participants,
        scene_profile=scene_profile,
        recent_messages=recent_messages or [],
        user_message=user_message,
        guidance="",
        allowed_target_ids=[item.persona_id for item in participants],
        actor_reply_schema="{}",
    )


def _reply(text: str, *, action: str = "停顿后回应") -> TavernActorReply:
    return TavernActorReply(
        text=text,
        mood="calm",
        action=action,
        speech_style="warm",
        delivery_cue="自然停顿",
        state_commentary="保持当前身份",
        addressed_participant_ids=[],
    )


class CountingMockProvider(MockModelProvider):
    def __init__(self) -> None:
        self.call_count = 0

    def generate_tavern_actor_reply(self, **kwargs) -> TavernActorReply:
        self.call_count += 1
        return super().generate_tavern_actor_reply(**kwargs)


class TavernPromptBudgetTests(unittest.TestCase):
    def test_trim_matches_exhaustive_suffix_oracle(self) -> None:
        from app.services import tavern_prompt as prompt

        participants = [_participant(_persona("persona-a", "阿澜"), display_order=0)]
        messages = [_message(i, '中文 evidence \\"\n' * 100) for i in range(1, 9)]
        limits = {"TAVERN_PROMPT_MAX_TRANSCRIPT_BYTES": 6000,
                  "TAVERN_PROMPT_MAX_CANONICAL_BYTES": 20000,
                  "TAVERN_PROMPT_MAX_INPUT_TOKEN_ESTIMATE": 6000}
        with patch.multiple(prompt, **limits):
            actual = _preflight(participants, recent_messages=messages)
        # Independently enumerate every suffix without allowing the preflight to
        # trim it. The first admissible suffix must be the production result.
        with patch.multiple(prompt, **{key: 10**9 for key in limits}):
            for removed in range(len(messages) + 1):
                candidate = _preflight(participants, recent_messages=messages[removed:])
                report = candidate.report
                if (report.final_transcript_bytes <= limits["TAVERN_PROMPT_MAX_TRANSCRIPT_BYTES"]
                    and report.final_prompt_bytes <= limits["TAVERN_PROMPT_MAX_CANONICAL_BYTES"]
                    and report.input_token_estimate <= limits["TAVERN_PROMPT_MAX_INPUT_TOKEN_ESTIMATE"]):
                    break
            else:
                self.fail("fixture has no admissible suffix")
        self.assertEqual(actual.messages, candidate.messages)
        self.assertEqual(actual.report.removed_message_count, removed)
        self.assertEqual(actual.report.input_token_estimate, report.input_token_estimate)

    def test_one_and_six_person_prompts_fit_explicit_limits(self) -> None:
        for count in (1, 6):
            with self.subTest(count=count):
                participants = [
                    _participant(
                        _persona(f"persona-{index}", f"角色{index}"),
                        display_order=index,
                    )
                    for index in range(count)
                ]
                result = _preflight(participants)
                self.assertLessEqual(
                    result.report.final_prompt_bytes,
                    TAVERN_PROMPT_MAX_CANONICAL_BYTES,
                )
                self.assertLessEqual(
                    result.report.input_token_estimate,
                    TAVERN_PROMPT_MAX_INPUT_TOKEN_ESTIMATE,
                )
                self.assertLessEqual(
                    result.report.final_transcript_bytes,
                    TAVERN_PROMPT_MAX_TRANSCRIPT_BYTES,
                )
                self.assertEqual(result.report.removed_message_count, 0)

    def test_forty_long_messages_trim_oldest_deterministically(self) -> None:
        participants = [_participant(_persona("persona-a", "阿澜"), display_order=0)]
        messages = [_message(index, "x" * 4000) for index in range(1, 41)]
        result = _preflight(participants, recent_messages=list(reversed(messages)))

        retained_sequences = [item.sequence for item in result.recent_messages]
        self.assertGreater(result.report.removed_message_count, 0)
        self.assertEqual(
            retained_sequences,
            list(range(result.report.removed_message_count + 1, 41)),
        )
        self.assertLessEqual(
            result.report.final_transcript_bytes,
            TAVERN_PROMPT_MAX_TRANSCRIPT_BYTES,
        )
        self.assertLessEqual(
            result.report.input_token_estimate,
            TAVERN_PROMPT_MAX_INPUT_TOKEN_ESTIMATE,
        )
        self.assertGreater(
            result.report.original_prompt_bytes,
            result.report.final_prompt_bytes,
        )

    def test_partition_boundary_passes_and_plus_one_fails(self) -> None:
        self.assertEqual(
            _require_partition_bytes(
                "x" * TAVERN_PROMPT_MAX_PERSONA_INSTRUCTION_BYTES,
                limit=TAVERN_PROMPT_MAX_PERSONA_INSTRUCTION_BYTES,
                error_code="boundary_error",
            ),
            TAVERN_PROMPT_MAX_PERSONA_INSTRUCTION_BYTES,
        )
        with self.assertRaises(TavernPromptBudgetError) as context:
            _require_partition_bytes(
                "x" * (TAVERN_PROMPT_MAX_PERSONA_INSTRUCTION_BYTES + 1),
                limit=TAVERN_PROMPT_MAX_PERSONA_INSTRUCTION_BYTES,
                error_code="boundary_error",
            )
        self.assertEqual(context.exception.code, "boundary_error")

    def test_scene_depth_boundary_and_plus_one(self) -> None:
        participants = [_participant(_persona("persona-a", "阿澜"), display_order=0)]
        accepted = _preflight(
            participants,
            scene_profile=_scene(TAVERN_PROMPT_MAX_SCENE_DEPTH),
        )
        self.assertEqual(
            accepted.report.scene_depth,
            TAVERN_PROMPT_MAX_SCENE_DEPTH,
        )
        with self.assertRaises(TavernPromptBudgetError) as context:
            _preflight(
                participants,
                scene_profile=_scene(TAVERN_PROMPT_MAX_SCENE_DEPTH + 1),
            )
        self.assertEqual(context.exception.code, "tavern_prompt_scene_depth_exceeded")

    def test_scene_persona_cast_and_final_total_fail_closed(self) -> None:
        actor = _participant(_persona("persona-a", "阿澜"), display_order=0)

        with self.subTest(partition="scene"):
            with self.assertRaises(TavernPromptBudgetError) as context:
                _preflight(
                    [actor],
                    scene_profile=_scene(1, summary="x" * TAVERN_PROMPT_MAX_SCENE_BYTES),
                )
            self.assertEqual(context.exception.code, "tavern_prompt_scene_bytes_exceeded")

        with self.subTest(partition="persona"):
            huge_actor = _participant(
                _persona(
                    "persona-huge",
                    "巨型角色",
                    system_prompt="x"
                    * (TAVERN_PROMPT_MAX_PERSONA_INSTRUCTION_BYTES + 1),
                ),
                display_order=0,
            )
            with self.assertRaises(TavernPromptBudgetError) as context:
                _preflight([huge_actor])
            self.assertEqual(
                context.exception.code,
                "tavern_prompt_persona_instruction_bytes_exceeded",
            )

        with self.subTest(partition="cast"):
            huge_cast_member = _participant(
                _persona(
                    "persona-b",
                    "贝塔",
                    summary="x" * (TAVERN_PROMPT_MAX_CAST_BYTES + 1),
                ),
                display_order=1,
            )
            with self.assertRaises(TavernPromptBudgetError) as context:
                _preflight([actor, huge_cast_member])
            self.assertEqual(context.exception.code, "tavern_prompt_cast_bytes_exceeded")

        with self.subTest(partition="canonical_total"):
            with self.assertRaises(TavernPromptBudgetError) as context:
                _preflight(
                    [actor],
                    user_message="x" * (TAVERN_PROMPT_MAX_CANONICAL_BYTES + 1),
                )
            self.assertEqual(
                context.exception.code,
                "tavern_prompt_canonical_bytes_exceeded",
            )

        with self.subTest(partition="token_estimate"):
            with self.assertRaises(TavernPromptBudgetError) as context:
                _preflight([actor], user_message="字" * 25_000)
            self.assertEqual(
                context.exception.code,
                "tavern_prompt_input_tokens_exceeded",
            )

    def test_preflight_failure_makes_zero_provider_calls(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            database = Database(f"sqlite:///{root / 'prompt-budget.db'}")
            database.create_schema()
            store = LocalJsonStore(database, StorageManager(root / "data"))
            repository = TavernRepository(database)
            persona_engine = PersonaEngine(
                store,
                tavern_reference_counter=repository.count_persona_references,
            )
            persona = persona_engine.create_persona(
                CreatePersonaRequest(
                    name="巨型角色",
                    summary="用于 provider fencing 测试",
                    system_prompt="x"
                    * (TAVERN_PROMPT_MAX_PERSONA_INSTRUCTION_BYTES + 1),
                    slots=[],
                )
            )
            provider = CountingMockProvider()
            service = TavernService(
                repository=repository,
                persona_engine=persona_engine,
                model_provider=provider,
            )
            room = service.create_room(
                CreateTavernRoomRequest(
                    title="预算失败房间",
                    persona_ids=[persona.id],
                    idempotency_key="create-prompt-budget-failure",
                )
            )
            try:
                with self.assertRaises(HTTPException) as context:
                    service.run_turn(
                        room_id=room.room.id,
                        payload=TavernTurnRequest(
                            input={"kind": "user_message", "content": "请回应。"},
                            mode="direct",
                            target_persona_ids=[persona.id],
                            idempotency_key="turn-prompt-budget-failure",
                            expected_room_revision=0,
                        ),
                    )
                self.assertEqual(context.exception.status_code, 502)
                self.assertEqual(provider.call_count, 0)
                run = repository.get_run_by_idempotency_key(
                    room_id=room.room.id,
                    idempotency_key="turn-prompt-budget-failure",
                )
                assert run is not None
                self.assertEqual(
                    run.harness_trace[0].trace_schema_version,
                    "harness-trace-v3",
                )
                self.assertEqual(run.harness_trace[0].stage.value, "actor_reply")
                self.assertEqual(
                    run.harness_trace[0].attempt_records[-1].error_code,
                    "tavern_prompt_persona_instruction_bytes_exceeded",
                )
                self.assertEqual(
                    run.harness_trace[0].commit_evidence.status.value,
                    "not_committed",
                )
                budget_check = next(
                    item
                    for item in run.harness_trace[0].checks
                    if item.name == "prompt_budget"
                )
                self.assertEqual(budget_check.status.value, "failed")
                self.assertEqual(
                    budget_check.code,
                    "tavern_prompt_persona_instruction_bytes_exceeded",
                )
                self.assertIn("partition=persona_instruction_bytes", budget_check.message)
                self.assertIn(
                    f"limit={TAVERN_PROMPT_MAX_PERSONA_INSTRUCTION_BYTES}",
                    budget_check.message,
                )
                self.assertNotIn("x" * 16, budget_check.message)
            finally:
                store.close()


class TavernSpeakerIdentityTests(unittest.TestCase):
    def setUp(self) -> None:
        self.actor = _participant(_persona("persona-a", "阿澜"), display_order=0)
        self.beta = _participant(_persona("persona-b", "贝塔"), display_order=1)
        self.harness = TavernActorHarness()

    def _validate(
        self,
        text: str,
        *,
        participants: list[TavernParticipantRecord] | None = None,
        action: str = "停顿后回应",
    ):
        resolved_participants = participants or [self.actor, self.beta]
        return self.harness.validate_and_repair(
            reply=_reply(text, action=action),
            actor=self.actor,
            participants=resolved_participants,
            recent_messages=[],
            user_message="请回应。",
            guidance="",
            allowed_target_ids=[item.persona_id for item in resolved_participants],
            policy=TavernHarnessPolicy(),
        )

    def test_marker_policy_covers_one_two_four_and_six_person_casts(self) -> None:
        for count in (1, 2, 4, 6):
            with self.subTest(count=count):
                participants = [
                    _participant(
                        _persona(f"persona-{index}", f"角色{index}"),
                        display_order=index,
                    )
                    for index in range(count)
                ]
                markers = build_speaker_identity_markers(
                    participants,
                    actor_persona_id=participants[0].persona_id,
                )
                self.assertEqual(len(markers), count - 1)

    def test_inline_quotes_markdown_ids_aliases_and_unicode_colons_are_repaired(self) -> None:
        cases = [
            "我先回应。\n贝塔：这不是你的台词。",
            "我先回应。\n> **贝塔：** 这不是你的台词。",
            "我先回应。“贝塔：这不是你的台词。”",
            "我先回应。\npersona-b﹕这不是你的台词。",
            "我先回应。\nB꞉ 这不是你的台词。",
            "我先回应。贝塔说道：“这不是你的台词。”",
            "我先回应。贝塔心想今晚必须离开。",
            "我说完后贝塔：这是冒充台词。",
            "我说完后 persona-b：这是冒充台词。",
            "我说完后Ｂ：这是冒充台词。",
            "我说完后 ｐｅｒｓｏｎａ－ｂ：这是冒充台词。",
            "我说完后 `贝塔`：这是冒充台词。",
            "我说完后 ~~贝塔~~：这是冒充台词。",
            "我说完后 [贝塔]：这是冒充台词。",
            "我说完后贝\u200b塔：这是冒充台词。",
            "我说完后贝\u2060塔：这是冒充台词。",
            "我说完后贝\ufeff塔：这是冒充台词。",
            "我说完后 persona\u200b-b：这是冒充台词。",
            "我说完后贝\u200c塔：这是冒充台词。",
            "我说完后贝\u00ad塔：这是冒充台词。",
            "我说完后贝**塔**：这是冒充台词。",
            "我说完后贝~~塔~~：这是冒充台词。",
            "我说完后贝`塔`：这是冒充台词。",
            "我说完后贝塔`:`这是冒充台词。",
            "我说完后[贝](x)塔：这是冒充台词。",
            "我说完后 per**sona-b**：这是冒充台词。",
            "我说完后&#x8D1D;&#x5854;：这是冒充台词。",
            "我说完后&#36125;&#22612;：这是冒充台词。",
            "我说完后贝&#x5854;：这是冒充台词。",
            "我说完后贝塔\\:这是冒充台词。",
            "我说完后 persona\\-b:这是冒充台词。",
        ]
        markers = build_speaker_identity_markers(
            [self.actor, self.beta],
            actor_persona_id=self.actor.persona_id,
        )
        for payload in cases:
            with self.subTest(payload=payload):
                repaired, trace = self._validate(payload)
                self.assertIn(repaired.text, {"我先回应。", "我说完后"})
                self.assertEqual(trace.status, HarnessStatus.REPAIRED)
                identity_check = next(
                    item for item in trace.checks if item.name == "speaker_identity"
                )
                self.assertEqual(
                    identity_check.code,
                    "cross_speaker_impersonation:persona-b",
                )
                self.assertIsNone(
                    find_cross_speaker_impersonation(repaired.text, markers)
                )
                self.assertIn(
                    TAVERN_SPEAKER_IDENTITY_POLICY_VERSION,
                    trace.version,
                )

    def test_unicode_equivalent_and_multichar_casefold_names_are_detected(self) -> None:
        cases = (
            ("persona-accent", "Béta", "Béta：这是冒充台词。"),
            ("persona-accent", "Béta", "Be\u0301ta：这是冒充台词。"),
            ("persona-accent", "Béta", "B&eacute;ta：这是冒充台词。"),
            ("persona-strasse", "Straße", "Straße：这是冒充台词。"),
            ("persona-strasse", "Straße", "STRASSE：这是冒充台词。"),
        )
        for persona_id, display_name, label in cases:
            with self.subTest(display_name=display_name, label=label):
                other = _participant(
                    _persona(persona_id, display_name),
                    display_order=1,
                )
                repaired, trace = self._validate(
                    f"保留这句。{label}",
                    participants=[self.actor, other],
                )
                self.assertEqual(repaired.text, "保留这句。")
                identity_check = next(
                    item for item in trace.checks if item.name == "speaker_identity"
                )
                self.assertEqual(
                    identity_check.code,
                    f"cross_speaker_impersonation:{persona_id}",
                )

    def test_unicode_colon_variants_are_all_detected(self) -> None:
        for colon in (":", "：", "﹕", "꞉", "︓"):
            with self.subTest(colon=colon):
                repaired, _ = self._validate(f"保留这句。\n贝塔{colon}冒充内容")
                self.assertEqual(repaired.text, "保留这句。")

    def test_name_containment_chooses_longest_role_marker(self) -> None:
        short_name = _participant(_persona("persona-short", "安"), display_order=1)
        long_name = _participant(_persona("persona-long", "安娜"), display_order=2)
        repaired, trace = self._validate(
            "先保留。\n安娜：这是冒充台词。",
            participants=[self.actor, short_name, long_name],
        )
        self.assertEqual(repaired.text, "先保留。")
        identity_check = next(
            item for item in trace.checks if item.name == "speaker_identity"
        )
        self.assertEqual(
            identity_check.code,
            "cross_speaker_impersonation:persona-long",
        )

    def test_plain_third_person_mentions_are_allowed(self) -> None:
        cases = (
            "我同意贝塔刚才的看法，也看向贝塔，等她自己回应。",
            "贝塔认为这个命题成立。",
        )
        for payload in cases:
            with self.subTest(payload=payload):
                repaired, trace = self._validate(payload)
                self.assertEqual(repaired.text, payload)
                identity_check = next(
                    item for item in trace.checks if item.name == "speaker_identity"
                )
                self.assertEqual(identity_check.status.value, "passed")

    def test_literal_code_markdown_and_raw_html_examples_are_allowed(self) -> None:
        foo_bar = _participant(
            _persona("persona-foobar", "FooBar"),
            display_order=1,
        )
        markers = build_speaker_identity_markers(
            [self.actor, foo_bar],
            actor_persona_id=self.actor.persona_id,
        )
        cases = (
            "`foo_bar:` 是变量名",
            "foo_bar: 是配置键",
            "foo[bar]: 是链接语法示例",
            "<b>Foo</b>Bar: 是原始 HTML 示例",
        )
        for payload in cases:
            with self.subTest(payload=payload):
                self.assertIsNone(
                    find_cross_speaker_impersonation(payload, markers)
                )

        beta_markers = build_speaker_identity_markers(
            [self.actor, self.beta],
            actor_persona_id=self.actor.persona_id,
        )
        for payload in (
            "`贝塔:` 是代码示例。",
            "  `贝塔:` 是缩进后的代码示例。",
            "> `贝塔:` 是引用中的代码示例。",
            "- `贝塔:` 是列表中的代码示例。",
            "“`贝塔:`” 是带引号的代码示例。",
            "前缀 `贝塔:` 是行内代码示例。",
        ):
            with self.subTest(payload=payload):
                self.assertIsNone(
                    find_cross_speaker_impersonation(payload, beta_markers)
                )

        for payload in (
            "贝_塔_：这是带下划线的可见示例。",
            "贝<b>塔</b>：这是原始 HTML 示例。",
            "贝**塔：这是未配对星号的可见示例。",
        ):
            with self.subTest(payload=payload):
                self.assertIsNone(
                    find_cross_speaker_impersonation(payload, beta_markers)
                )

    def test_code_span_must_contain_alias_and_colon_together(self) -> None:
        markers = build_speaker_identity_markers(
            [self.actor, self.beta],
            actor_persona_id=self.actor.persona_id,
        )
        for payload in (
            "`贝塔`：这是跨节点冒充台词。",
            "贝塔`：`这是跨节点冒充台词。",
            "`贝塔`\u200b`：`这是跨代码节点冒充台词。",
        ):
            with self.subTest(payload=payload):
                violation = find_cross_speaker_impersonation(payload, markers)
                self.assertIsNotNone(violation)
                assert violation is not None
                self.assertEqual(violation.persona_id, "persona-b")

    def test_unrepairable_text_or_non_text_impersonation_fails_closed(self) -> None:
        with self.subTest(field="text"):
            with self.assertRaises(TavernHarnessViolation) as context:
                self._validate("“贝塔：这是冒充台词。”")
            identity_check = next(
                item
                for item in context.exception.trace.checks
                if item.name == "speaker_identity"
            )
            self.assertEqual(identity_check.status.value, "failed")
            self.assertEqual(
                identity_check.code,
                "cross_speaker_impersonation_unrepairable:persona-b",
            )

        with self.subTest(field="action"):
            with self.assertRaises(TavernHarnessViolation) as context:
                self._validate(
                    "我只说自己的内容。",
                    action="贝塔心想今晚必须离开。",
                )
            identity_check = next(
                item
                for item in context.exception.trace.checks
                if item.name == "speaker_identity"
            )
            self.assertEqual(identity_check.status.value, "failed")

    def test_prompt_budget_report_records_content_free_trim_evidence(self) -> None:
        report = _preflight(
            [self.actor],
            recent_messages=[_message(index, "x" * 4000) for index in range(1, 41)],
        ).report
        trace = HarnessTraceRecord(
            version="test",
            workflow="tavern",
            stage="actor_reply",
            status=HarnessStatus.PASSED,
            schema_name="TavernActorReply",
        )
        merged = self.harness.merge_prompt_budget_report(trace, report)
        budget_check = next(
            item for item in merged.checks if item.name == "prompt_budget"
        )
        self.assertIn("prompt_bytes", budget_check.message)
        self.assertIn("transcript_bytes", budget_check.message)
        self.assertIn("removed_messages=", budget_check.message)
        self.assertNotIn("x" * 16, budget_check.message)
        self.assertEqual(merged.status, HarnessStatus.REPAIRED)

        failed = self.harness.merge_prompt_budget_report(
            trace.model_copy(update={"status": HarnessStatus.FAILED}),
            report,
        )
        self.assertEqual(failed.status, HarnessStatus.FAILED)
        self.assertTrue(any(item.name == "prompt_budget" for item in failed.checks))


if __name__ == "__main__":
    unittest.main()
