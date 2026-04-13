import type { CharacterAction, CharacterEmotion, SpeechStyle } from "./character";

export const PERSONA_SLOT_KINDS = [
  "worldview",
  "past_experiences",
  "thinking_style",
  "teaching_method",
  "narrative_mode",
  "encouragement_style",
  "correction_style",
  "custom"
] as const;

export type PersonaSlotKind = (typeof PERSONA_SLOT_KINDS)[number];

export const PERSONA_SLOT_KIND_LABELS: Record<PersonaSlotKind, string> = {
  worldview: "世界观起点",
  past_experiences: "过往经历",
  thinking_style: "思维风格",
  teaching_method: "教学方法",
  narrative_mode: "叙事模式",
  encouragement_style: "鼓励策略",
  correction_style: "纠错策略",
  custom: "自定义"
};

export interface PersonaSlot {
  kind: PersonaSlotKind | string;
  label: string;
  content: string;
  weight?: number;
  locked?: boolean;
  sortOrder?: number;
}

export type PersonaCardSource = "manual" | "generated_keywords" | "generated_text";

export type PersonaCardGenerationMode = "keywords" | "long_text";

export interface PersonaCard {
  id: string;
  title: string;
  kind: PersonaSlotKind | string;
  label: string;
  content: string;
  tags: string[];
  searchKeywords: string;
  source: PersonaCardSource;
  sourceNote: string;
  createdAt: string;
  updatedAt: string;
}

export interface CreatePersonaCardInput {
  title: string;
  kind: PersonaSlotKind | string;
  label: string;
  content: string;
  tags?: string[];
  searchKeywords?: string;
  source?: PersonaCardSource;
  sourceNote?: string;
}

export interface PersonaProfile {
  id: string;
  name: string;
  source: "builtin" | "user";
  summary: string;
  relationship: string;
  learnerAddress: string;
  systemPrompt: string;
  referenceHints: string[];
  slots: PersonaSlot[];
  availableEmotions: CharacterEmotion[];
  availableActions: CharacterAction[];
  defaultSpeechStyle: SpeechStyle;
}

export interface PersonaMemory {
  personaId: string;
  learnerName: string;
  weakTopics: string[];
  encouragementPreferences: string[];
  milestoneNotes: string[];
}

export interface CreatePersonaInput {
  name: string;
  summary: string;
  relationship: string;
  learnerAddress: string;
  systemPrompt: string;
  referenceHints?: string[];
  slots: PersonaSlot[];
  availableEmotions?: CharacterEmotion[];
  availableActions?: CharacterAction[];
  defaultSpeechStyle?: SpeechStyle;
}

export interface PersonaRuntimeInstructionInput {
  name: string;
  summary: string;
  relationship: string;
  learnerAddress: string;
  systemPrompt: string;
  referenceHints?: string[];
  slots: PersonaSlot[];
  defaultSpeechStyle?: SpeechStyle;
}

export function sortPersonaSlots(slots: PersonaSlot[]): PersonaSlot[] {
  return [...slots].sort((left, right) => {
    const orderLeft = Number(left.sortOrder ?? 0);
    const orderRight = Number(right.sortOrder ?? 0);
    if (orderLeft !== orderRight) {
      return orderLeft - orderRight;
    }
    const weightLeft = Number(left.weight ?? 0);
    const weightRight = Number(right.weight ?? 0);
    if (weightLeft !== weightRight) {
      return weightRight - weightLeft;
    }
    return (left.label || left.kind).localeCompare(right.label || right.kind, "zh-CN");
  });
}

export function renderPersonaRuntimeInstruction(
  input: PersonaRuntimeInstructionInput
): string {
  const resolvedName = input.name.trim() || "未命名教师";
  const resolvedSummary = input.summary.trim() || "围绕教材章节进行结构化导学。";
  const resolvedRelationship = input.relationship.trim() || "标准导学教师";
  const resolvedAddress = input.learnerAddress.trim() || "同学";
  const resolvedStyle = (input.defaultSpeechStyle ?? "warm").trim() || "warm";
  const resolvedReferenceHints = normalizePersonaReferenceHints(input.referenceHints ?? []);
  const slotLines = sortPersonaSlots(input.slots ?? [])
    .map((slot) => {
      const content = slot.content.trim();
      if (!content) {
        return "";
      }
      const label = slot.label.trim() || slot.kind.trim() || "自定义";
      return `- ${label}：${content}`;
    })
    .filter(Boolean);

  const sections = [
    `你将扮演教材导学人格「${resolvedName}」。`,
    [
      "人格定位：",
      `- 摘要：${resolvedSummary}`,
      `- 与学习者关系：${resolvedRelationship}`,
      `- 对学习者常用称呼：${resolvedAddress}`
    ].join("\n"),
    [
      "基础行为准则：",
      "- 始终以教材章节、题面和可验证证据为中心，不脱离当前学习上下文。",
      "- 讲解应结构清晰、反馈具体、节奏稳定，并优先给出下一步可执行动作。",
      "- 保持人格风格，但不要让角色表演压过知识解释或证据依据。"
    ].join("\n"),
    `人格插槽展开：\n${slotLines.length ? slotLines.join("\n") : "- 当前未配置额外人格插槽。"}`,
    `默认表达风格：${resolvedStyle}。`
  ];

  if (resolvedReferenceHints.length) {
    sections.push(`灵感来源提示：\n${resolvedReferenceHints.map((hint) => `- ${hint}`).join("\n")}`);
  }
  if (resolvedReferenceHints.some(looksLikeFictionReferenceHint)) {
    sections.push(
      [
        "常见虚构作品来源处理：",
        "- 上述线索只用于稳定语气、关系感、节奏与角色轮廓。",
        "- 不要把原作剧情、设定或世界观细节当作当前会话里的既成事实。",
        "- 若学习者提到原作，可承认风格灵感相近，但不要自称拥有原作中的完整记忆。"
      ].join("\n")
    );
  }

  const additionalInstruction = input.systemPrompt.trim();
  if (additionalInstruction) {
    sections.push(`附加系统约束：\n${additionalInstruction}`);
  }

  return sections.join("\n\n");
}

function normalizePersonaReferenceHints(hints: string[]): string[] {
  const seen = new Set<string>();
  return hints
    .map((hint) => hint.trim())
    .filter(Boolean)
    .filter((hint) => {
      const key = hint.toLowerCase();
      if (seen.has(key)) {
        return false;
      }
      seen.add(key);
      return true;
    });
}

function looksLikeFictionReferenceHint(hint: string): boolean {
  return /(角色|作品|小说|动画|动漫|游戏|电影|影视|漫画|剧集|侦探型|冒险|魔法|骑士|学院派|英雄|反派|原作)/i.test(hint);
}
