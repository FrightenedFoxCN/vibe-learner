import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useStudySessionNavigation } from "../hooks/use-study-session-navigation.ts";
import { StudyAsyncViewFence } from "../lib/async-result-fence.ts";

afterEach(cleanup);
after(() => dom.window.close());
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const plan = { id: "p", documentId: "", personaId: "mentor", studyUnits: [{ id: "u", title: "Unit" }], schedule: [], studyUnitProgress: [], objective: "Learn" };
const session = { id: "s", planId: "p", personaId: "mentor", studyUnitId: "u", revision: 1, updatedAt: "2026-09-10T00:00:00Z" };
function fixture() {
  const calls = [], sessions = [], notices = [];
  const view = new StudyAsyncViewFence({ initialPlanId: "p" });
  const port = Object.fromEntries(["listStudySessions", "createStudySession", "updateStudySessionStudyUnit"].map(name => [name, input => {
    const pending = deferred(); calls.push({ name, input, ...pending }); return pending.promise;
  }]));
  const options = { plan, document: null, view, getSelectedPlanId: () => "p", resolveSceneProfile: () => ({ sceneId: "initial" }),
    resolveStudyUnitTitle: id => id, resolveThemeHint: () => "Theme",
    onTransition: (target, clear) => view.transition(target, clear),
    onSession: value => { sessions.push(value); if (value) view.activateSession(value); else view.session = null; }, onNotice: value => notices.push(value) };
  return { ...renderHook(props => useStudySessionNavigation(props, port), { initialProps: options }), calls, sessions, notices, view, options };
}

test("goal-only history restores the newest Session without creating one", async () => {
  const h = fixture();
  assert.deepEqual(h.calls[0].input, { documentId: undefined, personaId: "mentor", planId: "p" });
  await act(async () => { h.calls[0].resolve([{ ...session, id: "old", updatedAt: "2026-09-09T00:00:00Z" }, session]); });
  assert.equal(h.sessions[0].id, "s");
  assert.equal(h.calls.length, 1);
});

test("explicit creation supersedes late history and duplicate create is suppressed", async () => {
  const h = fixture(); let create;
  act(() => { create = h.result.current.createSessionForActivePlan(); });
  await act(async () => { await h.result.current.createSessionForActivePlan(); });
  assert.equal(h.calls.length, 2);
  await act(async () => { h.calls[1].resolve({ ...session, id: "created" }); await create; });
  await act(async () => { h.calls[0].resolve([session]); });
  assert.deepEqual(h.sessions.map(item => item.id), ["created"]);
  assert.equal(h.result.current.isNavigating, false);
});

test("switching Plan discards old history and creation results", async () => {
  const h = fixture(); let create;
  act(() => { create = h.result.current.createSessionForActivePlan(); });
  h.view.transition("study-plan:other", true);
  h.rerender({ ...h.options, plan: { ...plan, id: "other" }, getSelectedPlanId: () => "other" });
  await act(async () => { h.calls[0].resolve([session]); h.calls[1].resolve(session); await create; h.calls[2].resolve([]); });
  assert.deepEqual(h.sessions, [null]);
  assert.equal(h.notices.length, 0);
});

test("rapid A B A selection reuses the A write and suppresses obsolete queued B", async () => {
  const h = fixture();
  await act(async () => { h.calls[0].resolve([session]); });
  let first, second, repeated;
  await act(async () => { first = h.result.current.handleSwitchSection("a"); });
  act(() => { second = h.result.current.handleSwitchSection("b"); repeated = h.result.current.handleSwitchSection("a"); });
  assert.equal(first, repeated);
  assert.equal(h.calls[1].input.studyUnitId, "a");
  await act(async () => { h.calls[1].resolve({ ...session, studyUnitId: "a", revision: 2 }); await Promise.all([first, second]); });
  assert.equal(h.calls.length, 2);
  assert.equal(h.sessions.at(-1).studyUnitId, "a");
});

test("Scene is captured before a history lookup and switching away stops follow-on creation", async () => {
  const h = fixture();
  await act(async () => { h.calls[0].resolve([]); });
  let ensure;
  act(() => { ensure = h.result.current.ensureSessionForSection("u"); });
  h.rerender({ ...h.options, resolveSceneProfile: () => ({ sceneId: "later" }) });
  await act(async () => { h.calls[1].resolve([]); });
  assert.equal(h.calls[2].input.sceneProfile.sceneId, "initial");
  await act(async () => { h.calls[2].resolve(session); await ensure; });
  h.view.transition("empty", true);
  act(() => { ensure = h.result.current.ensureSessionForSection("another"); });
  h.unmount();
  await act(async () => { h.calls[3].resolve([]); assert.equal(await ensure, null); });
  assert.equal(h.calls.length, 4);
});

test("late history cannot lower a Session revision already visible in the same view", async () => {
  const h = fixture();
  h.view.session = { ...session, revision: 9 };
  await act(async () => { h.calls[0].resolve([session]); });
  assert.deepEqual(h.sessions, []);
  assert.equal(h.view.session.revision, 9);
});
