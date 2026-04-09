import type { CharacterAction, CharacterEmotion, SpeechStyle } from "./character";

export interface PersonaProfile {
  id: string;
  name: string;
  source: "builtin" | "user";
  summary: string;
  systemPrompt: string;
  teachingStyle: string[];
  narrativeMode: "grounded" | "light_story";
  encouragementStyle: string;
  correctionStyle: string;
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
  teachingStyle: string[];
  narrativeMode: "grounded" | "light_story";
  encouragementStyle: string;
  correctionStyle: string;
}
