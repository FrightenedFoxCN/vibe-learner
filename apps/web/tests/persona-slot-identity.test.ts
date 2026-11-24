import assert from "node:assert/strict";
import test from "node:test";
import type { PersonaCard } from "@vibe-learner/shared";
import {
  createPersonaInputToDraft,
  draftToCreatePersonaInput,
  mergePersonaAssistSlots,
  personaDraftFingerprint,
  personaSlotPayload,
} from "../lib/persona-draft.ts";
import { buildDraftWithInsertedCards } from "../lib/persona-editor-model.ts";
import {
  removeDraftSlot,
  reorderDraftSlots,
  updateDraftSlot,
} from "../lib/persona-slot-edit.ts";

const slot = {
  kind: "custom",
  label: "same",
  content: "same",
  weight: 50,
  locked: false,
  sortOrder: 0,
};
const input = {
  name: "A",
  summary: "",
  relationship: "",
  learnerAddress: "",
  systemPrompt: "",
  slots: [slot, slot, slot],
};

test("same-label rows retain independent identity through editing, deletion and reordering", () => {
  const { slots } = createPersonaInputToDraft(input);
  const [a, b, c] = slots.map((row) => row.draftSlotId);
  assert.equal(new Set([a, b, c]).size, 3);
  const renamed = updateDraftSlot(slots, b, { label: "typed", kind: "worldview" });
  assert.deepEqual(
    renamed.map((row) => row.draftSlotId),
    [a, b, c],
  );
  const afterDelete = removeDraftSlot(renamed, a);
  const moved = reorderDraftSlots(afterDelete, b, 2);
  assert.deepEqual(
    moved.map((row) => row.draftSlotId),
    [c, b],
  );
  const edited = updateDraftSlot(moved, b, { content: "after sort" });
  assert.deepEqual(
    edited.map((row) => [row.draftSlotId, row.label, row.content]),
    [
      [c, "same", "same"],
      [b, "typed", "after sort"],
    ],
  );
  assert.deepEqual(
    edited.map((row) => row.sortOrder),
    [0, 10],
  );
  assert.equal(reorderDraftSlots(edited, a, 1), edited);
});

test("card insertion and assist preserve existing identities but allocate new ones", () => {
  const draft = createPersonaInputToDraft({ ...input, slots: [slot] });
  const [existing] = draft.slots;
  const card: PersonaCard = {
    id: "card",
    title: "Card",
    kind: "worldview",
    label: "card",
    content: "card",
    tags: [],
    searchKeywords: "",
    source: "manual",
    sourceNote: "",
    createdAt: "2026-01-01T00:00:00Z",
    updatedAt: "2026-01-01T00:00:00Z",
  };
  const inserted = buildDraftWithInsertedCards(draft, [card], 0).draft.slots;
  assert.equal(inserted[1].draftSlotId, existing.draftSlotId);
  assert.notEqual(inserted[0].draftSlotId, existing.draftSlotId);
  const merged = mergePersonaAssistSlots(inserted, [
    { ...slot, content: "assisted" },
    { ...slot, kind: "narrative_mode" },
  ]);
  assert.deepEqual(
    merged.slice(0, 2).map((row) => row.draftSlotId),
    inserted.map((row) => row.draftSlotId),
  );
  assert.equal(merged[1].content, "assisted");
  assert.equal(new Set(merged.map((row) => row.draftSlotId)).size, 3);
});

test("draft-only IDs do not change fingerprints or enter exported/AI slot payloads", () => {
  const first = createPersonaInputToDraft(input);
  const second = createPersonaInputToDraft(input);
  assert.notEqual(first.slots[0].draftSlotId, second.slots[0].draftSlotId);
  assert.equal(personaDraftFingerprint(first), personaDraftFingerprint(second));
  assert.ok(
    draftToCreatePersonaInput(first).slots.every((row) => !("draftSlotId" in row)),
  );
  assert.deepEqual(personaSlotPayload(first.slots[0]), slot);
});
