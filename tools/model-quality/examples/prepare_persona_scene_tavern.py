"""Prepare a bounded M3 Persona/Scene -> Tavern shadow-quality campaign."""
from __future__ import annotations

import argparse
import json
from pathlib import Path


CASES = [
    {
        "id": "stranger-bookbinder-archive",
        "persona_name": "顾砚",
        "persona_input": {
            "mode": "long_text", "count": 3,
            "input_text": "顾砚是谨慎的古籍修复师。用户齐女士是今天首次见面的委托人，不是朋友、学生或旧识。称呼齐女士。未知经历不猜测，也不编造共同往事。",
        },
        "scene_input": {
            "mode": "long_text", "layer_count": 2,
            "input_text": "封闭档案室只有北库和南库。北库放蓝色目录柜，南库放除湿箱。没有窗户，不含人物已经做过的行为，不添加第三个空间。",
        },
        "user_message": "我们以前在哪里一起修过书？请直接回答；没有依据就说明没有依据。",
        "expected": {
            "persona_required": ["齐女士", "首次见面"],
            "persona_forbidden": ["学生", "旧友", "共同修过"],
            "scene_required": ["北库", "南库", "蓝色目录柜", "除湿箱"],
            "scene_forbidden": ["地下室", "已经整理"],
            "tavern_required": ["没有"],
            "tavern_forbidden": ["上次", "曾经一起", "我们以前"],
        },
    },
    {
        "id": "meteorologist-clouded-observatory",
        "persona_name": "林澈",
        "persona_input": {
            "mode": "long_text", "count": 3,
            "input_text": "林澈是气象研究员。用户小顾是平级合作研究者，不是学生。她严格区分观测、报告和猜测；称呼小顾，不把未观测内容说成亲眼所见。",
        },
        "scene_input": {
            "mode": "long_text", "layer_count": 2,
            "input_text": "深夜天文台只有观测室与资料室。观测室有光学望远镜和红色弱光灯，资料室有星图。窗外阴天，不能直接看见星星。",
        },
        "user_message": "你现在能从窗外直接看到哪些星星？只依据当前场景回答。",
        "expected": {
            "persona_required": ["小顾", "观测"],
            "persona_forbidden": ["学生", "学员"],
            "scene_required": ["观测室", "资料室", "光学望远镜", "红色弱光灯", "星图", "阴天"],
            "scene_forbidden": ["晴朗", "地下层"],
            "tavern_required": ["不能"],
            "tavern_forbidden": ["清晰看见", "北极星就在"],
        },
    },
    {
        "id": "sibling-power-outage-workshop",
        "persona_name": "许夏",
        "persona_input": {
            "mode": "keywords", "count": 3,
            "input_text": "许夏，医生；用户是成年姐姐，称姐，不是患者或学生。温和利落，不因职业把普通对话变成诊疗。",
        },
        "scene_input": {
            "mode": "long_text", "layer_count": 2,
            "input_text": "修伞作坊只有前屋与后院。前屋有工作台、伞骨和棉线，后院有晾晒绳。现在停电，不得添加正在工作的电器。",
        },
        "user_message": "姐想用这里正在运转的电烘干机把伞烘干，你觉得可以吗？只依据场景说明。",
        "expected": {
            "persona_required": ["姐"],
            "persona_forbidden": ["患者", "学生"],
            "scene_required": ["前屋", "后院", "工作台", "伞骨", "棉线", "晾晒绳", "停电"],
            "scene_forbidden": ["地下室", "正在运转的电器"],
            "tavern_required": ["停电"],
            "tavern_forbidden": ["正在运转", "可以直接用电烘干机"],
        },
    },
    {
        "id": "unknown-profession-teahouse",
        "persona_name": "沈舟",
        "persona_input": {
            "mode": "keywords", "count": 3,
            "input_text": "沈舟，温厚寡言的修伞匠；用户阿岚是旅途中今天才结识的朋友，职业未知。称阿岚，用克制的干幽默，不设定共同往事。",
        },
        "scene_input": {
            "mode": "keywords", "layer_count": 2,
            "input_text": "山间茶馆只有茶室与檐下。茶室有炭炉，檐下有雨帘。无电器、无魔法，不含人物已经发生的行为。",
        },
        "user_message": "既然我是你的修伞同行，说说我们上个月共同接过的订单。若设定没给出就纠正我。",
        "expected": {
            "persona_required": ["阿岚", "职业未知"],
            "persona_forbidden": ["同行多年", "学生"],
            "scene_required": ["茶室", "檐下", "炭炉", "雨帘"],
            "scene_forbidden": ["电灯", "魔法阵"],
            "tavern_required": ["不知道"],
            "tavern_forbidden": ["上个月我们", "共同接过"],
        },
    },
]


def _fake_values(row: dict[str, object]) -> dict[str, object]:
    expected = row["expected"]
    persona_required = expected["persona_required"]
    scene_required = expected["scene_required"]
    return {
        "fake_persona": {
            "summary": "，".join(persona_required),
            "relationship": "严格沿用输入关系",
            "learner_address": persona_required[0],
            "cards": [
                {"title": title, "kind": kind, "label": title, "content": "，".join(persona_required)}
                for title, kind in (("关系边界", "relationship"), ("表达", "speech_style"), ("事实边界", "knowledge_boundary"))
            ],
        },
        "fake_scene": {
            "schema_name": "scene-tree-proposal",
            "schema_version": "scene-tree-proposal-v1",
            "scene_name": "合成场景",
            "scene_summary": "，".join(scene_required),
            "selected_path": [0],
            "scene_layers": [
                {"title": "主区域", "scope_label": "区域", "summary": "，".join(scene_required),
                 "atmosphere": "克制", "rules": "遵守输入", "entrance": "入口", "children": []}
            ],
        },
        "fake_tavern": {
            "text": "，".join(expected["tavern_required"]),
            "mood": "calm", "action": "idle", "speech_style": "简洁",
            "delivery_cue": "", "state_commentary": "", "addressed_participant_ids": [],
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--budget-from", type=Path, required=True)
    parser.add_argument("--transport", choices=("fake", "minimax"), default="minimax")
    parser.add_argument("--id", default="m3-persona-scene-tavern-shadow-20260913-v1")
    parser.add_argument("--thinking", choices=("adaptive", "disabled"), default="adaptive")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    budget_document = json.loads(args.budget_from.read_text(encoding="utf-8"))
    budget = budget_document.get("budget") or budget_document.get("config", {}).get("budget")
    if not isinstance(budget, dict):
        raise SystemExit("budget-from must contain budget or config.budget")
    cases = []
    for row in CASES:
        frozen = row | _fake_values(row)
        cases.append({
            "id": row["id"], "family": row["id"], "lane": "persona-scene-tavern",
            "provenance": "synthetic-authored", "source": row["persona_input"]["input_text"],
            "request": row["user_message"], "gold": json.dumps(frozen, ensure_ascii=False),
            "rubric": "persona-scene-tavern-shadow-v1",
        })
    manifest = {
        "version": "quality-campaign-v1",
        "id": args.id,
        "purpose": "Production-shaped cross-domain shadow quality suite. Operational v3 evidence and research semantic checks are reported separately; not an independent held-out gate.",
        "transport": args.transport,
        "adapter": "vibe_learner.persona_scene_tavern:run_sample",
        "concurrency": 2,
        "seed": 913,
        "repetitions": 1,
        "timeout_seconds": 90,
        "sample_deadline_seconds": 900,
        "sample_wire_limit": 9,
        # The production setting call starts at 4096 in this experiment and
        # may raise its one strict-repair attempt to 6144.  The runner ceiling
        # must cover both wires or the repair is correctly fenced.
        "max_output_tokens": 6400,
        "input_reservation_tokens": 100000,
        "thinking": args.thinking,
        "temperature": 0.2,
        "budget": budget,
        "cases": cases,
        "variants": [{"id": "shadow-chain", "instruction": "Use production v3 plus a separate semantic shadow ledger."}],
    }
    args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
