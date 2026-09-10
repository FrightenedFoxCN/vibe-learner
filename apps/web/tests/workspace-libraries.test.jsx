import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useWorkspaceLibraries } from "../hooks/use-workspace-libraries.ts";
import { PERSONA_LIBRARY_UPDATED_EVENT } from "../lib/persona-library-sync.ts";

afterEach(cleanup);
after(() => dom.window.close());
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function fixture() {
  const scenes = [], personas = [], applied = [];
  const port = { listSceneLibrary: () => { const pending = deferred(); scenes.push(pending); return pending.promise; }, listPersonas: () => { const pending = deferred(); personas.push(pending); return pending.promise; } };
  const options = { initialSceneId: "selected", onPersonas: value => applied.push(value) };
  return { ...renderHook(props => useWorkspaceLibraries(props, port), { initialProps: options }), scenes, personas, applied, options };
}

test("newer Scene refresh wins and selection uses the latest user choice", async () => {
  const h = fixture(); let refresh;
  act(() => { refresh = h.result.current.refreshSceneLibrary(); h.result.current.setSelectedSceneLibraryId("chosen"); });
  await act(async () => { h.scenes[1].resolve([{ sceneId: "chosen" }, { sceneId: "other" }]); await refresh; h.scenes[0].resolve([{ sceneId: "stale" }]); });
  assert.equal(h.result.current.selectedSceneLibraryId, "chosen");
  assert.deepEqual(h.result.current.sceneLibraryItems.map(item => item.sceneId), ["chosen", "other"]);
});

test("temporary Scene failure preserves known library and selection", async () => {
  const h = fixture();
  await act(async () => { h.scenes[0].resolve([{ sceneId: "selected" }]); });
  let refresh;
  act(() => { refresh = h.result.current.refreshSceneLibrary(); });
  await act(async () => { h.scenes[1].reject(new Error("offline")); await refresh; });
  assert.equal(h.result.current.selectedSceneLibraryId, "selected");
  assert.equal(h.result.current.sceneLibraryItems.length, 1);
});

test("Persona refresh suppresses stale results and applies through the current owner callback", async () => {
  const h = fixture(); let first, second;
  act(() => { first = h.result.current.refreshPersonaLibrary(); second = h.result.current.refreshPersonaLibrary(); });
  h.rerender({ ...h.options, onPersonas: value => h.applied.push(["current", value]) });
  await act(async () => { h.personas[1].resolve([{ id: "new" }]); await second; h.personas[0].resolve([{ id: "old" }]); await first; });
  assert.deepEqual(h.applied, [["current", [{ id: "new" }]]]);
});

test("library events belong to the mounted learning owner and unmount discards responses", async () => {
  const h = fixture();
  act(() => window.dispatchEvent(new Event(PERSONA_LIBRARY_UPDATED_EVENT)));
  assert.equal(h.personas.length, 1);
  h.unmount();
  await act(async () => { h.personas[0].resolve([{ id: "old" }]); h.scenes[0].resolve([{ sceneId: "old" }]); });
  window.dispatchEvent(new Event(PERSONA_LIBRARY_UPDATED_EVENT));
  assert.equal(h.personas.length, 1);
  assert.deepEqual(h.applied, []);
  await h.result.current.refreshSceneLibrary();
  assert.equal(h.scenes.length, 1);
});
