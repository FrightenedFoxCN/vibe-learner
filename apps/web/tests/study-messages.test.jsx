import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
import { useStudyMessages } from "../hooks/use-study-messages.ts";
import { useStudyChatRecovery } from "../hooks/use-study-chat-recovery.ts";
import { createStudyOperationStore } from "../lib/study-operation-state.ts";
import { StudyAsyncViewFence } from "../lib/async-result-fence.ts";
import { ApiHttpError } from "../lib/http-error.ts";

afterEach(cleanup);
after(() => dom.window.close());
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}
const session = { id: "s", planId: "p", studyUnitId: "u", revision: 4 };
function fixture({ delaySession = false } = {}) {
  const values = new Map();
  const store = createStudyOperationStore(() => ({ getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }));
  const writes = [], queries = [], applied = [], cleared = [], notices = [], openings = [];
  const view = new StudyAsyncViewFence({ session });
  const port = { sendStudyMessage: input => { const pending = deferred(); writes.push({ input, ...pending }); return pending.promise; },
    getStudyChatOperation: input => { const pending = deferred(); queries.push({ input, ...pending }); return pending.promise; } };
  const h = renderHook(() => {
    const recovery = useStudyChatRecovery({ session: view.session, view, getSelectedPlanId: () => "p",
      onExchange: result => { applied.push(result); view.activateSession(result.session); }, onSession() {}, onResetView() {}, onNotice: value => notices.push(value) }, { ...port, listStudySessions: async () => [] }, store);
    const messages = useStudyMessages({ view, recovery, ensureSessionForSection: () => {
      const pending = deferred(); openings.push(pending); if (!delaySession) pending.resolve(view.session); return pending.promise;
    }, isDialogueInterruptedForSession: () => true, peekDeferredInteractiveCallbackPrefix: () => "Deferred answer", clearInterruptedDialogueState: id => cleared.push(id), onNotice: value => notices.push(value) }, port, store);
    return { ...messages, recovery };
  });
  const receipt = (status, requestId = writes.at(-1)?.input.clientRequestId) => ({ sessionId: "s", clientRequestId: requestId, status, safeToRetry: status === "not_committed",
    result: status === "committed" ? { session: { ...session, revision: 5 }, reply: "answer", citations: [], characterEvents: [] } : null });
  return { ...h, writes, queries, applied, cleared, notices, openings, store, view, receipt };
}

test("learner admission captures revision, attachments and deferred prefix, suppressing a duplicate during Session lookup", async () => {
  const h = fixture({ delaySession: true }); let send;
  const attachments = [new File(["content"], "notes.txt")];
  act(() => { send = h.result.current.handleAsk("question", attachments); });
  await act(async () => { assert.equal(await h.result.current.handleAsk("duplicate"), false); });
  assert.equal(h.openings.length, 1);
  await act(async () => { h.openings[0].resolve(session); });
  assert.equal(h.writes[0].input.expectedSessionRevision, 4);
  assert.equal(h.writes[0].input.hiddenMessagePrefix, "Deferred answer");
  assert.deepEqual(h.writes[0].input.attachments, attachments);
  await act(async () => { h.writes[0].resolve(h.receipt("committed")); assert.equal(await send, true); });
  assert.deepEqual(h.cleared, ["s"]);
  assert.equal(h.store.readPendingStudyOperation(), null);
  assert.equal(h.result.current.isSending, false);
});

test("ambiguous POST failure blocks new writes and recovery queries the original request", async () => {
  const h = fixture(); let send;
  await act(async () => { send = h.result.current.handleAsk("question"); });
  await act(async () => { h.writes[0].reject(new Error("network lost")); assert.equal(await send, false); });
  assert.equal(h.result.current.recovery.chatFailure.canQuery, true);
  await act(async () => { assert.equal(await h.result.current.handleAsk("again"), false); await h.result.current.retryFailedAsk(); });
  assert.equal(h.writes.length, 1);
  let query;
  act(() => { query = h.result.current.recovery.queryStudyChatOperation(); });
  assert.equal(h.queries[0].input.clientRequestId, h.writes[0].input.clientRequestId);
  await act(async () => { h.queries[0].resolve(h.receipt("committed")); await query; });
  assert.equal(h.applied.length, 1);
});

test("definite pre-admission rejection requires Session refresh and retains the learner draft", async () => {
  const h = fixture(); let send;
  await act(async () => { send = h.result.current.handleAsk("retain me"); });
  await act(async () => { h.writes[0].reject(new ApiHttpError({ status: 409, code: "study_chat_session_revision_conflict", message: "conflict", payload: {} })); await send; });
  const failure = h.result.current.recovery.chatFailure;
  assert.equal(failure.message, "retain me");
  assert.equal(failure.canRefreshSession, true);
  assert.equal(failure.canResend, false);
  assert.equal(h.store.readPendingStudyOperation(), null);
});

test("leaving during Session lookup never starts a POST", async () => {
  const h = fixture({ delaySession: true }); let send;
  act(() => { send = h.result.current.handleAsk("question"); });
  h.unmount();
  await act(async () => { h.openings[0].resolve(session); assert.equal(await send, false); });
  assert.equal(h.writes.length, 0);
});

test("late committed POST cannot update a different Session or clear its interruption", async () => {
  const h = fixture(); let send;
  await act(async () => { send = h.result.current.handleAsk("question"); });
  h.view.activateSession({ ...session, id: "other" });
  await act(async () => { h.writes[0].resolve(h.receipt("committed")); assert.equal(await send, false); });
  assert.deepEqual(h.applied, []);
  assert.deepEqual(h.cleared, []);
});

test("automatic retries query a retained identity and forget it only after safe not-committed evidence", async () => {
  const h = fixture();
  const first = h.result.current.automaticStudyRequest("prelude:s:u:4", "prelude");
  const identity = h.result.current.automaticStudyRequest("prelude:s:u:4", "prelude");
  assert.equal(identity.queryExisting, true);
  let send;
  act(() => { send = h.result.current.sendHiddenSessionMessage({ session, ...identity, operationKey: "prelude:s:u:4", message: "hidden", messageKind: "session_prelude" }).catch(error => String(error)); });
  assert.equal(h.writes.length, 0);
  await act(async () => { h.queries[0].resolve(h.receipt("not_committed", identity.clientRequestId)); assert.match(await send, /not_committed/); });
  const next = h.result.current.automaticStudyRequest("prelude:s:u:4", "prelude");
  assert.notEqual(next.clientRequestId, first.clientRequestId);
  assert.equal(next.queryExisting, false);
});


test("callback diagnostic ancestry reaches sends and query retries without entering durable admission state", async () => {
  const h = fixture(); let send;
  const key = "callback:s:t:4";
  const first = h.result.current.automaticStudyRequest(key, "callback");
  act(() => { send = h.result.current.sendHiddenSessionMessage({ session, ...first, operationKey: key, message: "hidden answer", messageKind: "interactive_callback", diagnosticFlowId: "answer-flow" }).catch(String); });
  assert.equal(h.writes[0].input.diagnosticFlowId, "answer-flow");
  assert.equal(Object.hasOwn(h.store.readPendingStudyOperation(), "diagnosticFlowId"), false);
  await act(async () => { h.writes[0].reject(Error("network lost")); await send; });
  const retry = h.result.current.automaticStudyRequest(key, "callback");
  assert.equal(retry.clientRequestId, first.clientRequestId);
  act(() => { send = h.result.current.sendHiddenSessionMessage({ session, ...retry, operationKey: key, message: "hidden answer", messageKind: "interactive_callback", diagnosticFlowId: "answer-flow" }); });
  assert.equal(h.queries[0].input.diagnosticFlowId, "answer-flow");
  await act(async () => { h.queries[0].resolve(h.receipt("committed", first.clientRequestId)); await send; });
  assert.equal(h.writes.length, 1);
});
