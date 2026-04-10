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
}

export interface PersonaProfile {
  id: string;
  name: string;
  source: "builtin" | "user";
  summary: string;
  systemPrompt: string;
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
  systemPrompt: string;
  slots: PersonaSlot[];
  availableEmotions?: CharacterEmotion[];
  availableActions?: CharacterAction[];
  defaultSpeechStyle?: SpeechStyle;
}
