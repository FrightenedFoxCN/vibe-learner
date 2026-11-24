export type PersonaPromptSuggestion = {
  value: string;
  source: string;
  isCurrent: () => boolean;
};

export function resolvePersonaPromptSuggestion(
  shown: PersonaPromptSuggestion | null,
  current: PersonaPromptSuggestion | null,
): string | null {
  return shown && shown === current && shown.isCurrent() ? shown.value : null;
}
