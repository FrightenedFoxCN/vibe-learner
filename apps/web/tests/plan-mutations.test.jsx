import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { usePlanMutations } from "../hooks/use-plan-mutations.ts";

afterEach(cleanup);
after(() => dom.window.close());
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function fixture() {
  const calls = [], events = [];
  const port = Object.fromEntries([
    "updateLearningPlanTitle", "deleteLearningPlan", "updateDocumentStudyUnitTitle",
    "updateLearningPlanProgress", "answerLearningPlanQuestion",
  ].map(name => [name, (...args) => { const pending = deferred(); calls.push({ name, args, ...pending }); return pending.promise; }]));
  const options = {
    plans: [{ id: "p", revision: 7 }],
    onPlan: plan => events.push(["plan", plan]), onDeleted: id => events.push(["delete", id]),
    onDocumentAndPlans: payload => events.push(["document", payload]), onNotice: notice => events.push(["notice", notice]),
  };
  return { ...renderHook(props => usePlanMutations(props, port), { initialProps: options }), calls, events, options };
}

test("invalid edits never write and a plan write blocks conflicting writes until settled", async () => {
  const h = fixture();
  await act(async () => {
    assert.equal(await h.result.current.renamePlanTitle("p", "  "), false);
    assert.equal(await h.result.current.updatePlanProgress({ planId: "p", scheduleIds: [], status: "done" }), false);
    assert.equal(await h.result.current.answerPlanQuestion({ planId: "p", questionId: "q", answer: " " }), false);
  });
  assert.equal(h.calls.length, 0);
  let edit;
  act(() => { edit = h.result.current.renamePlanTitle("p", "  Edited  "); });
  await act(async () => { assert.equal(await h.result.current.removePlan("p"), false); });
  assert.deepEqual(h.calls[0].args, ["p", "Edited", 7]);
  assert.equal(h.calls.length, 1);
  await act(async () => { h.calls[0].resolve({ id: "p", courseTitle: "Edited" }); assert.equal(await edit, true); });
  assert.equal(h.result.current.isMutating, false);
  assert.deepEqual(h.events[0], ["plan", { id: "p", courseTitle: "Edited" }]);
});

test("different resources retain busy state until all finish and old errors cannot replace latest feedback", async () => {
  const h = fixture(); let first, second;
  act(() => { first = h.result.current.renamePlanTitle("p", "first"); second = h.result.current.removePlan("other"); });
  await act(async () => { h.calls[1].resolve(); await second; });
  assert.equal(h.result.current.isMutating, true);
  await act(async () => { h.calls[0].reject(new Error("late failure")); assert.equal(await first, false); });
  assert.equal(h.result.current.isMutating, false);
  assert.deepEqual(h.events, [["delete", "other"], ["notice", "计划已删除。"]]);
});

test("delete projects into the latest workspace callback after navigation", async () => {
  const h = fixture(); let remove;
  act(() => { remove = h.result.current.removePlan("old"); });
  h.rerender({ ...h.options, onDeleted: id => h.events.push(["new selection retained", id]) });
  await act(async () => { h.calls[0].resolve(); await remove; });
  assert.deepEqual(h.events[0], ["new selection retained", "old"]);
});

test("unmount suppresses abandoned projections and does not retry a committed write", async () => {
  const h = fixture(); let save;
  act(() => { save = h.result.current.renameStudyUnitTitle("doc", "unit", "  Unit  "); });
  h.unmount();
  await act(async () => { h.calls[0].resolve({ document: { id: "doc" }, plans: [] }); assert.equal(await save, false); });
  assert.deepEqual(h.calls[0].args, ["doc", "unit", "Unit"]);
  assert.equal(h.calls.length, 1);
  assert.deepEqual(h.events, []);
});

test("unit updates apply document and plans together; progress and answers use authoritative plan responses", async () => {
  const h = fixture(); let pending;
  const payload = { document: { id: "doc" }, plans: [{ id: "p" }] };
  act(() => { pending = h.result.current.renameStudyUnitTitle("doc", "unit", "Unit"); });
  await act(async () => { h.calls[0].resolve(payload); await pending; });
  assert.deepEqual(h.events[0], ["document", payload]);
  for (const [name, input] of [
    ["updatePlanProgress", { planId: "p", scheduleIds: ["s"], status: "completed", note: "done" }],
    ["answerPlanQuestion", { planId: "p", questionId: "q", answer: "answer" }],
  ]) {
    act(() => { pending = h.result.current[name](input); });
    assert.deepEqual(h.calls.at(-1).args, [{ ...input, expectedRevision: 7 }]);
    await act(async () => { h.calls.at(-1).resolve({ id: "p", overview: name }); await pending; });
    assert.deepEqual(h.events.at(-2), ["plan", { id: "p", overview: name }]);
  }
});
