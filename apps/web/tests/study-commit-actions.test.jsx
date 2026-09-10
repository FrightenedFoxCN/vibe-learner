import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useStudyCommitActions } from "../hooks/use-study-commit-actions.ts";
import { StudyAsyncViewFence } from "../lib/async-result-fence.ts";
import { session, attempt, commitAttempt } from "./support/study-attempts.ts";

afterEach(cleanup);
after(() => dom.window.close());
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
function fixture() {
  const view = new StudyAsyncViewFence({ session: session() });
  const writes = [], applied = [], callbacks = [], forgotten = [], notices = [];
  const port = Object.fromEntries(["submitStudyQuestionAttempt", "resolveStudyPlanConfirmation"].map(name => [name, input => {
    const pending = deferred(); writes.push({ name, input, ...pending }); return pending.promise;
  }]));
  const h = renderHook(() => useStudyCommitActions({ view,
    automaticStudyRequest: () => ({ clientRequestId: "client-attempt-1", queryExisting: false }),
    forgetAutomaticStudyRequest: key => forgotten.push(key),
    onSession: value => { applied.push(["session", value]); view.activateSession(value); },
    onPlan: value => applied.push(["plan", value]),
    onCommittedQuestion: async (value, input) => { callbacks.push({ value, input }); }, onNotice: value => notices.push(value),
  }, port));
  function committed() { const next = session(), receipt = attempt(); commitAttempt(next, receipt); return { session: next, attempt: receipt }; }
  return { ...h, view, writes, applied, callbacks, forgotten, notices, committed };
}
const answer = { turnId: "turn-1", submittedAnswer: "A" };

test("answer submission deduplicates a Turn and calls back only from matching persisted read-back", async () => {
  const h = fixture(); let save;
  act(() => { save = h.result.current.handleSubmitQuestionAttempt(answer); });
  await act(async () => { assert.equal(await h.result.current.handleSubmitQuestionAttempt(answer), false); });
  assert.equal(h.writes.length, 1);
  assert.deepEqual(h.writes[0].input, { sessionId: "session-1", turnId: "turn-1", expectedSessionRevision: 4, clientAttemptId: "client-attempt-1", submittedAnswer: "A" });
  assert.equal(h.callbacks.length, 0);
  const committed = h.committed();
  await act(async () => { h.writes[0].resolve(committed); assert.equal(await save, true); });
  assert.equal(h.callbacks[0].value, committed.session);
  assert.deepEqual(h.callbacks[0].input, { turnId: "turn-1" });
  assert.equal(h.forgotten.length, 1);
});

test("mismatched result never projects an answer or triggers a follow-up", async () => {
  const h = fixture(); let save;
  act(() => { save = h.result.current.handleSubmitQuestionAttempt(answer); });
  const committed = h.committed(); committed.session.turns[0].interactiveQuestion.result.submittedAnswer = "B";
  await act(async () => { h.writes[0].resolve(committed); assert.equal(await save, false); });
  assert.deepEqual(h.applied, []);
  assert.deepEqual(h.callbacks, []);
  assert.equal(h.forgotten.length, 0);
});

test("a committed answer in a previous Session remains persisted without changing the new view", async () => {
  const h = fixture(); let save;
  act(() => { save = h.result.current.handleSubmitQuestionAttempt(answer); });
  h.view.activateSession({ ...session(), id: "other" });
  await act(async () => { h.writes[0].resolve(h.committed()); assert.equal(await save, true); });
  assert.equal(h.view.session.id, "other");
  assert.deepEqual(h.applied, []);
  assert.deepEqual(h.callbacks, []);
});

test("unmount suppresses answer callbacks and confirmation projection", async () => {
  const h = fixture(); let answerSave, confirmation;
  act(() => { answerSave = h.result.current.handleSubmitQuestionAttempt(answer); confirmation = h.result.current.handleResolvePlanConfirmation({ confirmationId: "c", decision: "approve" }); });
  h.unmount();
  await act(async () => { h.writes[0].resolve(h.committed()); h.writes[1].resolve({ session: session(), plan: { id: "p" } }); await Promise.all([answerSave, confirmation]); });
  assert.deepEqual(h.applied, []);
  assert.deepEqual(h.callbacks, []);
  assert.deepEqual(h.notices, []);
});

test("confirmation deduplicates writes and a stale read-back cannot lower the current Session", async () => {
  const h = fixture(); let save;
  const input = { confirmationId: "c", decision: "approve", note: "Confirmed" };
  act(() => { save = h.result.current.handleResolvePlanConfirmation(input); });
  await act(async () => { assert.equal(await h.result.current.handleResolvePlanConfirmation(input), false); });
  assert.deepEqual(h.writes[0].input, { sessionId: "session-1", ...input });
  h.view.activateSession({ ...session(), revision: 9 });
  await act(async () => { h.writes[0].resolve({ session: { ...session(), revision: 5 }, plan: { id: "p" } }); assert.equal(await save, false); });
  assert.equal(h.writes.length, 1);
  assert.deepEqual(h.applied, []);
  assert.equal(h.result.current.isApplying, false);
});

test("current confirmation applies the Session and Plan returned by persistence", async () => {
  const h = fixture(); let save;
  act(() => { save = h.result.current.handleResolvePlanConfirmation({ confirmationId: "c", decision: "approve" }); });
  const updated = { session: { ...session(), revision: 5 }, plan: { id: "p", overview: "Confirmed plan" } };
  await act(async () => { h.writes[0].resolve(updated); assert.equal(await save, true); });
  assert.deepEqual(h.applied, [["session", updated.session], ["plan", updated.plan]]);
});


test("switching Study Unit within the same Session prevents the old answer from replacing navigation", async () => {
  const h = fixture(); let save;
  act(() => { save = h.result.current.handleSubmitQuestionAttempt(answer); });
  h.view.activateSession({ ...session(), studyUnitId: "next-unit", revision: 6 });
  await act(async () => { h.writes[0].resolve(h.committed()); assert.equal(await save, true); });
  assert.equal(h.view.session.studyUnitId, "next-unit");
  assert.deepEqual(h.applied, []);
  assert.deepEqual(h.callbacks, []);
});
