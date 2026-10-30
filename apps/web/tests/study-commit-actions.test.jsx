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
  const promise = new Promise((yes, no) => {
    resolve = yes;
    reject = no;
  });
  return { promise, resolve, reject };
}
function fixture() {
  const view = new StudyAsyncViewFence({ session: session() });
  const writes = [],
    applied = [],
    forgotten = [],
    notices = [];
  const port = Object.fromEntries(
    ["submitStudyQuestionAttempt", "resolveStudyPlanConfirmation"].map((name) => [
      name,
      (input, context) => {
        const pending = deferred();
        writes.push({ name, input, context, ...pending });
        return pending.promise;
      },
    ]),
  );
  const h = renderHook(() =>
    useStudyCommitActions(
      {
        view,
        automaticStudyRequest: () => ({
          clientRequestId: "client-attempt-1",
          queryExisting: false,
        }),
        forgetAutomaticStudyRequest: (key) => forgotten.push(key),
        onSession: (value) => {
          applied.push(["session", value]);
          view.activateSession(value);
        },
        onPlan: (value) => applied.push(["plan", value]),
        onNotice: (value) => notices.push(value),
      },
      port,
    ),
  );
  function committed(before = session()) {
    const next = structuredClone(before);
    const receipt = attempt({
      sessionId: before.id,
      turnId: before.turns[0].id,
      beforeRevision: before.revision,
      committedRevision: before.revision + 1,
    });
    commitAttempt(next, receipt);
    return { session: next, attempt: receipt };
  }
  return { ...h, view, writes, applied, forgotten, notices, committed };
}
const answer = { turnId: "turn-1", submittedAnswer: "A" };

test("answer submission deduplicates a Turn and stops after matching persisted read-back", async () => {
  const h = fixture();
  let save;
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
    null,
  );
  act(() => {
    save = h.result.current.handleSubmitQuestionAttempt(answer);
  });
  await act(async () => {
    assert.equal(await h.result.current.handleSubmitQuestionAttempt(answer), false);
  });
  assert.equal(h.writes.length, 1);
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
    null,
  );
  assert.deepEqual(h.writes[0].input, {
    sessionId: "session-1",
    turnId: "turn-1",
    expectedSessionRevision: 4,
    clientAttemptId: "client-attempt-1",
    submittedAnswer: "A",
  });
  const committed = h.committed();
  await act(async () => {
    h.writes[0].resolve(committed);
    assert.equal(await save, true);
  });
  assert.ok(h.writes[0].context.flow_id);
  h.rerender();
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
    h.writes[0].context.flow_id,
  );
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("other-session", "turn-1"),
    null,
  );
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "other-turn"),
    null,
  );
  assert.deepEqual(h.notices, ["答案已记录。需要进一步讲解时，可选择“生成答题讲解”。"]);
  assert.equal(h.forgotten.length, 1);
});

test("mismatched result never projects an answer or offers continuation", async () => {
  const h = fixture();
  let save;
  act(() => {
    save = h.result.current.handleSubmitQuestionAttempt(answer);
  });
  const committed = h.committed();
  committed.session.turns[0].interactiveQuestion.result.submittedAnswer = "B";
  await act(async () => {
    h.writes[0].resolve(committed);
    assert.equal(await save, false);
  });
  assert.deepEqual(h.applied, []);
  assert.match(h.notices[0], /记录答案失败/);
  assert.equal(h.forgotten.length, 0);
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
    null,
  );
});

test("a committed answer in a previous Session remains persisted without changing the new view", async () => {
  const h = fixture();
  let save;
  act(() => {
    save = h.result.current.handleSubmitQuestionAttempt(answer);
  });
  h.view.activateSession({ ...session(), id: "other" });
  await act(async () => {
    h.writes[0].resolve(h.committed());
    assert.equal(await save, true);
  });
  assert.equal(h.view.session.id, "other");
  assert.deepEqual(h.applied, []);
  assert.deepEqual(h.notices, []);
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
    null,
  );
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("other", "turn-1"),
    null,
  );
});

test("unmount suppresses answer notices and confirmation projection", async () => {
  const h = fixture();
  let answerSave, confirmation;
  act(() => {
    answerSave = h.result.current.handleSubmitQuestionAttempt(answer);
    confirmation = h.result.current.handleResolvePlanConfirmation({
      confirmationId: "c",
      decision: "approve",
    });
  });
  h.unmount();
  await act(async () => {
    h.writes[0].resolve(h.committed());
    h.writes[1].resolve({ session: session(), plan: { id: "p" } });
    await Promise.all([answerSave, confirmation]);
  });
  assert.deepEqual(h.applied, []);
  assert.deepEqual(h.notices, []);
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
    null,
  );
});

test("confirmation deduplicates writes and a stale read-back cannot lower the current Session", async () => {
  const h = fixture();
  let save;
  const input = { confirmationId: "c", decision: "approve", note: "Confirmed" };
  act(() => {
    save = h.result.current.handleResolvePlanConfirmation(input);
  });
  await act(async () => {
    assert.equal(await h.result.current.handleResolvePlanConfirmation(input), false);
  });
  assert.deepEqual(h.writes[0].input, { sessionId: "session-1", ...input });
  h.view.activateSession({ ...session(), revision: 9 });
  await act(async () => {
    h.writes[0].resolve({ session: { ...session(), revision: 5 }, plan: { id: "p" } });
    assert.equal(await save, false);
  });
  assert.equal(h.writes.length, 1);
  assert.deepEqual(h.applied, []);
  assert.equal(h.result.current.isApplying, false);
});

test("current confirmation applies the Session and Plan returned by persistence", async () => {
  const h = fixture();
  let save;
  act(() => {
    save = h.result.current.handleResolvePlanConfirmation({
      confirmationId: "c",
      decision: "approve",
    });
  });
  const updated = {
    session: { ...session(), revision: 5 },
    plan: { id: "p", overview: "Confirmed plan" },
  };
  await act(async () => {
    h.writes[0].resolve(updated);
    assert.equal(await save, true);
  });
  assert.deepEqual(h.applied, [
    ["session", updated.session],
    ["plan", updated.plan],
  ]);
});

test("switching Study Unit within the same Session prevents the old answer from replacing navigation", async () => {
  const h = fixture();
  let save;
  act(() => {
    save = h.result.current.handleSubmitQuestionAttempt(answer);
  });
  h.view.activateSession({ ...session(), studyUnitId: "next-unit", revision: 6 });
  await act(async () => {
    h.writes[0].resolve(h.committed());
    assert.equal(await save, true);
  });
  assert.equal(h.view.session.studyUnitId, "next-unit");
  assert.deepEqual(h.applied, []);
  assert.deepEqual(h.notices, []);
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
    null,
  );
});

test("diagnostic ID failure does not change a committed answer or its explicit continuation notice", async () => {
  const h = fixture();
  let save;
  const descriptor = Object.getOwnPropertyDescriptor(globalThis, "crypto");
  try {
    Object.defineProperty(globalThis, "crypto", {
      configurable: true,
      value: {
        randomUUID() {
          throw Error("diagnostic entropy denied");
        },
      },
    });
    act(() => {
      save = h.result.current.handleSubmitQuestionAttempt(answer);
    });
    await act(async () => {
      h.writes[0].resolve(h.committed());
      assert.equal(await save, true);
    });
    assert.equal(h.applied.length, 1);
    assert.equal(h.writes[0].context.flow_id, null);
    assert.equal(
      h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
      null,
    );
    assert.deepEqual(h.notices, [
      "答案已记录。需要进一步讲解时，可选择“生成答题讲解”。",
    ]);
  } finally {
    if (descriptor) Object.defineProperty(globalThis, "crypto", descriptor);
    else delete globalThis.crypto;
  }
});

test("a failed submission keeps its retry identity but cannot supply the retry's diagnostic flow", async () => {
  const h = fixture();
  let first, retry;
  act(() => {
    first = h.result.current.handleSubmitQuestionAttempt(answer);
  });
  const failedFlow = h.writes[0].context.flow_id;
  assert.ok(failedFlow);
  await act(async () => {
    h.writes[0].reject(new Error("attempt transport failed"));
    assert.equal(await first, false);
  });
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
    null,
  );
  assert.deepEqual(h.forgotten, []);
  act(() => {
    retry = h.result.current.handleSubmitQuestionAttempt(answer);
  });
  assert.equal(h.writes[1].input.clientAttemptId, h.writes[0].input.clientAttemptId);
  assert.ok(h.writes[1].context.flow_id);
  assert.notEqual(h.writes[1].context.flow_id, failedFlow);
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
    null,
  );
  await act(async () => {
    h.writes[1].resolve(h.committed());
    assert.equal(await retry, true);
  });
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
    h.writes[1].context.flow_id,
  );
  assert.equal(h.forgotten.length, 1);
});

for (const [name, corrupt] of [
  [
    "a different Session projection",
    (value) => {
      value.session.id = "foreign-session";
    },
  ],
  [
    "a receipt for another Session",
    (value) => {
      value.attempt.sessionId = "foreign-session";
    },
  ],
  [
    "a receipt for another Turn",
    (value) => {
      value.attempt.turnId = "foreign-turn";
    },
  ],
  [
    "a revision preceding the committed receipt",
    (value) => {
      value.session.revision = 4;
    },
  ],
  [
    "a changed immutable Turn",
    (value) => {
      value.session.turns[0].assistantReply = "unrelated reply";
    },
  ],
]) {
  test(`${name} cannot register diagnostic correlation`, async () => {
    const h = fixture();
    let save;
    act(() => {
      save = h.result.current.handleSubmitQuestionAttempt(answer);
    });
    const value = h.committed();
    corrupt(value);
    await act(async () => {
      h.writes[0].resolve(value);
      assert.equal(await save, false);
    });
    for (const [sessionId, turnId] of [
      ["session-1", "turn-1"],
      ["foreign-session", "turn-1"],
      ["session-1", "foreign-turn"],
    ])
      assert.equal(
        h.result.current.getQuestionAttemptDiagnosticFlowId(sessionId, turnId),
        null,
      );
    assert.deepEqual(h.applied, []);
    assert.deepEqual(h.forgotten, []);
    assert.equal(h.result.current.isApplying, false);
  });
}

test("a newer authoritative Session can confirm correlation without projecting an older read-back", async () => {
  const h = fixture();
  let save;
  act(() => {
    save = h.result.current.handleSubmitQuestionAttempt(answer);
  });
  const value = h.committed();
  const current = { ...structuredClone(value.session), revision: 6 };
  h.view.activateSession(current);
  await act(async () => {
    h.writes[0].resolve(value);
    assert.equal(await save, true);
  });
  assert.equal(h.view.session, current);
  assert.deepEqual(h.applied, []);
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
    h.writes[0].context.flow_id,
  );
});

test("a newer Session lacking the committed attempt cannot supply correlation", async () => {
  const h = fixture();
  let save;
  act(() => {
    save = h.result.current.handleSubmitQuestionAttempt(answer);
  });
  const current = { ...session(), revision: 6 };
  h.view.activateSession(current);
  await act(async () => {
    h.writes[0].resolve(h.committed());
    assert.equal(await save, false);
  });
  assert.equal(h.view.session, current);
  assert.deepEqual(h.applied, []);
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
    null,
  );
});

test("leaving and returning to the same Session fences the old submission's correlation", async () => {
  const h = fixture();
  let save;
  act(() => {
    save = h.result.current.handleSubmitQuestionAttempt(answer);
  });
  h.view.activateSession({ ...session(), id: "other-session" });
  h.view.activateSession(session());
  await act(async () => {
    h.writes[0].resolve(h.committed());
    assert.equal(await save, true);
  });
  assert.deepEqual(h.applied, []);
  assert.deepEqual(h.notices, []);
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
    null,
  );
});

test("committed answers in different Sessions retain separate flows even with the same Turn ID", async () => {
  const h = fixture();
  let first, second;
  act(() => {
    first = h.result.current.handleSubmitQuestionAttempt(answer);
  });
  await act(async () => {
    h.writes[0].resolve(h.committed());
    assert.equal(await first, true);
  });
  const firstFlow = h.writes[0].context.flow_id;
  const other = { ...session(), id: "other-session" };
  h.view.activateSession(other);
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId(other.id, "turn-1"),
    null,
  );
  act(() => {
    second = h.result.current.handleSubmitQuestionAttempt(answer);
  });
  await act(async () => {
    h.writes[1].resolve(h.committed(other));
    assert.equal(await second, true);
  });
  const secondFlow = h.writes[1].context.flow_id;
  assert.ok(secondFlow);
  assert.notEqual(secondFlow, firstFlow);
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
    firstFlow,
  );
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId(other.id, "turn-1"),
    secondFlow,
  );
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId(other.id, "other-turn"),
    null,
  );
});

test("a plan confirmation with the same local identifier cannot impersonate a question attempt", async () => {
  const h = fixture();
  let save;
  act(() => {
    save = h.result.current.handleResolvePlanConfirmation({
      confirmationId: "turn-1",
      decision: "approve",
    });
  });
  await act(async () => {
    h.writes[0].resolve({ session: { ...session(), revision: 5 }, plan: null });
    assert.equal(await save, true);
  });
  assert.equal(h.applied.length, 1);
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId("session-1", "turn-1"),
    null,
  );
});

test("correlation retains at most 128 verified Session/Turn entries and failed writes cannot evict them", async () => {
  const h = fixture();
  const entries = [];
  async function saveNext(index) {
    const before = { ...session(), id: `bounded-session-${index}` };
    h.view.activateSession(before);
    let save;
    act(() => {
      save = h.result.current.handleSubmitQuestionAttempt(answer);
    });
    const write = h.writes.at(-1);
    assert.equal(
      h.result.current.getQuestionAttemptDiagnosticFlowId(before.id, answer.turnId),
      null,
    );
    await act(async () => {
      write.resolve(h.committed(before));
      assert.equal(await save, true);
    });
    assert.ok(write.context.flow_id);
    entries.push({ sessionId: before.id, flowId: write.context.flow_id });
  }
  for (let index = 0; index < 128; index += 1) await saveNext(index);
  for (const entry of entries)
    assert.equal(
      h.result.current.getQuestionAttemptDiagnosticFlowId(
        entry.sessionId,
        answer.turnId,
      ),
      entry.flowId,
    );
  h.view.activateSession({ ...session(), id: "failed-capacity-write" });
  let failed;
  act(() => {
    failed = h.result.current.handleSubmitQuestionAttempt(answer);
  });
  await act(async () => {
    h.writes.at(-1).reject(new Error("uncommitted answer"));
    assert.equal(await failed, false);
  });
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId(
      "failed-capacity-write",
      answer.turnId,
    ),
    null,
  );
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId(
      entries[0].sessionId,
      answer.turnId,
    ),
    entries[0].flowId,
  );
  await saveNext(128);
  assert.equal(
    h.result.current.getQuestionAttemptDiagnosticFlowId(
      entries[0].sessionId,
      answer.turnId,
    ),
    null,
  );
  for (const entry of entries.slice(1))
    assert.equal(
      h.result.current.getQuestionAttemptDiagnosticFlowId(
        entry.sessionId,
        answer.turnId,
      ),
      entry.flowId,
    );
  assert.equal(
    entries.filter(
      (entry) =>
        h.result.current.getQuestionAttemptDiagnosticFlowId(
          entry.sessionId,
          answer.turnId,
        ) !== null,
    ).length,
    128,
  );
});
