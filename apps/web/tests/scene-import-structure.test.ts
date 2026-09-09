import assert from "node:assert/strict";
import test from "node:test";
import { validateSceneImportStructure } from "../lib/scene-import-structure.ts";

test("scene import accepts exported trees and rejects unrelated valid JSON", () => {
  validateSceneImportStructure({ version: 1, sceneName: "Observatory", sceneLayers: [{ title: "Dome", tags: ["red"], objects: [{ name: "Lamp" }], children: [] }] });
  for (const input of [null, [42], [{ sceneName: "Wrong container" }], { sceneLayers: [{ title: 17 }] }, { version: 2, sceneLayers: [{ title: "Dome" }] }]) {
    assert.throws(() => validateSceneImportStructure(input));
  }
});

test("scene import enforces depth, layer, object and text limits before mutation", () => {
  const layer = () => ({ title: "Dome", objects: [] as { name: string }[], children: [] as unknown[] });
  validateSceneImportStructure({ sceneLayers: Array.from({ length: 64 }, layer) });
  assert.throws(() => validateSceneImportStructure({ sceneLayers: Array.from({ length: 65 }, layer) }));
  const root = layer(); root.objects = Array.from({ length: 128 }, () => ({ name: "Lamp" }));
  validateSceneImportStructure([root]);
  root.objects.push({ name: "Extra" });
  assert.throws(() => validateSceneImportStructure([root]));
  let tree = layer();
  for (let i = 0; i < 7; i++) tree = { ...layer(), children: [tree] };
  validateSceneImportStructure([tree]);
  assert.throws(() => validateSceneImportStructure([{ ...layer(), children: [tree] }]));
  assert.throws(() => validateSceneImportStructure([{ title: "Dome", summary: "x".repeat(60_000) }]));
});

test("scene import counts Unicode codepoints at exactly 60000 and leaves source untouched on rejection", () => {
  const input = { sceneName: "景", sceneSummary: "述", sceneLayers: [{ title: "层", summary: "🦊".repeat(59_997) }] };
  const serialized = JSON.stringify(input);
  validateSceneImportStructure(input);
  assert.equal(JSON.stringify(input), serialized);
  const invalid = { ...input, sceneName: "景🦊" };
  const before = JSON.stringify(invalid);
  assert.throws(() => validateSceneImportStructure(invalid), /scene_text_budget_exceeded/);
  assert.equal(JSON.stringify(invalid), before);
  validateSceneImportStructure(JSON.parse(serialized));
});
