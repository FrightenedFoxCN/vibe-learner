import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useSceneDraft } from "../hooks/use-scene-draft.ts";
import { useSceneRewrite } from "../hooks/use-scene-rewrite.ts";
import { updateLayerTree } from "../lib/scene-editor-model.ts";
import { saveClock } from "./support/save-clock.js";

afterEach(cleanup);
after(() => dom.window.close());
function fixture() {
  const requests = [], clock = saveClock();
  return { requests, ...renderHook(() => {
    const draft = useSceneDraft({
      onSelectionChange: () => rewrite.invalidateRewrite(),
      onImported: () => rewrite.resetRewrite(), onNotice() {},
    }, { read: () => null, write() {} }, clock);
    const rewrite = useSceneRewrite({
      sceneLayers: draft.sceneLayers, currentSceneAsyncScope: draft.currentSceneAsyncScope,
      setSceneFieldTarget: draft.setSceneFieldTarget,
      updateLayer: (id, update) => draft.updateSceneLayersState(layers => updateLayerTree(layers, id, update)),
      updateObject: (layerId, objectId, key, value) => draft.updateSceneLayersState(layers => updateLayerTree(layers, layerId, layer => ({ ...layer, objects: layer.objects.map(object => object.id === objectId ? { ...object, [key]: value } : object) }))),
    }, input => new Promise((resolve, reject) => requests.push({ input, resolve: content => resolve({ slot: { ...input.slot, content }, modelRecoveries: [] }), reject })));
    return { draft, rewrite };
  }) };
}

test("layer rewrite applies once and undo restores the exact previous field", async () => {
  const h = fixture(), original = h.result.current.draft.sceneLayers[0]; let run;
  act(() => { run = h.result.current.rewrite.rewriteLayerField(original.id, "summary", "Summary"); });
  assert.equal(h.requests[0].input.slot.content, original.summary);
  await act(async () => { h.requests[0].resolve("rewritten"); await run; });
  assert.equal(h.result.current.draft.sceneLayers[0].summary, "rewritten");
  act(() => h.result.current.rewrite.undoLastRewrite());
  assert.equal(h.result.current.draft.sceneLayers[0].summary, original.summary);
  assert.equal(h.result.current.rewrite.lastRewrite, null);
});

test("object undo refuses to overwrite a subsequent manual field edit", async () => {
  const h = fixture(), layer = h.result.current.draft.sceneLayers[0], object = layer.objects[0]; let run;
  act(() => { run = h.result.current.rewrite.rewriteObjectField(layer.id, object.id, "description", "Description"); });
  await act(async () => { h.requests[0].resolve("rewritten"); await run; });
  act(() => h.result.current.draft.updateSceneLayersState(layers => updateLayerTree(layers, layer.id, current => ({ ...current, objects: current.objects.map(item => item.id === object.id ? { ...item, description: "manual edit" } : item) }))));
  act(() => h.result.current.rewrite.undoLastRewrite());
  assert.equal(h.result.current.draft.sceneLayers[0].objects[0].description, "manual edit");
  assert.match(h.result.current.rewrite.rewriteError, /字段已更改/);
});

test("a superseded failure does not clear a newer request or display its error", async () => {
  const h = fixture(), layer = h.result.current.draft.sceneLayers[0]; let old, current;
  act(() => { old = h.result.current.rewrite.rewriteLayerField(layer.id, "summary", "Summary"); });
  act(() => { current = h.result.current.rewrite.rewriteLayerField(layer.id, "rules", "Rules"); });
  await act(async () => { h.requests[0].reject(new Error("old")); await old; });
  assert.equal(h.result.current.rewrite.rewritePendingKey, `${layer.id}:rules`);
  assert.equal(h.result.current.rewrite.rewriteError, "");
  await act(async () => { h.requests[1].resolve("new rules"); await current; });
  assert.equal(h.result.current.draft.sceneLayers[0].rules, "new rules");
});

test("selection change, scene import and unmount fence late replies", async () => {
  for (const change of ["selection", "import", "unmount"]) {
    const h = fixture(), layer = h.result.current.draft.sceneLayers[0]; let run;
    act(() => { run = h.result.current.rewrite.rewriteLayerField(layer.id, "summary", "Summary"); });
    act(() => {
      if (change === "selection") h.result.current.draft.selectSceneObject(layer.objects[0].id);
      if (change === "import") h.result.current.draft.applySceneImport({ sceneName: "new", sceneSummary: "new", sceneLayers: h.result.current.draft.sceneLayers, selectedLayerId: layer.id, collapsedLayerIds: [] }, "import", "other");
    });
    if (change === "unmount") h.unmount();
    await act(async () => { h.requests[0].resolve("stale"); await run; });
    assert.equal(h.result.current.draft.sceneLayers[0].summary, layer.summary);
    assert.equal(h.result.current.rewrite.lastRewrite, null);
    h.unmount();
  }
});

test("current failure is visible and never retries the provider automatically", async () => {
  const h = fixture(), layer = h.result.current.draft.sceneLayers[0]; let run;
  act(() => { run = h.result.current.rewrite.rewriteLayerField(layer.id, "summary", "Summary"); });
  await act(async () => { h.requests[0].reject(new Error("offline")); await run; });
  assert.match(h.result.current.rewrite.rewriteError, /offline/);
  assert.equal(h.result.current.rewrite.rewritePendingKey, "");
  assert.equal(h.requests.length, 1);
});
