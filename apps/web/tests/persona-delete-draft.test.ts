import assert from "node:assert/strict";
import test from "node:test";
import type { PersonaProfile } from "@vibe-learner/shared";
import {
  findLoadablePersona,
  resolvePersonaDeleteDraft,
} from "../lib/persona-delete-draft.ts";

function profile(id: string): PersonaProfile {
  return {
    id,
    revision: 1,
    name: id,
    source: "user",
    summary: "",
    relationship: "",
    learnerAddress: "",
    systemPrompt: "",
    referenceHints: [],
    slots: [],
    availableEmotions: [],
    availableActions: [],
    defaultSpeechStyle: "warm",
  };
}

test("B becoming pending during activation makes it unloadable despite a matching library revision", () => {
  const a = profile("A");
  const b = profile("B");
  let deletingId = "";
  const isDeleting = (id: string) => deletingId === id;
  assert.equal(findLoadablePersona("B", [a, b], isDeleting), b);
  deletingId = "B";
  assert.equal(findLoadablePersona("B", [a, b], isDeleting), undefined);
  assert.equal(findLoadablePersona("A", [a, b], isDeleting), a);
  deletingId = "";
  assert.equal(findLoadablePersona("B", [a, b], isDeleting), b);
  assert.equal(findLoadablePersona("B", [a], isDeleting), undefined);
});

const committedB = {
  deletedId: "B",
  selectedId: "B",
  sameDraftEpoch: true,
  wasDirty: false,
  revisionChanged: false,
};

test("deleting selected B detaches both earlier and concurrent edits for save-as-new", () => {
  assert.equal(
    resolvePersonaDeleteDraft({ ...committedB, wasDirty: true }),
    "detach-edited",
  );
  assert.equal(
    resolvePersonaDeleteDraft({ ...committedB, revisionChanged: true }),
    "detach-edited",
  );
  assert.equal(resolvePersonaDeleteDraft(committedB), "load-fallback");
});

test("a delete receipt does not replace another current draft", () => {
  assert.equal(
    resolvePersonaDeleteDraft({ ...committedB, selectedId: "A" }),
    "keep-current",
  );
  assert.equal(
    resolvePersonaDeleteDraft({ ...committedB, sameDraftEpoch: false }),
    "keep-current",
  );
});
