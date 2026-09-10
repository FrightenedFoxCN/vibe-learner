import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, renderHook } from "@testing-library/react";
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
const session = { id: "s", planId: "p", personaId: "mentor", studyUnitId: "u", revision: 2, turns: [] };
const draft = { sessionId: "s", clientRequestId: "r", expectedSessionRevision: 2, studyUnitId: "u", messageKind: "learner", message: "question", attachments: [] };
function receipt(status, overrides = {}) {
  return { sessionId: "s", clientRequestId: "r", status, safeToRetry: status === "not_committed",
    result: status === "committed" ? { reply: "Answer", session: { ...session, revision: 3 } } : null, ...overrides };
}
function fixture({ pending = false } = {}) {
  const values = new Map();
  const store = createStudyOperationStore(() => ({ getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) }));
  if (pending) store.persistPendingStudyOperation(draft);
  const queries = [], reads = [], applied = [], notices = [];
  const view = new StudyAsyncViewFence({ session, initialPlanId: "p" });
  const props = { session, view, getSelectedPlanId: () => "p", onExchange: value => { applied.push(value); view.activateSession(value.session); }, onSession: value => applied.push({ session: value }), onResetView: () => view.transition("reset", true), onNotice: value => notices.push(value) };
  const port = { getStudyChatOperation: input => { const pending = deferred(); queries.push({ input, ...pending }); return pending.promise; }, listStudySessions: input => { const pending = deferred(); reads.push({ input, ...pending }); return pending.promise; } };
  return { ...renderHook(options => useStudyChatRecovery(options, port, store), { initialProps: props }), props, store, queries, reads, applied, notices, view };
}

test("refresh restores identity via query only and uncertain remains queryable without resend", async () => {
  const h = fixture({ pending: true });
  assert.equal(h.queries.length, 1);
  assert.equal(h.queries[0].input.clientRequestId, "r");
  await act(async () => { h.queries[0].resolve(receipt("uncertain")); });
  assert.equal(h.result.current.chatFailure.canQuery, true);
  assert.equal(h.result.current.chatFailure.canResend, false);
  let query;
  act(() => { query = h.result.current.queryStudyChatOperation(); });
  assert.equal(h.queries[1].input.clientRequestId, "r");
  await act(async () => { h.queries[1].resolve(receipt("committed")); assert.equal(await query, true); });
  assert.equal(h.applied[0].session.revision, 3);
  assert.equal(h.store.readPendingStudyOperation(), null);
  assert.equal(h.result.current.chatFailure, null);
});

test("late committed restore never overwrites another Session or clears a newer pending identity", async () => {
  const h = fixture({ pending: true });
  const next = { ...session, id: "other", studyUnitId: "other-unit" };
  h.view.activateSession(next);
  h.store.persistPendingStudyOperation({ ...draft, sessionId: "other", clientRequestId: "new" });
  h.rerender({ ...h.props, session: next });
  await act(async () => { h.queries[0].resolve(receipt("committed")); });
  assert.deepEqual(h.applied, []);
  assert.equal(h.store.readPendingStudyOperation().clientRequestId, "new");
});

test("unmount invalidates read-back while still clearing the exact confirmed pending request", async () => {
  const h = fixture({ pending: true });
  h.unmount();
  await act(async () => { h.queries[0].resolve(receipt("committed")); });
  assert.deepEqual(h.applied, []);
  assert.equal(h.store.readPendingStudyOperation(), null);
});

test("safe not-committed can resend only a retained learner draft, never restored empty input", async () => {
  const h = fixture({ pending: true });
  await act(async () => { h.queries[0].resolve(receipt("not_committed")); });
  assert.equal(h.result.current.chatFailure.canResend, false);
  act(() => { const ticket = h.result.current.beginStudyResponseTicket(draft); h.result.current.applyStudyChatOperation(receipt("not_committed"), draft, ticket); });
  assert.equal(h.result.current.chatFailure.canResend, true);
  assert.equal(h.queries.length, 1);
});

test("missing operation requires explicit Session refresh and does not automatically resubmit", async () => {
  const h = fixture({ pending: true });
  await act(async () => { h.queries[0].reject(new ApiHttpError({ status: 404, code: "study_chat_operation_not_found", message: "missing", payload: {} })); });
  assert.equal(h.result.current.chatFailure.canRefreshSession, true);
  assert.equal(h.result.current.chatFailure.canResend, false);
  assert.equal(h.reads.length, 0);
  let refresh;
  act(() => { refresh = h.result.current.refreshStudySessionAfterRejectedAdmission(); });
  await act(async () => { h.reads[0].resolve([{ ...session, revision: 5 }]); assert.equal(await refresh, true); });
  assert.equal(h.applied[0].session.revision, 5);
  assert.equal(h.result.current.chatFailure, null);
  assert.equal(h.queries.length, 1);
});

test("an older committed receipt cannot roll back a newer Session projection", () => {
  const h = fixture();
  h.view.activateSession({ ...session, revision: 7 });
  act(() => {
    const ticket = h.result.current.beginStudyResponseTicket(draft);
    assert.equal(h.result.current.applyStudyChatOperation(receipt("committed"), draft, ticket), true);
  });
  assert.deepEqual(h.applied, []);
  assert.equal(h.view.session.revision, 7);
});


test("terminal automatic-message receipts clear only their own pending identity", () => {
  for (const status of ["committed", "not_committed"]) {
    const h = fixture();
    const automatic = { ...draft, messageKind: "session_prelude" };
    h.store.persistPendingStudyOperation(automatic);
    act(() => {
      const ticket = h.result.current.beginStudyResponseTicket(automatic);
      h.result.current.applyStudyChatOperation(receipt(status), automatic, ticket);
    });
    assert.equal(h.store.readPendingStudyOperation(), null);
    h.unmount();
  }
});
