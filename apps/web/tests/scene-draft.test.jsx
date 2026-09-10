import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useSceneDraft } from "../hooks/use-scene-draft.ts";
import { INITIAL_SCENE } from "../lib/scene-editor-model.ts";
import { saveClock } from "./support/save-clock.js";

afterEach(cleanup);
after(() => dom.window.close());
const saved = () => ({ sceneName: "saved scene", sceneSummary: "summary", sceneLayers: structuredClone(INITIAL_SCENE), selectedLayerId: "missing", collapsedLayerIds: ["missing", INITIAL_SCENE[0].id] });
function fixture(initial = null) {
  const writes = [], notices = [], clock = saveClock();
  const storage = { read: () => initial, write: value => writes.push(value) };
  const view = renderHook(() => useSceneDraft({ onSelectionChange() {}, onImported() {}, onNotice: value => notices.push(value) }, storage, clock));
  return { ...view, writes, notices, clock };
}

test("local hydration normalizes selection and does not overwrite the saved draft with defaults", () => {
  const h = fixture(saved());
  assert.equal(h.result.current.sceneName, "saved scene");
  assert.equal(h.result.current.selectedLayerId, INITIAL_SCENE[0].id);
  assert.deepEqual(h.result.current.collapsedLayerIds, [INITIAL_SCENE[0].id]);
  h.clock.tick(699); assert.equal(h.writes.length, 0);
  h.clock.tick(1); assert.equal(h.writes.length, 1);
  assert.equal(h.writes[0].sceneName, "saved scene");
});

test("rapid edit then unmount flushes the latest draft before debounce", () => {
  const h = fixture(saved());
  act(() => h.result.current.updateSceneGenerationInput(() => h.result.current.setSceneName("latest edit")));
  h.clock.tick(100);
  h.unmount();
  assert.equal(h.writes.length, 1);
  assert.equal(h.writes[0].sceneName, "latest edit");
  h.clock.tick(1000); assert.equal(h.writes.length, 1);
});

test("pagehide flushes current selection and does not duplicate a successful write on unmount", () => {
  const h = fixture(saved());
  const object = h.result.current.sceneLayers[0].objects[0];
  act(() => h.result.current.selectSceneObject(object.id));
  act(() => window.dispatchEvent(new window.Event("pagehide")));
  assert.equal(h.writes[0].selectedLayerId, INITIAL_SCENE[0].id);
  assert.equal(h.result.current.currentSceneAsyncScope().fieldTarget, `scene-object:${object.id}`);
  h.unmount(); assert.equal(h.writes.length, 1);
});

test("edits and imports advance the async scope and imports replace its subject", () => {
  const h = fixture();
  const before = h.result.current.currentSceneAsyncScope();
  act(() => h.result.current.updateSceneLayersState(layers => layers.map(layer => ({ ...layer, summary: "edited" }))));
  assert.equal(h.result.current.currentSceneAsyncScope().draftRevision, before.draftRevision + 1);
  act(() => h.result.current.applySceneImport(saved(), "imported", "scene-library:stored"));
  const after = h.result.current.currentSceneAsyncScope();
  assert.equal(after.subjectId, "scene-library:stored");
  assert.equal(after.draftRevision, before.draftRevision + 2);
});

test("invalid stored draft leaves the default editor usable with an explicit notice", () => {
  const h = fixture({ broken: true });
  assert.equal(h.result.current.sceneName, "示例场景");
  assert.match(h.notices[0], /解析失败/);
  act(() => h.result.current.selectSceneLayer(INITIAL_SCENE[0].id));
  assert.ok(h.result.current.selectedLayer);
});
