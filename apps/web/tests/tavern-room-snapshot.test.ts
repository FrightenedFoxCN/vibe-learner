import assert from "node:assert/strict";
import test from "node:test";

import type { TavernRoomDetail, TavernRun } from "@vibe-learner/shared";

import {
  reduceTavernRoomSnapshot,
  type TavernRoomSnapshot,
  type TavernRoomSnapshotAction,
} from "../lib/tavern-room-snapshot.ts";
import { refreshTavernTranscript } from "../lib/tavern-transcript-refresh.ts";
import {
  createTavernPendingRecoveryBudget,
  tavernAutomaticRecoveryDelay,
  tavernPendingRecoveryBlocked,
} from "../lib/tavern-pending-recovery.ts";

test("pending recovery stops only for matching, explicitly blocked run evidence", () => {
  const blocked = {
    leafRun: { id: "run-a" },
    chainStatus: "active",
    recoveryAction: "none",
  } as const;
  assert.equal(tavernPendingRecoveryBlocked([blocked], "run-a"), true);
  assert.equal(tavernPendingRecoveryBlocked([blocked], "run-b"), false);
  assert.equal(tavernPendingRecoveryBlocked([], "run-a"), false);
  assert.equal(
    tavernPendingRecoveryBlocked(
      [{ ...blocked, recoveryAction: "wait_and_resume" }],
      "run-a",
    ),
    false,
  );
});

const now = "2026-01-01T00:00:00Z";
function page(
  id: string,
  first: number,
  end: number,
  before: number | null,
  revision = end,
): TavernRoomDetail {
  return {
    room: {
      id,
      title: id,
      status: "active",
      revision,
      lastSequence: end,
      createdAt: now,
      updatedAt: now,
      harnessPolicy: {
        version: "tavern-harness-v1",
        maxCharacterMessages: 4,
        maxReplyCharacters: 2000,
        contextMessageLimit: 30,
        preventSpeakerImpersonation: true,
      },
    },
    participants: [],
    messages: Array.from({ length: end - first + 1 }, (_, i) => ({
      id: id + "-message-" + (first + i),
      roomId: id,
      sequence: first + i,
      authorKind: "user",
      content: "fixture",
      emotion: "neutral",
      addressedParticipantIds: [],
      createdAt: now,
    })),
    messageCount: end,
    nextAfterSequence: null,
    nextBeforeSequence: before,
  };
}

function run(roomId: string, status: TavernRun["status"]): TavernRun {
  return {
    id: roomId + "-run",
    roomId,
    idempotencyKey: roomId + "-key",
    mode: "direct",
    triggerKind: "user_message",
    inputMessageId: null,
    scheduledParticipantIds: [],
    speakerSteps: [],
    guidance: "",
    status,
    expectedRoomRevision: 10,
    generatedMessageIds: [],
    harnessTrace: [],
    terminalSequence: 10,
    createdAt: now,
  };
}

function apply(current: TavernRoomSnapshot | null, action: TavernRoomSnapshotAction) {
  const next = reduceTavernRoomSnapshot(current, action);
  assert.ok(next);
  return next;
}

function open(detail: TavernRoomDetail, runs: TavernRun[] | null = []) {
  return apply(null, { kind: "open", detail, runs, recovery: [] });
}

const first = () => page("a", 8, 10, 8);
const sequences = (snapshot: TavernRoomSnapshot) =>
  snapshot.detail.messages.map((message) => message.sequence);

test("room switch rejects late results from an abandoned room", async () => {
  const a = open(first(), [run("a", "pending")]);
  const b = open(page("b", 1, 2, null));
  const refresh = await Promise.resolve(page("a", 8, 11, 8));
  const actions: TavernRoomSnapshotAction[] = [
    {
      kind: "refresh",
      detail: refresh,
      initial: a.detail,
      transcript: refresh,
      runs: [],
      recovery: [],
      ownsRecovery: true,
    },
    { kind: "archive", detail: refresh },
    {
      kind: "turn",
      result: {
        roomState: refresh.room,
        run: run("a", "completed"),
        inputMessage: null,
        generatedMessages: [],
      },
    },
    { kind: "older", roomId: "a", requestedBefore: 8, detail: page("a", 1, 7, null) },
    { kind: "poll", roomId: "a", runs: [run("a", "completed")] },
    { kind: "recovery", roomId: "a", chains: [] },
  ];
  for (const action of actions) assert.equal(apply(b, action), b, action.kind);
});

test("refresh rebases onto an older page that lands while bridging", async () => {
  const a = open(first());
  const tail = page("a", 13, 15, 13);
  let resolveBridge!: (detail: TavernRoomDetail) => void;
  const bridge = new Promise<TavernRoomDetail>((resolve) => {
    resolveBridge = resolve;
  });
  const prepared = refreshTavernTranscript(a.detail, tail, (after, count) => {
    assert.equal(after, 10);
    assert.equal(count, 2);
    return bridge;
  });
  const older = apply(a, {
    kind: "older",
    roomId: "a",
    requestedBefore: 8,
    detail: page("a", 5, 7, 5),
  });
  resolveBridge(page("a", 11, 12, null));
  const next = apply(older, {
    kind: "refresh",
    detail: tail,
    initial: a.detail,
    transcript: await prepared,
    runs: [],
    recovery: [],
    ownsRecovery: true,
  });
  assert.equal(next.detail.nextBeforeSequence, 5);
  assert.equal(next.detail.room.revision, 15);
  assert.deepEqual(sequences(next), [5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15]);
});

test("a fresh tail drops disjoint old history and rejects the old page cursor", async () => {
  const a = open(first());
  const tail = page("a", 300, 303, 300);
  const prepared = await refreshTavernTranscript(a.detail, tail, () =>
    assert.fail("bridge exceeds limit"),
  );
  const pageResponse = {
    kind: "older",
    roomId: "a",
    requestedBefore: 8,
    detail: page("a", 5, 7, 5),
  } as const;
  const older = apply(a, pageResponse);
  const next = apply(older, {
    kind: "refresh",
    detail: tail,
    initial: a.detail,
    transcript: prepared,
    runs: [],
    recovery: [],
    ownsRecovery: true,
  });
  assert.deepEqual(sequences(next), [300, 301, 302, 303]);
  assert.equal(next.detail.nextBeforeSequence, 300);
  assert.equal(apply(next, pageResponse), next);
});

test("failed run read keeps prior evidence but does not equate unknown with empty", () => {
  const a = open(first(), [run("a", "pending")]);
  const detail = page("a", 8, 11, 8);
  const action = {
    kind: "refresh",
    detail,
    initial: a.detail,
    transcript: detail,
    recovery: null,
    ownsRecovery: true,
  } as const;
  const unknown = apply(a, { ...action, runs: null });
  assert.equal(unknown.runs, a.runs);
  assert.equal(unknown.runsKnown, false);
  assert.equal(unknown.recoveryKnown, false);
  assert.equal(unknown.detail.room.lastSequence, 11);
  const poll = apply(unknown, {
    kind: "poll",
    roomId: "a",
    runs: [run("a", "completed")],
  });
  assert.equal(poll.runsKnown, false);
  const empty = apply(unknown, { ...action, runs: [], recovery: [] });
  assert.equal(empty.runsKnown, true);
  assert.deepEqual(empty.runs, []);
  assert.equal(empty.recoveryKnown, true);
  assert.equal(open(detail, null).runsKnown, false);
});

test("terminal runs, newer details and newer recovery are not regressed", () => {
  const a = open(first(), [run("a", "pending")]);
  const detail = page("a", 8, 11, 8);
  const done = apply(a, {
    kind: "turn",
    result: {
      roomState: detail.room,
      run: run("a", "completed"),
      inputMessage: null,
      generatedMessages: detail.messages.slice(-1),
    },
  });
  const poll = apply(done, { kind: "poll", roomId: "a", runs: [run("a", "pending")] });
  assert.equal(poll.runs[0].status, "completed");
  assert.equal(
    apply(poll, {
      kind: "refresh",
      initial: a.detail,
      transcript: a.detail,
      detail: a.detail,
      runs: [],
      recovery: [],
      ownsRecovery: true,
    }),
    poll,
  );
  assert.deepEqual(sequences(poll), [8, 9, 10, 11]);
  const refresh = apply(poll, {
    kind: "refresh",
    initial: poll.detail,
    transcript: detail,
    detail,
    runs: null,
    recovery: null,
    ownsRecovery: false,
  });
  assert.equal(refresh.runsKnown, true);
  assert.equal(refresh.recoveryKnown, true);
});

test("pending resume has a per-run budget, backs off, and allows a manual attempt after exhaustion", () => {
  const budget = createTavernPendingRecoveryBudget();
  let progress;
  for (const delay of [2500, 5000, 10000]) {
    assert.equal(tavernAutomaticRecoveryDelay(progress), delay);
    const started = budget.begin("a-run", "automatic");
    assert.ok(started);
    assert.equal(tavernAutomaticRecoveryDelay(started), null);
    assert.equal(budget.begin("a-run", "automatic"), null);
    assert.equal(budget.begin("a-run", "manual"), null);
    // Failure/lease conflict/pending reply all consume exactly one attempt.
    progress = budget.finish("a-run");
  }
  assert.equal(tavernAutomaticRecoveryDelay(progress), null);
  assert.equal(budget.begin("a-run", "automatic"), null);
  assert.equal(budget.begin("b-run", "automatic")?.automaticAttempts, 1);
  assert.equal(budget.begin("a-run", "manual")?.automaticAttempts, 3);
  assert.equal(tavernAutomaticRecoveryDelay(budget.finish("a-run")), null);
  assert.equal(budget.begin("a-run", "automatic"), null);
});

test("a lost resume response is recovered by reading committed records, without duplicating the input", async () => {
  const pending = run("a", "pending");
  const before = open(first(), [pending]);
  const after = page("a", 10, 11, 10);
  const transcript = await refreshTavernTranscript(before.detail, after, () =>
    assert.fail("the server tail already overlaps the committed transcript"),
  );
  const completed = apply(before, {
    kind: "refresh",
    detail: after,
    initial: before.detail,
    transcript,
    runs: [run("a", "completed")],
    recovery: [],
    ownsRecovery: true,
  });
  assert.deepEqual(sequences(completed), [8, 9, 10, 11]);
  assert.deepEqual(
    completed.runs.map(({ id, status }) => [id, status]),
    [[pending.id, "completed"]],
  );
});

test("replaying creation of the visible room preserves unknown Run status and cursor", () => {
  const unknown = open(first(), null);
  const replayed = apply(unknown, { kind: "created", detail: page("a", 8, 11, 8) });
  assert.equal(replayed.runsKnown, false);
  assert.equal(replayed.detail.nextBeforeSequence, 8);
  assert.deepEqual(sequences(replayed), [8, 9, 10, 11]);
  const newRoom = apply(replayed, { kind: "created", detail: page("b", 1, 1, null) });
  assert.equal(newRoom.runsKnown, true);
  assert.deepEqual(newRoom.runs, []);
});
