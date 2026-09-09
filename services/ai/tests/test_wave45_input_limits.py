"""Exact and overflowing production boundaries; no model-quality assertions."""

from __future__ import annotations

import copy
import unittest

from app.models.planning import LearningPlanOperationRequestV1, LearningPlanProposalV1
from app.models.scene import SceneTreeProposalV1, project_scene_tree_proposal
from app.models.study_chat_operation import StudyChatOperationRequestPayload
from app.models.tavern import CreateTavernRoomRequest, TavernTurnRequest
from app.models.persona_generation import (
    PersonaGenerationProposalV1,
)
from pydantic import ValidationError


def layer():
    return dict(
        title="层",
        scope_label="域",
        summary="述",
        atmosphere="气",
        rules="规",
        entrance="门",
        objects=[],
        children=[],
    )


def scene(layers):
    return dict(
        schema_name="scene-tree-proposal",
        schema_version="scene-tree-proposal-v1",
        scene_name="景",
        scene_summary="述",
        selected_path=[0],
        scene_layers=layers,
    )


class Wave45InputLimitTests(unittest.TestCase):
    def test_scene_joint_depth_layers_objects_and_identity_projection(self):
        # Eight chains of depth eight, two objects per layer: all three maxima together.
        roots = []
        nodes = []
        for _ in range(8):
            root = node = layer()
            roots.append(root)
            for depth in range(8):
                nodes.append(node)
                node["objects"] = [
                    dict(name="物", description="述", interaction="动")
                    for _ in range(2)
                ]
                if depth < 7:
                    child = layer()
                    node["children"] = [child]
                    node = child
        payload = scene(roots)
        payload["selected_path"] = [7] + [0] * 7
        proposal = SceneTreeProposalV1.model_validate(payload)
        projected = project_scene_tree_proposal(proposal, allowed_reusable_nodes={})
        identities = []

        def visit(n):
            identities.append(n.id)
            identities.extend(o.id for o in n.objects)
            for child in n.children:
                visit(child)

        for root in projected.scene_layers:
            visit(root)
        self.assertEqual(len(identities), 192)
        self.assertEqual(len(set(identities)), 192)
        self.assertIn(projected.selected_layer_id, identities)
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from app.services.local_store import LocalJsonStore
        from app.services.scene_library import SceneLibraryService

        with TemporaryDirectory() as folder:
            store = LocalJsonStore(Path(folder))
            try:
                saved = SceneLibraryService(store).upsert_scene(
                    scene_id=None,
                    scene_name=projected.scene_name,
                    scene_summary=projected.scene_summary,
                    scene_layers=projected.scene_layers,
                    selected_layer_id=projected.selected_layer_id,
                    collapsed_layer_ids=[],
                    expected_revision=0,
                )
                expected = saved.model_dump(mode="json")
            finally:
                store.close()
            store = LocalJsonStore(Path(folder))
            try:
                self.assertEqual(
                    SceneLibraryService(store)
                    .require_scene(saved.scene_id)
                    .model_dump(mode="json"),
                    expected,
                )
            finally:
                store.close()
        for overflow in ("depth", "objects", "layers"):
            broken = copy.deepcopy(payload)
            node = broken["scene_layers"][0]
            if overflow == "depth":
                for _ in range(7):
                    node = node["children"][0]
                node["children"] = [layer()]
            elif overflow == "layers":
                node["children"].append(layer())
            else:
                node["objects"].append(
                    dict(name="额", description="述", interaction="动")
                )
            with self.subTest(overflow=overflow), self.assertRaises(ValidationError):
                SceneTreeProposalV1.model_validate(broken)

    def test_scene_exact_60000_unicode_codepoints_and_plus_one(self):
        roots = [layer() for _ in range(4)]
        # Six required fields/layer plus name+summary consume 26 codepoints.
        remaining = 60000 - 26
        for node in roots:
            for field in ("summary", "atmosphere", "rules", "entrance"):
                extra = min(3999, remaining)
                node[field] += "🦊" * extra
                remaining -= extra
        self.assertEqual(remaining, 0)
        payload = scene(roots)
        proposal = SceneTreeProposalV1.model_validate(payload)
        project_scene_tree_proposal(proposal, allowed_reusable_nodes={})
        payload["scene_name"] += "🦊"
        with self.assertRaisesRegex(ValidationError, "scene_text_budget_exceeded"):
            SceneTreeProposalV1.model_validate(payload)

    def test_persona_maximum_slot_and_card_batches(self):
        slot = dict(
            kind="k" * 160,
            label="l" * 500,
            content="🦊" * 8000,
            weight=100.0,
            locked=True,
            sort_order=10000,
        )
        setting = dict(
            request_kind="setting_assist",
            slots=[dict(slot) for _ in range(64)],
            system_prompt_suggestion="s" * 16000,
            summary="s" * 8000,
            relationship="r" * 2000,
            learner_address="a" * 500,
        )
        PersonaGenerationProposalV1.model_validate(setting)
        for field, value in (
            ("slots", setting["slots"] + [slot]),
            ("system_prompt_suggestion", "s" * 16001),
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                PersonaGenerationProposalV1.model_validate({**setting, field: value})
        broken = copy.deepcopy(setting)
        broken["slots"][63]["content"] += "🦊"
        with self.assertRaises(ValidationError):
            PersonaGenerationProposalV1.model_validate(broken)
        card = dict(
            title="t" * 500,
            kind="k" * 160,
            label="l" * 500,
            content="c" * 8000,
            source_note="n" * 2000,
            tags=[f"tag-{i}" for i in range(24)],
        )
        batch = dict(request_kind="card_batch", cards=[dict(card) for _ in range(24)])
        PersonaGenerationProposalV1.model_validate(batch)
        for field in ("cards", "tags"):
            broken = copy.deepcopy(batch)
            if field == "cards":
                broken["cards"].append(card)
            else:
                broken["cards"][0]["tags"].append("tag-extra")
            with self.subTest(field=field), self.assertRaises(ValidationError):
                PersonaGenerationProposalV1.model_validate(broken)

    def test_maximum_persona_save_reopen_and_oversize_zero_write(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory

        from app.models.api import CreatePersonaRequest
        from app.services.local_store import LocalJsonStore
        from app.services.persona import PersonaEngine

        payload = dict(
            name="n" * 120,
            summary="s" * 100000,
            relationship="r" * 10000,
            learner_address="a" * 2000,
            system_prompt="p" * 100000,
            reference_hints=[str(i) + "h" * 9998 for i in range(64)],
            slots=[
                dict(
                    kind=f"custom-{i}",
                    label="l" * 256,
                    content="c" * 100000,
                    weight=100.0,
                    locked=True,
                    sort_order=i * 10,
                )
                for i in range(64)
            ],
        )
        with TemporaryDirectory() as folder:
            root = Path(folder)
            store = LocalJsonStore(root)
            try:
                engine = PersonaEngine(store)
                created = engine.create_persona(
                    CreatePersonaRequest.model_validate(payload)
                )
                expected = created.model_dump(mode="json")
                baseline_ids = [p.id for p in engine.list_personas()]
                for field, value in (
                    ("slots", payload["slots"] + [payload["slots"][0]]),
                    ("summary", "s" * 100001),
                ):
                    with self.subTest(field=field), self.assertRaises(ValidationError):
                        engine.create_persona(
                            CreatePersonaRequest.model_validate(
                                {**payload, field: value}
                            )
                        )
                self.assertEqual([p.id for p in engine.list_personas()], baseline_ids)
            finally:
                store.close()
            store = LocalJsonStore(root)
            try:
                actual = PersonaEngine(store).require_persona(created.id)
                self.assertEqual(actual.model_dump(mode="json"), expected)
                self.assertEqual(len(actual.slots), 64)
                self.assertEqual(
                    sum(len(slot.content) for slot in actual.slots), 6400000
                )
            finally:
                store.close()

    def test_planning_nested_maximum_and_each_count_overflow(self):
        refs = [f"section-{i}" for i in range(32)]
        part = dict(page_start=1, page_end=1, source_section_ids=refs)
        chapter = dict(
            title="c" * 500,
            anchor_page_start=1,
            anchor_page_end=1,
            source_section_ids=refs,
            content_slices=[copy.deepcopy(part) for _ in range(24)],
        )
        item = dict(
            title="t" * 500,
            focus="f" * 2000,
            activity_type="learn",
            schedule_chapters=[copy.deepcopy(chapter) for _ in range(24)],
        )
        payload = dict(
            schema_name="learning-plan-proposal",
            schema_version="learning-plan-proposal-v1",
            course_title="c" * 500,
            overview="o" * 4000,
            today_tasks=["t" * 500] * 12,
            schedule=[dict(item, unit_id=f"unit-{i}") for i in range(24)],
        )
        parsed = LearningPlanProposalV1.model_validate(payload)
        self.assertEqual(
            sum(
                len(c.content_slices)
                for s in parsed.schedule
                for c in s.schedule_chapters
            ),
            13824,
        )
        for field in (
            "schedule",
            "schedule_chapters",
            "content_slices",
            "source_section_ids",
            "today_tasks",
        ):
            broken = copy.deepcopy(payload)
            target = (
                broken
                if field in ("schedule", "today_tasks")
                else broken["schedule"][0]
                if field == "schedule_chapters"
                else broken["schedule"][0]["schedule_chapters"][0]
            )
            target[field].append(
                "extra"
                if field == "source_section_ids"
                else copy.deepcopy(target[field][0])
            )
            with self.subTest(field=field), self.assertRaises(ValidationError):
                LearningPlanProposalV1.model_validate(broken)

    def test_document_256_page_stress_commits_and_preserves_anchors(self):
        import io
        from pathlib import Path
        from tempfile import TemporaryDirectory

        import fitz
        from app.services.document_parser import DocumentParser
        from app.services.documents import DocumentService
        from app.services.local_store import LocalJsonStore
        from app.services.study_arrangement import StudyArrangementService
        from fastapi import UploadFile

        with TemporaryDirectory() as folder:
            with fitz.open() as pdf:
                for i in range(256):
                    page = pdf.new_page()
                    page.insert_text(
                        (72, 70), f"Chapter {i + 1} Synthetic vectors", fontsize=16
                    )
                    for j in range(20):
                        page.insert_text(
                            (72, 110 + 20 * j),
                            f"ANCHOR{i:04d} Row {j}: linear maps preserve vector addition and scalar multiplication.",
                        )
                pdf.set_toc([[1, f"Chapter {i + 1}", i + 1] for i in range(256)])
                data = pdf.tobytes()
            store = LocalJsonStore(Path(folder))
            try:
                service = DocumentService(
                    store,
                    DocumentParser(ocr_engine_name="disabled"),
                    StudyArrangementService(),
                )
                doc = service.create_document(
                    UploadFile(
                        filename="synthetic-256.pdf",
                        file=io.BytesIO(data),
                        headers={"content-type": "application/pdf"},
                    )
                )
                service.process_document(doc.id)
                final = service.require_document(doc.id)
                self.assertEqual(final.page_count, 256)
                op = service.process_repository.latest(document_id=doc.id)
                self.assertEqual(op.status.value, "committed")
                from app.models.domain import DocumentDebugRecord

                debug = store.load_item("document_debug", doc.id, DocumentDebugRecord)
                self.assertEqual(
                    [p.page_number for p in debug.pages], list(range(1, 257))
                )
                text = "\n".join(c.content for c in debug.chunks)
                for i in range(256):
                    self.assertIn(f"ANCHOR{i:04d}", text)
                self.assertEqual(len({c.id for c in debug.chunks}), len(debug.chunks))
            finally:
                store.close()

    def test_request_text_limits_and_tavern_maximum_configuration(self):
        plan = dict(
            client_request_id="k" * 80,
            persona_id="p" * 64,
            objective="🦊" * 12000,
            scene_profile_summary="s" * 4000,
        )
        LearningPlanOperationRequestV1.model_validate(plan)
        with self.assertRaises(ValidationError):
            LearningPlanOperationRequestV1.model_validate(
                {**plan, "objective": plan["objective"] + "x"}
            )
        study = dict(
            message="🦊" * 20000,
            hidden_message_prefix="h" * 20000,
            message_kind="learner",
            follow_up_id="",
            expected_session_revision=0,
            attachments=[],
        )
        StudyChatOperationRequestPayload.model_validate(study)
        for field in ("message", "hidden_message_prefix"):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                StudyChatOperationRequestPayload.model_validate(
                    {**study, field: study[field] + "x"}
                )
        room = dict(
            title="t" * 80,
            persona_ids=[f"p-{i}" for i in range(6)],
            opening_prompt="o" * 2000,
            idempotency_key="k" * 80,
        )
        CreateTavernRoomRequest.model_validate(room)
        with self.assertRaises(ValidationError):
            CreateTavernRoomRequest.model_validate(
                {**room, "persona_ids": room["persona_ids"] + ["p-6"]}
            )
        turn = dict(
            input={"kind": "user_message", "content": "🦊" * 4000},
            mode="facilitated",
            target_persona_ids=room["persona_ids"][:4],
            guidance="g" * 1000,
            idempotency_key="k" * 80,
            expected_room_revision=0,
        )
        TavernTurnRequest.model_validate(turn)
        for field, value in (
            ("target_persona_ids", room["persona_ids"][:5]),
            ("guidance", "g" * 1001),
            ("input", {"kind": "user_message", "content": "x" * 4001}),
        ):
            with self.subTest(field=field), self.assertRaises(ValidationError):
                TavernTurnRequest.model_validate({**turn, field: value})
