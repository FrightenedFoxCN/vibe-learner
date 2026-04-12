from __future__ import annotations

from app.models.domain import PersonaProfile, PersonaSlot, persona_sorted_slots


def render_persona_runtime_instruction(persona: PersonaProfile) -> str:
    return render_persona_runtime_instruction_from_parts(
        name=persona.name,
        summary=persona.summary,
        relationship=persona.relationship,
        learner_address=persona.learner_address,
        slots=persona.slots,
        additional_instruction=persona.system_prompt,
        default_speech_style=persona.default_speech_style,
    )


def render_persona_runtime_instruction_from_parts(
    *,
    name: str,
    summary: str,
    relationship: str,
    learner_address: str,
    slots: list[PersonaSlot],
    additional_instruction: str = "",
    default_speech_style: str = "",
) -> str:
    resolved_name = name.strip() or "未命名教师"
    resolved_summary = summary.strip() or "围绕教材章节进行结构化导学。"
    resolved_relationship = relationship.strip() or "标准导学教师"
    resolved_address = learner_address.strip() or "同学"
    resolved_style = default_speech_style.strip() or "warm"
    slot_lines = _render_slot_lines(slots)

    sections = [
        f"你将扮演教材导学人格「{resolved_name}」。",
        "\n".join(
            [
                "人格定位：",
                f"- 摘要：{resolved_summary}",
                f"- 与学习者关系：{resolved_relationship}",
                f"- 对学习者常用称呼：{resolved_address}",
            ]
        ),
        "\n".join(
            [
                "基础行为准则：",
                "- 始终以教材章节、题面和可验证证据为中心，不脱离当前学习上下文。",
                "- 讲解应结构清晰、反馈具体、节奏稳定，并优先给出下一步可执行动作。",
                "- 保持人格风格，但不要让角色表演压过知识解释或证据依据。",
            ]
        ),
        "人格插槽展开：\n" + ("\n".join(slot_lines) if slot_lines else "- 当前未配置额外人格插槽。"),
        f"默认表达风格：{resolved_style}。",
    ]

    if additional_instruction.strip():
        sections.append("附加系统约束：\n" + additional_instruction.strip())

    return "\n\n".join(section for section in sections if section.strip())


def _render_slot_lines(slots: list[PersonaSlot]) -> list[str]:
    lines: list[str] = []
    for slot in persona_sorted_slots(slots):
        content = slot.content.strip()
        if not content:
            continue
        label = slot.label.strip() or slot.kind.strip() or "自定义"
        lines.append(f"- {label}：{content}")
    return lines
