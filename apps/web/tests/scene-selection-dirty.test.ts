import assert from "node:assert/strict";
import { test } from "node:test";
import { act } from "react";
import { register } from "tsx/esm/api";
import type { SceneDraftStorage } from "../hooks/use-scene-draft";
import { mountSceneHook } from "./scene-hook-test-support.ts";

const unregister = register();
const { useSceneDraft } = await import("../hooks/use-scene-draft.ts");
const { INITIAL_SCENE } = await import("../lib/scene-editor-model.ts");
unregister();

const listeners = { onSelectionChange() {}, onImported() {}, onNotice() {} };
const scheduler = { schedule() {}, cancel() {} };
const root = INITIAL_SCENE[0];
const child = root.children[0];

async function mountDraft(raw: unknown = null) {
  const writes: Parameters<SceneDraftStorage["write"]>[0][] = [];
  const mount = await mountSceneHook(() =>
    useSceneDraft(
      listeners,
      {
        read: () => raw,
        write: (payload) => writes.push(payload),
      },
      scheduler,
    ),
  );
  return { ...mount, writes };
}

test("selection-only edits are dirty and a completed save records its submitted selection", async (t) => {
  const draft = await mountDraft();
  t.after(draft.unmount);
  assert.equal(draft.current().isSceneDraftDirty, false);
  await act(() => draft.current().setCollapsedLayerIds([]));
  assert.equal(draft.current().isSceneDraftDirty, false);
  await act(() => draft.current().selectSceneLayer(child.id));
  assert.equal(draft.current().isSceneDraftDirty, true);
  await act(() => assert.equal(draft.current().flushDraft(), true));
  assert.equal(draft.writes.at(-1)?.selectedLayerId, child.id);
  assert.equal(draft.writes.at(-1)?.draftDirty, true);

  const submitted = draft.current().contentFingerprint;
  await act(() => draft.current().selectSceneLayer(root.id));
  await act(() => draft.current().markSaved(submitted));
  assert.equal(draft.current().isSceneDraftDirty, true);
  await act(() => draft.current().selectSceneObject(child.objects[0].id));
  assert.equal(draft.current().sceneSelectionLayerId, child.id);
  assert.equal(draft.current().isSceneDraftDirty, false);
});

test("restoring an explicitly dirty draft does not mistake the default selection for a baseline", async (t) => {
  const initial = await mountDraft();
  const { sceneName, sceneSummary } = initial.current();
  await initial.unmount();
  const restored = await mountDraft({
    sceneName,
    sceneSummary,
    sceneLayers: INITIAL_SCENE,
    selectedLayerId: root.id,
    collapsedLayerIds: [],
    draftDirty: true,
  });
  t.after(restored.unmount);
  assert.equal(restored.current().isSceneDraftDirty, true);
});

test("clean restored drafts baseline the same selection they actually persist", async (t) => {
  const imported = {
    sceneName: "saved scene",
    sceneSummary: "summary",
    sceneLayers: INITIAL_SCENE,
    collapsedLayerIds: [],
    draftDirty: false,
  };
  for (const [selectedLayerId, effectiveId] of [
    [child.id, child.id],
    ["missing", root.id],
  ]) {
    await t.test(selectedLayerId, async (scenario) => {
      const draft = await mountDraft({ ...imported, selectedLayerId });
      scenario.after(draft.unmount);
      assert.equal(draft.current().sceneSelectionLayerId, effectiveId);
      assert.equal(draft.current().isSceneDraftDirty, false);
      await act(() => assert.equal(draft.current().flushDraft(), true));
      assert.equal(draft.writes.at(-1)?.selectedLayerId, effectiveId);
      assert.equal(draft.writes.at(-1)?.draftDirty, false);
    });
  }
});
