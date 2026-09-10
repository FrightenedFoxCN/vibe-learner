import type { PersonaCard, PersonaProfile } from "@vibe-learner/shared";
import { mergeReferenceHints, type PersonaDraft } from "./persona-draft";

export function buildDraftWithInsertedCards(
  draft: PersonaDraft,
  cards: PersonaCard[],
  insertIndex?: number,
): { draft: PersonaDraft; insertedCount: number } {
  const safeInsertIndex = Math.max(0, Math.min(insertIndex ?? draft.slots.length, draft.slots.length));
  const existingKeys = new Set(
    draft.slots.map((slot) => `${slot.kind}::${slot.label}::${slot.content.trim()}`)
  );
  const appended = cards
    .filter((card) => {
      const key = `${card.kind}::${card.label}::${card.content.trim()}`;
      if (existingKeys.has(key)) {
        return false;
      }
      existingKeys.add(key);
      return true;
    })
    .map((card, index) => ({
      kind: card.kind,
      label: card.label,
      content: card.content,
      weight: 50,
      locked: false,
      sortOrder: (safeInsertIndex + index) * 10,
    }));
  if (!appended.length) {
    return { draft, insertedCount: 0 };
  }
  const nextSlots = [...draft.slots];
  nextSlots.splice(safeInsertIndex, 0, ...appended);
  return {
    draft: {
      ...draft,
      slots: nextSlots.map((slot, index) => ({ ...slot, sortOrder: index * 10 })),
    },
    insertedCount: appended.length,
  };
}

export function matchesPersonaCard(card: PersonaCard, query: string): boolean {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) {
    return true;
  }
  const haystack = [
    card.title,
    card.label,
    card.content,
    card.sourceNote,
    card.searchKeywords,
    card.tags.join(" "),
  ]
    .join("\n")
    .toLowerCase();
  return haystack.includes(trimmed);
}

export function matchesPersonaProfile(persona: PersonaProfile, query: string): boolean {
  const trimmed = query.trim().toLowerCase();
  if (!trimmed) {
    return true;
  }
  const haystack = [
    persona.name,
    persona.summary,
    persona.relationship,
    persona.learnerAddress,
    persona.systemPrompt,
    (persona.referenceHints ?? []).join(" "),
    persona.source === "builtin" ? "内置人格" : "用户人格",
  ]
    .join("\n")
    .toLowerCase();
  return haystack.includes(trimmed);
}

export function collectReferenceHintsFromCards(cards: PersonaCard[]): string[] {
  return mergeReferenceHints(
    [],
    cards.map((card) => card.sourceNote)
  );
}

