export const CHARACTER_EMOTIONS = [
  "calm",
  "encouraging",
  "playful",
  "serious",
  "excited",
  "concerned"
] as const;

export const CHARACTER_ACTIONS = [
  "idle",
  "explain",
  "point",
  "celebrate",
  "reflect",
  "prompt"
] as const;

export const SPEECH_STYLES = [
  "steady",
  "warm",
  "dramatic",
  "gentle",
  "energetic"
] as const;

export type CharacterEmotion = (typeof CHARACTER_EMOTIONS)[number];
export type CharacterAction = (typeof CHARACTER_ACTIONS)[number];
export type SpeechStyle = (typeof SPEECH_STYLES)[number];

export interface CharacterStateEvent {
  emotion: CharacterEmotion;
  action: CharacterAction;
  intensity: number;
  speechStyle: SpeechStyle;
  sceneHint: string;
  lineSegmentId: string;
  timingHint: "instant" | "linger" | "after_text";
  toolName?: string;
  toolSummary?: string;
}

export interface CharacterStreamFrame {
  messageId: string;
  events: CharacterStateEvent[];
}
