import assert from "node:assert/strict";
import { test } from "node:test";
import { createStudyOperationStore, presentStudyChatOperation } from "../lib/study-operation-state.ts";

function fixture() {
  const values = new Map(); let sequence = 0;
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key) };
  return { values, storage, store: createStudyOperationStore(() => storage, scope => `${scope}-${++sequence}`) };
}
const identity = { sessionId: "s", clientRequestId: "r", expectedSessionRevision: 2, studyUnitId: "u", messageKind: "learner" };

test("pending persistence contains identity only and stale receipt cannot erase a newer request", () => {
  const h = fixture();
  h.store.persistPendingStudyOperation({ ...identity, message: "private text", attachments: ["private file"] });
  assert.deepEqual(h.store.readPendingStudyOperation(), identity);
  assert.equal([...h.values.values()][0].includes("private"), false);
  h.store.persistPendingStudyOperation({ ...identity, clientRequestId: "new" });
  h.store.clearPendingStudyOperation(identity);
  assert.equal(h.store.readPendingStudyOperation().clientRequestId, "new");
  h.store.clearPendingStudyOperation({ ...identity, clientRequestId: "new" });
  assert.equal(h.store.readPendingStudyOperation(), null);
});

test("automatic identities are reused across a fresh page and only explicitly forgotten identities can be generated again", () => {
  const h = fixture();
  const first = h.store.getOrCreateAutomaticRequestId(new Map(), "prelude:s:u:2", "prelude");
  assert.equal(first.queryExisting, false);
  const secondStore = createStudyOperationStore(() => h.storage, () => { throw new Error("must query"); });
  assert.deepEqual(secondStore.getOrCreateAutomaticRequestId(new Map(), "prelude:s:u:2", "prelude"), { ...first, queryExisting: true });
  h.store.forgetAutomaticStudyRequestId(new Map(), "prelude:s:u:2");
  assert.notEqual(h.store.getOrCreateAutomaticRequestId(new Map(), "prelude:s:u:2", "prelude").clientRequestId, first.clientRequestId);
});

test("storage denial preserves in-memory automatic identity and malformed pending state cannot restore", () => {
  const store = createStudyOperationStore(() => { throw new Error("blocked storage"); }, () => "memory-id");
  const map = new Map();
  assert.equal(store.getOrCreateAutomaticRequestId(map, "key", "scope").queryExisting, false);
  assert.equal(store.getOrCreateAutomaticRequestId(map, "key", "scope").queryExisting, true);
  assert.equal(store.readPendingStudyOperation(), null);
  assert.doesNotThrow(() => store.persistPendingStudyOperation(identity));
  const h = fixture(); h.store.persistPendingStudyOperation(identity);
  const key = [...h.values.keys()][0];
  for (const value of ["{", "null", JSON.stringify({ ...identity, expectedSessionRevision: -1 }), JSON.stringify({ ...identity, sessionId: "" })]) {
    h.values.set(key, value);
    assert.equal(h.store.readPendingStudyOperation(), null);
  }
});

test("retry eligibility requires explicit not-committed evidence", () => {
  for (const status of ["admitted", "running", "uncertain", "committed"]) {
    assert.equal(presentStudyChatOperation({ status, safeToRetry: true }).canResend, false);
  }
  assert.equal(presentStudyChatOperation({ status: "uncertain", safeToRetry: false }).canQuery, true);
  assert.equal(presentStudyChatOperation({ status: "not_committed", safeToRetry: false }).canResend, false);
  assert.equal(presentStudyChatOperation({ status: "not_committed", safeToRetry: true }).canResend, true);
});
