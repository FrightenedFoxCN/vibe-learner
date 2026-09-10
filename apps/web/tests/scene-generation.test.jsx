import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useSceneGeneration } from "../hooks/use-scene-generation.ts";
import { INITIAL_SCENE } from "../lib/scene-editor-model.ts";

afterEach(cleanup);
after(() => dom.window.close());
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const reply = name => ({ sceneName: name, sceneSummary: "summary", sceneLayers: structuredClone(INITIAL_SCENE), selectedLayerId: INITIAL_SCENE[0].id, mode: "keywords", usedModel: "fixture-model", usedWebSearch: false, modelRecoveries: [] });
function fixture() {
  const scope = { subjectId: "local", draftRevision: 0 }, requests = [];
  const view = renderHook(() => useSceneGeneration(fieldTarget => ({ ...scope, fieldTarget }), input => {
    const pending = deferred(); requests.push({ input, ...pending }); return pending.promise;
  }));
  act(() => view.result.current.setSceneKeywordInput("library"));
  return { ...view, scope, requests };
}

test("slow file read cannot issue a request after a newer generation has started", async () => {
  const h = fixture(), file = deferred(); let old, latest;
  act(() => h.result.current.setSceneLongTextFile({ text: () => file.promise }));
  act(() => { old = h.result.current.handleGenerateScene("long_text"); });
  act(() => { latest = h.result.current.handleGenerateScene("keywords"); });
  await act(async () => { file.resolve("older file"); await old; });
  assert.equal(h.requests.length, 1);
  assert.equal(h.requests[0].input.mode, "keywords");
  assert.equal(h.result.current.sceneGeneratePending, "keywords");
  await act(async () => { h.requests[0].resolve(reply("latest")); await latest; });
  assert.equal(h.result.current.generatedSceneCandidate.sceneName, "latest");
});

test("outdated generation failure and finally do not overwrite newer state", async () => {
  const h = fixture(); let old, latest;
  act(() => { old = h.result.current.handleGenerateScene("keywords"); });
  act(() => { latest = h.result.current.handleGenerateScene("keywords"); });
  await act(async () => { h.requests[0].reject(new Error("old failure")); await old; });
  assert.equal(h.result.current.sceneGenerateError, "");
  assert.equal(h.result.current.sceneGeneratePending, "keywords");
  await act(async () => { h.requests[1].resolve(reply("latest")); await latest; });
  assert.equal(h.result.current.sceneGeneratePending, null);
});

test("draft edits or importing another scene prevent stale candidate application", async () => {
  for (const change of ["draft", "import"]) {
    const h = fixture(); let run;
    act(() => { run = h.result.current.handleGenerateScene("keywords"); });
    act(() => { change === "draft" ? h.scope.draftRevision++ : h.result.current.resetSceneGeneration(); });
    await act(async () => { h.requests[0].resolve(reply("old")); await run; });
    assert.equal(h.result.current.generatedSceneCandidate, null);
    assert.equal(h.result.current.sceneGeneratePending, null);
    h.unmount();
  }
});

test("unmount while reading a file suppresses the provider request", async () => {
  const h = fixture(), file = deferred(); let run;
  act(() => h.result.current.setSceneLongTextFile({ text: () => file.promise }));
  act(() => { run = h.result.current.handleGenerateScene("long_text"); });
  h.unmount();
  await act(async () => { file.resolve("text"); await run; });
  assert.equal(h.requests.length, 0);
});

test("invalid generation inputs do not call the provider; valid input produces a candidate", async () => {
  const h = fixture();
  act(() => h.result.current.setSceneGenerateLayerCount("0"));
  await act(async () => { await h.result.current.handleGenerateScene("keywords"); });
  assert.equal(h.requests.length, 0);
  assert.match(h.result.current.sceneGenerateError, /大于 0/);
  assert.equal(h.result.current.sceneGeneratePending, null);
  act(() => h.result.current.setSceneGenerateLayerCount("3"));
  let run;
  act(() => { run = h.result.current.handleGenerateScene("keywords"); });
  assert.deepEqual(h.requests[0].input, { mode: "keywords", inputText: "library", layerCount: 3 });
  await act(async () => { h.requests[0].resolve(reply("candidate")); await run; });
  assert.equal(h.result.current.generatedSceneCandidate.sceneName, "candidate");
  assert.equal(h.result.current.generatedSceneCandidate.usedModel, "fixture-model");
});
