import assert from "node:assert/strict";
import test from "node:test";

import {
  clearPersonaDraftForGeneratedBackfill,
  createPersonaInputToDraft,
  draftToCreatePersonaInput,
  duplicatePersonaDraft,
  EMPTY_PERSONA_DRAFT,
  mergePersonaAssistSlots,
  normalizeImportedPersonaConfig,
  personaDraftFingerprint,
} from "../lib/persona-draft.ts";

test("Persona config export and import preserve every editable field", () => {
  const draft = createPersonaInputToDraft({
    name: "Atlas",
    summary: "Structured mentor",
    relationship: "teacher",
    learnerAddress: "同学",
    systemPrompt: "Stay grounded",
    referenceHints: ["source-a", "source-b"],
    slots: [{
      kind: "teaching_method",
      label: "Method",
      content: "Socratic",
      weight: 73,
      locked: true,
      sortOrder: 20,
    }],
    availableEmotions: ["calm", "focused-custom"],
    availableActions: ["idle", "diagram-custom"],
    defaultSpeechStyle: "precise-custom",
  });
  const exported = draftToCreatePersonaInput(draft);
  const imported = normalizeImportedPersonaConfig(
    JSON.parse(JSON.stringify(exported)) as Record<string, unknown>,
  );

  assert.deepEqual(imported, exported);
  assert.deepEqual(imported.referenceHints, ["source-a", "source-b"]);
  assert.equal(imported.slots[0]?.locked, true);
  assert.equal(imported.slots[0]?.weight, 73);
});

test("Persona config import accepts snake case aliases without coercing unsafe values", () => {
  const imported = normalizeImportedPersonaConfig({
    name: "Alias",
    summary: "",
    relationship: "",
    learner_address: "伙伴",
    system_prompt: "",
    reference_hints: ["one", "ONE", "two"],
    slots: [{
      kind: "custom",
      label: "Tone",
      content: "Clear",
      weight: 0,
      locked: false,
      sort_order: 0,
    }],
    available_emotions: ["calm"],
    available_actions: ["idle"],
    default_speech_style: "warm",
  });

  assert.equal(imported.learnerAddress, "伙伴");
  assert.deepEqual(imported.referenceHints, ["one", "two"]);
  assert.equal(imported.slots[0]?.locked, false);

  for (const invalidSlot of [
    { kind: "custom", label: "", content: "", locked: "false" },
    { kind: "custom", label: "", content: "", weight: Number.NaN },
    { kind: "custom", label: "", content: "", weight: 101 },
    { kind: "custom", label: "", content: "", sortOrder: -1 },
    { kind: "custom", label: "", content: "", sortOrder: 1.5 },
  ]) {
    assert.throws(
      () => normalizeImportedPersonaConfig({
        name: "Invalid",
        systemPrompt: "",
        slots: [invalidSlot],
      }),
    );
  }
});

test("Persona draft fingerprints track edits and reset against committed snapshots", () => {
  const baseline = createPersonaInputToDraft({
    name: "Mentor",
    summary: "Baseline",
    relationship: "",
    learnerAddress: "",
    systemPrompt: "",
    referenceHints: [],
    slots: [],
  });
  const baselineFingerprint = personaDraftFingerprint(baseline);
  assert.equal(personaDraftFingerprint({ ...baseline }), baselineFingerprint);
  assert.notEqual(
    personaDraftFingerprint({ ...baseline, summary: "Edited" }),
    baselineFingerprint,
  );

  const duplicate = duplicatePersonaDraft(baseline);
  assert.equal(duplicate.name, "Mentor 副本");
  assert.notEqual(personaDraftFingerprint(duplicate), baselineFingerprint);
});

test("Whole-setting assist merges by slot identity and preserves locks", () => {
  const current = [
    { kind: "worldview", label: "World", content: "locked", locked: true, weight: 80, sortOrder: 0 },
    { kind: "teaching_method", label: "Method", content: "old", locked: false, weight: 60, sortOrder: 10 },
  ];
  const suggested = [
    { kind: "teaching_method", label: "Method", content: "new", locked: false, weight: 10, sortOrder: 0 },
    { kind: "worldview", label: "World", content: "must-not-apply", locked: false, weight: 10, sortOrder: 10 },
    { kind: "custom", label: "Extra", content: "added", locked: false, weight: 50, sortOrder: 20 },
  ];

  const merged = mergePersonaAssistSlots(current, suggested);
  assert.deepEqual(merged.map((slot) => slot.kind), ["worldview", "teaching_method", "custom"]);
  assert.equal(merged[0]?.content, "locked");
  assert.equal(merged[1]?.content, "new");
  assert.equal(merged[1]?.weight, 60);
  assert.equal(merged[2]?.content, "added");
});

test("Destructive generated backfill clears exactly the fields named in the UI", () => {
  const populated = {
    ...EMPTY_PERSONA_DRAFT,
    name: "Keep name",
    summary: "clear",
    relationship: "clear",
    learnerAddress: "clear",
    systemPrompt: "keep prompt",
    referenceHints: ["clear"],
    slots: [{ kind: "custom", label: "clear", content: "clear" }],
    defaultSpeechStyle: "warm",
  };
  const cleared = clearPersonaDraftForGeneratedBackfill(populated);
  assert.equal(cleared.name, "Keep name");
  assert.equal(cleared.systemPrompt, "keep prompt");
  assert.equal(cleared.summary, "");
  assert.equal(cleared.relationship, "");
  assert.equal(cleared.learnerAddress, "");
  assert.deepEqual(cleared.referenceHints, []);
  assert.deepEqual(cleared.slots, []);
});

test("maximum API-sized persona survives JSON reload and draft conversion without truncation", () => {
  const payload = {
    name: "n".repeat(120), summary: "s".repeat(100_000), relationship: "r".repeat(10_000),
    learnerAddress: "a".repeat(2_000), systemPrompt: "p".repeat(100_000),
    referenceHints: Array.from({ length: 64 }, (_, i) => `${i}:` + "h".repeat(9_990)),
    slots: Array.from({ length: 64 }, (_, i) => ({ kind: `custom-${i}`, label: "l".repeat(256), content: "c".repeat(100_000), weight: 100, locked: true, sortOrder: i })),
    availableEmotions: ["calm"], availableActions: ["idle"], defaultSpeechStyle: "precise",
  };
  const input = normalizeImportedPersonaConfig(JSON.parse(JSON.stringify(payload)));
  assert.deepEqual(input, payload);
  const restored = draftToCreatePersonaInput(createPersonaInputToDraft(input));
  // Saving reindexes application-owned ordering; content and controls remain exact.
  assert.deepEqual(restored, { ...payload, slots: payload.slots.map((slot, i) => ({ ...slot, sortOrder: i * 10 })) });
});
