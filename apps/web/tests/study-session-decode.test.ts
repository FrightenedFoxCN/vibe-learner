import assert from "node:assert/strict";
import test from "node:test";

import type { DialogueTurnRecord } from "@vibe-learner/shared";

import {
  decodeStudySessionCommittedIdentity,
  isStudySessionDecodeError,
  orderStudySessionTurns,
  resolveStudyChatFailurePresentation,
  resolveStudySessionErrorNotice,
  StudySessionDecodeError,
} from "../lib/study-session-decode.ts";

function wireTurn(id: string, sequence: number) {
  return { id, sequence };
}

function wireSession(turns = [wireTurn("turn-1", 1), wireTurn("turn-2", 2)]) {
  return {
    revision: 4,
    last_turn_sequence: turns.length,
    turns,
  };
}

test("Study Session committed identity decoder accepts contiguous unique turns", () => {
  assert.deepEqual(decodeStudySessionCommittedIdentity(wireSession()), {
    revision: 4,
    lastTurnSequence: 2,
    turns: [wireTurn("turn-1", 1), wireTurn("turn-2", 2)],
  });
});

test("Study Session committed identity decoder fails closed on missing watermarks", () => {
  const missingRevision = { ...wireSession() } as Record<string, unknown>;
  delete missingRevision.revision;
  assert.throws(
    () => decodeStudySessionCommittedIdentity(missingRevision),
    (error: unknown) =>
      error instanceof StudySessionDecodeError && error.path === "study_session.revision",
  );

  const missingTurnWatermark = { ...wireSession() } as Record<string, unknown>;
  delete missingTurnWatermark.last_turn_sequence;
  assert.throws(
    () => decodeStudySessionCommittedIdentity(missingTurnWatermark),
    (error: unknown) =>
      error instanceof StudySessionDecodeError &&
      error.path === "study_session.last_turn_sequence",
  );
});

test("Study Session committed identity decoder rejects invalid numeric projections", () => {
  for (const revision of [Number.NaN, 1.5, -1, "4"]) {
    assert.throws(
      () => decodeStudySessionCommittedIdentity({ ...wireSession(), revision }),
      StudySessionDecodeError,
    );
  }
  assert.throws(
    () => decodeStudySessionCommittedIdentity({ ...wireSession(), last_turn_sequence: 1 }),
    (error: unknown) =>
      error instanceof StudySessionDecodeError &&
      error.path === "study_session.last_turn_sequence",
  );
});

test("Study Session committed identity decoder rejects duplicate, empty, or gapped turns", () => {
  for (const turns of [
    [wireTurn("turn-1", 1), wireTurn("turn-1", 2)],
    [wireTurn("", 1)],
    [wireTurn("turn-2", 2)],
    [wireTurn("turn-1", 1), wireTurn("turn-3", 3)],
  ]) {
    assert.throws(
      () => decodeStudySessionCommittedIdentity(wireSession(turns)),
      StudySessionDecodeError,
    );
  }
});

test("Study Session display ordering follows sequence rather than timestamps", () => {
  const base = {
    learnerMessage: "question",
    assistantReply: "answer",
    citations: [],
    characterEvents: [],
  };
  const laterCommit: DialogueTurnRecord = {
    ...base,
    id: "turn-2",
    sequence: 2,
    createdAt: "2026-08-12T00:00:00Z",
  };
  const earlierCommit: DialogueTurnRecord = {
    ...base,
    id: "turn-1",
    sequence: 1,
    createdAt: "2026-08-12T00:00:01Z",
  };
  assert.deepEqual(
    orderStudySessionTurns([laterCommit, earlierCommit]).map((turn) => turn.id),
    ["turn-1", "turn-2"],
  );
});

test("Study Session decode failures use safe user notices and retain generic fallbacks", () => {
  const decodeError = new StudySessionDecodeError("study_session.revision", "expected_integer");
  assert.equal(isStudySessionDecodeError(decodeError), true);
  const historyNotice = resolveStudySessionErrorNotice(
    decodeError,
    `载入失败：${String(decodeError)}`,
    "history",
  );
  assert.match(historyNotice, /历史学习会话格式异常/);
  assert.doesNotMatch(historyNotice, /StudySessionDecodeError|study_session\.revision/);

  const responseNotice = resolveStudySessionErrorNotice(decodeError, "发送失败", "response");
  assert.match(responseNotice, /不要重复发送本次消息/);
  assert.doesNotMatch(responseNotice, /StudySessionDecodeError|study_session\.revision/);

  assert.equal(
    resolveStudySessionErrorNotice(new Error("offline"), "网络连接失败", "update"),
    "网络连接失败",
  );
});

test("Study Session decode failures never expose a retryable chat failure", () => {
  const decodeError = new StudySessionDecodeError(
    "study_session.turns[0].sequence",
    "expected_contiguous_sequence_1",
  );
  assert.equal(resolveStudyChatFailurePresentation(decodeError), null);

  const ordinaryFailure = resolveStudyChatFailurePresentation(new Error("network_offline"));
  assert.deepEqual(ordinaryFailure, {
    detail: "Error: network_offline",
    retryAllowed: true,
  });
});
