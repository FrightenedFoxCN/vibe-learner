import type { PersonaProfile } from "@vibe-learner/shared";

export function findLoadablePersona(
  id: string,
  personas: PersonaProfile[],
  isDeleting: (id: string) => boolean,
): PersonaProfile | undefined {
  return isDeleting(id) ? undefined : personas.find((persona) => persona.id === id);
}

export function resolvePersonaDeleteDraft({
  deletedId,
  selectedId,
  sameDraftEpoch,
  wasDirty,
  revisionChanged,
}: {
  deletedId: string;
  selectedId: string;
  sameDraftEpoch: boolean;
  wasDirty: boolean;
  revisionChanged: boolean;
}): "keep-current" | "detach-edited" | "load-fallback" {
  if (!sameDraftEpoch || selectedId !== deletedId) return "keep-current";
  return wasDirty || revisionChanged ? "detach-edited" : "load-fallback";
}
