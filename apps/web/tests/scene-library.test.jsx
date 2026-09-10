import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useSceneLibrary } from "../hooks/use-scene-library.ts";

afterEach(cleanup);
after(() => dom.window.close());
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const scene = (id, revision = 1) => ({ sceneId: id, revision, sceneName: id });
function fixture(overrides = {}) {
  const scenes = deferred(), nodes = deferred(), writes = [];
  const port = {
    listSceneLibrary: () => scenes.promise, listReusableSceneNodes: () => nodes.promise,
    createSceneLibraryItem: async () => scene("created"),
    updateSceneLibraryItem: async (id, input) => { writes.push({ id, input }); return scene(id, input.expectedRevision + 1); },
    deleteSceneLibraryItem: async () => {},
    createReusableSceneNode: async () => ({ nodeId: "node" }), deleteReusableSceneNode: async () => {}, ...overrides,
  };
  return { ...renderHook(() => useSceneLibrary(port)), scenes, nodes, writes };
}

test("late initial list retains committed updates and does not resurrect deleted rows", async () => {
  const h = fixture();
  await act(async () => {
    await h.result.current.updateSceneLibraryItem("updated", { expectedRevision: 1 });
    await h.result.current.deleteSceneLibraryItem("deleted");
    h.scenes.resolve([scene("updated"), scene("deleted"), scene("other")]);
    h.nodes.resolve([]);
  });
  assert.deepEqual(h.result.current.savedScenes.map(item => [item.sceneId, item.revision]), [["updated", 2], ["other", 1]]);
  assert.equal(h.writes[0].input.expectedRevision, 1);
});

test("scene and reusable list failures are isolated", async () => {
  const h = fixture();
  await act(async () => { h.scenes.resolve([scene("available")]); h.nodes.reject(new Error("node list offline")); });
  assert.equal(h.result.current.savedScenes[0].sceneId, "available");
  assert.match(h.result.current.libraryError, /node list offline/);
});

test("completed create does not take selection back from a later user choice", async () => {
  const created = deferred(), h = fixture({ createSceneLibraryItem: () => created.promise }); let run;
  await act(async () => { h.scenes.resolve([scene("old"), scene("chosen")]); h.nodes.resolve([]); });
  act(() => { run = h.result.current.createSceneLibraryItem({}); });
  act(() => h.result.current.setSelectedSavedSceneId("chosen"));
  await act(async () => { created.resolve(scene("new")); await run; });
  assert.equal(h.result.current.selectedSavedSceneId, "chosen");
  assert.ok(h.result.current.savedScenes.some(item => item.sceneId === "new"));
});

test("concurrent writes to the same scene are rejected without another backend call", async () => {
  const pending = deferred(); let calls = 0;
  const h = fixture({ updateSceneLibraryItem: () => { calls++; return pending.promise; } }); let run;
  act(() => { run = h.result.current.updateSceneLibraryItem("same", { expectedRevision: 4 }); });
  await assert.rejects(h.result.current.updateSceneLibraryItem("same", { expectedRevision: 4 }), /write_in_progress/);
  await act(async () => { pending.resolve(scene("same", 5)); await run; });
  assert.equal(calls, 1);
});

test("older reusable action completion cannot clear the newer action feedback", async () => {
  const h = fixture(), old = deferred(), latest = deferred(); let first, second;
  act(() => { first = h.result.current.runReusableAction("old", "old saved", () => old.promise); });
  act(() => { second = h.result.current.runReusableAction("latest", "latest saved", () => latest.promise); });
  await act(async () => { old.reject(new Error("old failed")); await first; });
  assert.equal(h.result.current.reusableActionPendingId, "latest");
  assert.equal(h.result.current.reusableError, "");
  await act(async () => { latest.resolve(); await second; });
  assert.equal(h.result.current.reusableMessage, "latest saved");
  assert.equal(h.result.current.reusableActionPendingId, "");
});

test("unmount discards both late initial reads and committed mutation projections", async () => {
  const created = deferred(), h = fixture({ createSceneLibraryItem: () => created.promise }); let run;
  act(() => { run = h.result.current.createSceneLibraryItem({}); });
  h.unmount();
  await act(async () => { h.scenes.resolve([scene("late")]); h.nodes.resolve([]); created.resolve(scene("new")); await run; });
  assert.deepEqual(h.result.current.savedScenes, []);
  assert.equal(h.result.current.selectedSavedSceneId, "");
});
