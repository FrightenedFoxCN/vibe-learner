import type { PersonaSlot } from "@vibe-learner/shared";
import type { PersonaDraftSlot } from "./persona-draft";

export function updateDraftSlot(
  slots: PersonaDraftSlot[],
  id: string,
  changes: Partial<PersonaSlot>,
): PersonaDraftSlot[] {
  return slots.map((slot) =>
    slot.draftSlotId === id ? { ...slot, ...changes, draftSlotId: id } : slot,
  );
}

export function removeDraftSlot(
  slots: PersonaDraftSlot[],
  id: string,
): PersonaDraftSlot[] {
  return slots.filter((slot) => slot.draftSlotId !== id);
}

export function reindexDraftSlots(slots: PersonaDraftSlot[]): PersonaDraftSlot[] {
  return slots.map((slot, index) => ({ ...slot, sortOrder: index * 10 }));
}

export function reorderDraftSlots(
  slots: PersonaDraftSlot[],
  id: string,
  insertionIndex: number,
): PersonaDraftSlot[] {
  const from = slots.findIndex((slot) => slot.draftSlotId === id);
  const to = from < insertionIndex ? insertionIndex - 1 : insertionIndex;
  if (from < 0 || from === to || insertionIndex < 0 || insertionIndex > slots.length) {
    return slots;
  }
  const next = [...slots];
  const [moved] = next.splice(from, 1);
  next.splice(to, 0, moved);
  return reindexDraftSlots(next);
}
