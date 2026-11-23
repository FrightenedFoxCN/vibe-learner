import assert from "node:assert/strict";
import test from "node:test";
import {
  isExactStudyCommit,
  whenStudyDraftCommitted,
} from "../lib/study-composer-receipt.ts";
import {
  appendDeferredInteractiveCallback,
  captureDeferredStudyCallbacks,
  commitDeferredStudyCallbacks,
  readDeferredInteractiveCallbacks,
  readInterruptedDialogueSessionId,
  writeInterruptedDialogueSessionId,
} from "../lib/study-dialogue-interruption.ts";
import { createStudyOperationStore } from "../lib/study-operation-state.ts";

const key = { sessionId: "study-session", clientRequestId: "study-operation" };
const committed = { ...key, status: "committed", result: { session: {} } };

function memoryStorage() {
  const values = new Map<string, string>();
  return {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => {
      values.set(key, value);
    },
    removeItem: (key: string) => {
      values.delete(key);
    },
  };
}

function withLocalStorage(run: (storage: ReturnType<typeof memoryStorage>) => void) {
  const storage = memoryStorage();
  const before = Object.getOwnPropertyDescriptor(globalThis, "localStorage");
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: storage,
  });
  try {
    run(storage);
  } finally {
    if (before) Object.defineProperty(globalThis, "localStorage", before);
    else Reflect.deleteProperty(globalThis, "localStorage");
  }
}

test("a recovered matching commit clears the unchanged draft once, not a new draft", () => {
  const version = { current: {} as object | null };
  let clears = 0;
  const consume = whenStudyDraftCommitted(version, () => {
    clears += 1;
  });
  for (const receipt of [
    { ...committed, status: "running", result: undefined },
    { ...committed, result: undefined },
    { ...committed, sessionId: "other" },
    { ...committed, clientRequestId: "other" },
  ])
    assert.equal(isExactStudyCommit(receipt, key), false);
  assert.equal(isExactStudyCommit(committed, key), true);
  consume();
  consume();
  assert.equal(clears, 1);
  version.current = {};
  const stale = whenStudyDraftCommitted(version, () => {
    clears += 1;
  });
  version.current = {};
  stale();
  version.current = null;
  stale();
  assert.equal(clears, 1);
});

test("reload restores only metadata and consumes exactly the committed deferred prefix", () => {
  withLocalStorage((storage) => {
    writeInterruptedDialogueSessionId(key.sessionId);
    appendDeferredInteractiveCallback(key.sessionId, "old explanation");
    const captured = captureDeferredStudyCallbacks(key.sessionId)!;
    assert.equal(captured.prefix, "old explanation");
    const before = createStudyOperationStore(() => storage);
    const draft = {
      ...key,
      expectedSessionRevision: 2,
      messageKind: "learner",
      message: "do not persist",
      deferredCallbackReceipt: captured.receipt,
    };
    before.persistPendingStudyOperation(draft);
    appendDeferredInteractiveCallback(key.sessionId, "later explanation");
    const restored = createStudyOperationStore(
      () => storage,
    ).readPendingStudyOperation()!;
    assert.equal("message" in restored, false);
    assert.deepEqual(restored.deferredCallbackReceipt, captured.receipt);
    assert.equal(isExactStudyCommit(committed, restored), true);
    assert.equal(
      commitDeferredStudyCallbacks(key.sessionId, restored.deferredCallbackReceipt!),
      true,
    );
    assert.equal(
      commitDeferredStudyCallbacks(key.sessionId, restored.deferredCallbackReceipt!),
      false,
    );
    assert.deepEqual(readDeferredInteractiveCallbacks(key.sessionId), [
      "later explanation",
    ]);
    assert.equal(readInterruptedDialogueSessionId(), key.sessionId);
    const next = captureDeferredStudyCallbacks(key.sessionId)!;
    assert.equal(commitDeferredStudyCallbacks(key.sessionId, next.receipt), true);
    assert.equal(readInterruptedDialogueSessionId(), "");
  });
});

test("a new interruption is not removed by an older commit, even with identical text", () => {
  withLocalStorage(() => {
    writeInterruptedDialogueSessionId(key.sessionId);
    appendDeferredInteractiveCallback(key.sessionId, "same named explanation");
    const first = captureDeferredStudyCallbacks(key.sessionId)!;
    writeInterruptedDialogueSessionId(key.sessionId);
    assert.equal(commitDeferredStudyCallbacks(key.sessionId, first.receipt), false);
    assert.deepEqual(readDeferredInteractiveCallbacks(key.sessionId), [
      "same named explanation",
    ]);
  });
});
