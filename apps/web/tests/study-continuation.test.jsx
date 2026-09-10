import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useStudyContinuation } from "../hooks/use-study-continuation.ts";
import { StudyAsyncViewFence } from "../lib/async-result-fence.ts";
import { session as questionSession, attempt, commitAttempt } from "./support/study-attempts.ts";

afterEach(cleanup);
after(() => dom.window.close());
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function fixture({ prepared = true, pendingOperation = false, followUp = false } = {}) {
  const session = questionSession();
  session.preparedStudyUnitIds = prepared ? [session.studyUnitId] : [];
  session.pendingFollowUps = followUp ? [{ id: "follow", dueAt: "2026-09-10T00:00:01Z", status: "pending", hiddenMessage: "Next" }] : [];
  const view = new StudyAsyncViewFence({ session });
  const timers = new Map(), messages = [], cancellations = [], applied = [], notices = [], callbacks = [];
  const state = { paused: "", pendingOperation }; let timerId = 0;
  const port = {
    cancelStudySessionFollowUps: input => { const pending = deferred(); cancellations.push({ input, ...pending }); return pending.promise; },
    readInterruptedDialogueSessionId: () => state.paused, writeInterruptedDialogueSessionId: id => { state.paused = id; },
    appendDeferredInteractiveCallback: (id, message) => callbacks.push({ id, message }), readDeferredInteractiveCallbacks: id => callbacks.filter(item => item.id === id).map(item => item.message),
    clearDeferredInteractiveCallbacks: id => { for (let i = callbacks.length - 1; i >= 0; i--) if (callbacks[i].id === id) callbacks.splice(i, 1); },
    hasPendingOperation: () => state.pendingOperation,
    now: () => Date.parse("2026-09-10T00:00:00Z"), setTimeout: (callback, delay) => { const id = ++timerId; timers.set(id, { callback, delay }); return id; }, clearTimeout: id => timers.delete(id),
  };
  const props = { session, view, busy: false, ensureSessionForSection: async () => view.session,
    sendHiddenSessionMessage: input => { const pending = deferred(); messages.push({ input, ...pending }); return pending.promise; },
    automaticStudyRequest: key => ({ clientRequestId: key, queryExisting: false }), onSession: value => { applied.push(value); view.activateSession(value); }, onNotice: value => notices.push(value) };
  const h = renderHook(options => useStudyContinuation(options, port), { initialProps: props });
  const fireTimer = () => { const [id, timer] = [...timers.entries()][0]; timers.delete(id); timer.callback(); };
  return { ...h, props, session, view, timers, messages, cancellations, applied, notices, callbacks, state, fireTimer };
}

test("failed automatic prelude is not retried on busy changes; explicit retry uses its scoped operation", async () => {
  const h = fixture({ prepared: false });
  assert.equal(h.messages.length, 1);
  await act(async () => { h.messages[0].reject(new Error("uncertain")); });
  h.rerender({ ...h.props, busy: true }); h.rerender(h.props);
  assert.equal(h.messages.length, 1);
  let retry;
  await act(async () => { retry = h.result.current.triggerSessionPrelude({ studyUnitId: "unit-1" }); });
  assert.equal(h.messages[1].input.operationKey, "prelude:session-1:unit-1:4");
  await act(async () => { h.messages[1].reject(new Error("still failed")); assert.equal(await retry, false); });
});

test("a pending operation prevents restored unprepared Session from starting another automatic message", () => {
  const h = fixture({ prepared: false, pendingOperation: true, followUp: true });
  assert.equal(h.messages.length, 0);
  act(() => h.fireTimer());
  assert.equal(h.messages.length, 0);
});

test("follow-up timer uses the latest Session revision and is not rescheduled by its own failure feedback", async () => {
  const h = fixture({ followUp: true });
  assert.equal([...h.timers.values()][0].delay, 1000);
  h.view.activateSession({ ...h.session, revision: 7 });
  act(() => h.fireTimer());
  assert.equal(h.messages[0].input.session.revision, 7);
  await act(async () => { h.messages[0].reject(new Error("uncertain")); });
  assert.equal(h.timers.size, 0);
  assert.equal(h.messages.length, 1);
});

test("changing Session clears old timers and unmount prevents their retained callbacks from sending", () => {
  const h = fixture({ followUp: true });
  const callback = [...h.timers.values()][0].callback;
  const next = { ...h.session, id: "other", pendingFollowUps: [] };
  h.view.activateSession(next); h.rerender({ ...h.props, session: next });
  assert.equal(h.timers.size, 0);
  h.unmount(); callback();
  assert.equal(h.messages.length, 0);
});

test("interrupt clears timers before persistence and a late cancel result cannot pause a different Session", async () => {
  const h = fixture({ followUp: true }); let cancel;
  act(() => { cancel = h.result.current.interruptDialogue(); });
  assert.equal(h.timers.size, 0);
  await act(async () => { assert.equal(await h.result.current.interruptDialogue(), false); });
  const next = { ...h.session, id: "other", pendingFollowUps: [] };
  h.view.activateSession(next); h.rerender({ ...h.props, session: next });
  await act(async () => { h.cancellations[0].resolve({ ...h.session, revision: 5, pendingFollowUps: [] }); assert.equal(await cancel, false); });
  assert.deepEqual(h.applied, []);
  assert.equal(h.state.paused, "");
});

test("paused answer callbacks use only committed grading and are retained for the next learner message", async () => {
  const h = fixture();
  await act(async () => { await h.result.current.interruptDialogue(); await h.result.current.triggerInteractiveQuestionCallback(h.session, { turnId: "turn-1" }); });
  assert.equal(h.callbacks.length, 0);
  const committed = structuredClone(h.session); commitAttempt(committed, attempt());
  h.view.activateSession(committed);
  await act(async () => { await h.result.current.triggerInteractiveQuestionCallback(committed, { turnId: "turn-1" }); });
  assert.equal(h.messages.length, 0);
  assert.match(h.result.current.peekDeferredInteractiveCallbackPrefix(committed.id), /学习者答案：A/);
  const consumed = h.result.current.peekDeferredInteractiveCallbackPrefix(committed.id);
  act(() => h.result.current.clearInterruptedDialogueState(committed.id, consumed));
  assert.equal(h.callbacks.length, 0);
  assert.equal(h.state.paused, "");
});

test("active answer callback sends the committed result and never invents missing grading", async () => {
  const h = fixture(); const committed = structuredClone(h.session); commitAttempt(committed, attempt());
  h.view.activateSession(committed); let send;
  act(() => { send = h.result.current.triggerInteractiveQuestionCallback(committed, { turnId: "turn-1", diagnosticFlowId: "answer-flow" }); });
  assert.match(h.messages[0].input.message, /判定：正确/);
  assert.equal(h.messages[0].input.operationKey, "callback:session-1:turn-1:5");
  assert.equal(h.messages[0].input.diagnosticFlowId, "answer-flow");
  await act(async () => { h.messages[0].resolve({ status: "committed" }); await send; });
});


test("a learner commit consumes only callbacks captured before its request, preserving answers queued in flight", async () => {
  const h = fixture();
  await act(async () => { await h.result.current.interruptDialogue(); });
  h.callbacks.push({ id: h.session.id, message: "old answer" });
  const prefix = h.result.current.peekDeferredInteractiveCallbackPrefix(h.session.id);
  h.callbacks.push({ id: h.session.id, message: "new answer" });
  act(() => h.result.current.clearInterruptedDialogueState(h.session.id, prefix));
  assert.equal(h.result.current.peekDeferredInteractiveCallbackPrefix(h.session.id), "new answer");
  assert.equal(h.state.paused, h.session.id);
  act(() => h.result.current.clearInterruptedDialogueState(h.session.id, ""));
  assert.equal(h.callbacks.length, 1);
});
