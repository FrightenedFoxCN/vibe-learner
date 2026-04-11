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
  "nod",
  "point",
  "lean_in",
  "smile",
  "pause",
  "write"
] as const;

export const SPEECH_STYLES = [
  "steady",
  "warm",
  "dramatic",
  "gentle",
  "energetic"
] as const;

export type CharacterEmotion = (typeof CHARACTER_EMOTIONS)[number] | string;
export type CharacterAction = (typeof CHARACTER_ACTIONS)[number] | string;
export type SpeechStyle = (typeof SPEECH_STYLES)[number] | string;

export interface CharacterStateEvent {
  emotion: CharacterEmotion;
  action: CharacterAction;
  speechStyle: SpeechStyle;
  sceneHint: string;
  lineSegmentId: string;
  timingHint: "instant" | "linger" | "after_text";
  toolName?: string;
  toolSummary?: string;
  deliveryCue?: string;
  commentary?: string;
}

export interface CharacterStreamFrame {
  messageId: string;
  events: CharacterStateEvent[];
}
