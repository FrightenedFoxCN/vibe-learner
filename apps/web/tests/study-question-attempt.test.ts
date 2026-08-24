import assert from "node:assert/strict";
import test from "node:test";

import type { StudySessionRecord } from "@vibe-learner/shared";

import {
  decodeStudyQuestionAttemptResponse,
  decideStudyQuestionAttemptApply,
  validateStudyQuestionAttemptReadBack,
  type StudyQuestionAttemptResponse,
} from "../lib/study-question-attempt.ts";

function session(): StudySessionRecord {
  return {
    id: "session-1",
    documentId: "doc-1",
    personaId: "persona-1",
    planId: null,
    sceneInstanceId: "",
    studyUnitId: "unit-1",
    studyUnitTitle: "Unit 1",
    themeHint: "",
    sessionSystemPrompt: "",
    status: "active",
    revision: 4,
    lastTurnSequence: 1,
    turns: [
      {
        id: "turn-1",
        sequence: 1,
        learnerMessage: "question",
        assistantReply: "answer",
        citations: [],
        characterEvents: [],
        interactiveQuestion: {
          schemaVersion: "study-interactive-question-v2",
          questionType: "multiple_choice",
          prompt: "Pick one",
          difficulty: "medium",
          topic: "topic",
          options: [{ key: "A", text: "A" }, { key: "B", text: "B" }],
          callBack: true,
          result: null,
        },
        createdAt: "2026-08-13T00:00:00Z",
      },
    ],
    preparedStudyUnitIds: [],
    pendingFollowUps: [],
    sessionMemory: [],
    affinityState: { score: 0, level: "neutral", summary: "", updatedAt: "", events: [] },
    planConfirmations: [],
    createdAt: "2026-08-13T00:00:00Z",
    updatedAt: "2026-08-13T00:00:00Z",
  };
}

function attempt(overrides: Partial<StudyQuestionAttemptResponse> = {}): StudyQuestionAttemptResponse {
  return {
    schemaVersion: "study-question-attempt-response-v1",
    attemptId: "attempt-1",
    clientAttemptId: "client-attempt-1",
    sessionId: "session-1",
    turnId: "turn-1",
    submittedAnswer: "A",
    isCorrect: true,
    feedbackText: "回答正确",
    explanation: "Because A",
    beforeRevision: 4,
    committedRevision: 5,
    committedAt: "2026-08-13T00:00:01Z",
    ...overrides,
  };
}

function commitAttempt(target: StudySessionRecord, committed: StudyQuestionAttemptResponse): void {
  target.revision = committed.committedRevision;
  target.updatedAt = committed.committedAt;
  target.turns[0]!.interactiveQuestion!.result = {
    schemaVersion: "study-question-result-v1",
    attemptId: committed.attemptId,
    clientAttemptId: committed.clientAttemptId,
    submittedAnswer: committed.submittedAnswer,
    isCorrect: committed.isCorrect,
    feedbackText: committed.feedbackText,
    explanation: committed.explanation,
    beforeRevision: committed.beforeRevision,
    committedRevision: committed.committedRevision,
    committedAt: committed.committedAt,
  };
}

function appendTurn(target: StudySessionRecord): void {
  target.turns.push({
    id: "turn-2",
    sequence: 2,
    learnerMessage: "next question",
    assistantReply: "next answer",
    citations: [],
    characterEvents: [],
    createdAt: "2026-08-13T00:00:02Z",
  });
  target.lastTurnSequence = 2;
}

test("attempt response decoder binds exact Session, Turn, identity, and revisions", () => {
  const raw = {
    schema_version: "study-question-attempt-response-v1",
    attempt_id: "attempt-1",
    client_attempt_id: "client-attempt-1",
    session_id: "session-1",
    turn_id: "turn-1",
    submitted_answer: "A",
    is_correct: true,
    feedback_text: "回答正确",
    explanation: "Because A",
    before_revision: 4,
    committed_revision: 5,
    committed_at: "2026-08-13T00:00:01Z",
  };
  assert.equal(decodeStudyQuestionAttemptResponse(raw, {
    sessionId: "session-1",
    turnId: "turn-1",
    clientAttemptId: "client-attempt-1",
    expectedSessionRevision: 4,
  }).attemptId, "attempt-1");
  assert.throws(() => decodeStudyQuestionAttemptResponse(
    { ...raw, is_correct: "true" },
    { sessionId: "session-1", turnId: "turn-1", clientAttemptId: "client-attempt-1", expectedSessionRevision: 4 },
  ));
  assert.throws(() => decodeStudyQuestionAttemptResponse(
    { ...raw, answer_key: "A" },
    { sessionId: "session-1", turnId: "turn-1", clientAttemptId: "client-attempt-1", expectedSessionRevision: 4 },
  ));
});

test("attempt read-back accepts the exact committed result", () => {
  const before = session();
  const after = structuredClone(before);
  const committed = attempt();
  commitAttempt(after, committed);
  assert.equal(validateStudyQuestionAttemptReadBack({ before, after, turnId: "turn-1", submittedAnswer: "A", attempt: committed }), true);
});

test("attempt read-back rejects identity, answer, verdict, and result drift", () => {
  const before = session();
  const after = structuredClone(before);
  const committed = attempt();
  commitAttempt(after, committed);
  assert.equal(validateStudyQuestionAttemptReadBack({ before, after: { ...after, id: "session-2" }, turnId: "turn-1", submittedAnswer: "A", attempt: committed }), false);
  assert.equal(validateStudyQuestionAttemptReadBack({ before, after, turnId: "turn-missing", submittedAnswer: "A", attempt: committed }), false);
  after.turns[0]!.interactiveQuestion!.result!.feedbackText = "tampered";
  assert.equal(validateStudyQuestionAttemptReadBack({ before, after, turnId: "turn-1", submittedAnswer: "A", attempt: committed }), false);
});

test("a late lower-revision response cannot replace a newer committed snapshot", () => {
  const before = session();
  const after = structuredClone(before);
  const committed = attempt();
  commitAttempt(after, committed);
  const current = structuredClone(after);
  current.revision = 6;
  current.updatedAt = "2026-08-13T00:00:02Z";

  assert.equal(decideStudyQuestionAttemptApply({ before, after, current, turnId: "turn-1", submittedAnswer: "A", attempt: committed }), "keep_current");
  current.turns[0]!.interactiveQuestion!.result!.attemptId = "attempt-other";
  assert.equal(decideStudyQuestionAttemptApply({ before, after, current, turnId: "turn-1", submittedAnswer: "A", attempt: committed }), "reject");
});

test("read-back applies only to the active Session and only when it advances state", () => {
  const before = session();
  const after = structuredClone(before);
  const committed = attempt();
  commitAttempt(after, committed);

  assert.equal(decideStudyQuestionAttemptApply({ before, after, current: before, turnId: "turn-1", submittedAnswer: "A", attempt: committed }), "apply_returned");
  assert.equal(decideStudyQuestionAttemptApply({ before, after, current: { ...before, id: "session-2" }, turnId: "turn-1", submittedAnswer: "A", attempt: committed }), "committed_in_inactive_session");
  assert.equal(decideStudyQuestionAttemptApply({ before, after, current: after, turnId: "turn-1", submittedAnswer: "A", attempt: committed }), "keep_current");
});

test("an attempt read-back accepts a legitimate concurrently appended Turn", () => {
  const before = session();
  const after = structuredClone(before);
  const committed = attempt();
  commitAttempt(after, committed);
  after.revision = 6;
  appendTurn(after);

  assert.equal(validateStudyQuestionAttemptReadBack({ before, after, turnId: "turn-1", submittedAnswer: "A", attempt: committed }), true);
  assert.equal(decideStudyQuestionAttemptApply({ before, after, current: { ...before, revision: 5 }, turnId: "turn-1", submittedAnswer: "A", attempt: committed }), "apply_returned");
});

test("read-back rejects committed Turn prefix drift and invalid watermarks", () => {
  const before = session();
  const after = structuredClone(before);
  const committed = attempt();
  commitAttempt(after, committed);
  after.revision = 6;
  appendTurn(after);

  after.turns[0]!.assistantReply = "tampered";
  assert.equal(validateStudyQuestionAttemptReadBack({ before, after, turnId: "turn-1", submittedAnswer: "A", attempt: committed }), false);
  after.turns[0]!.assistantReply = before.turns[0]!.assistantReply;
  after.lastTurnSequence = 1;
  assert.equal(validateStudyQuestionAttemptReadBack({ before, after, turnId: "turn-1", submittedAnswer: "A", attempt: committed }), false);
});

test("a question with any prior committed result cannot be submitted again", () => {
  const before = session();
  const prior = attempt({ attemptId: "attempt-prior", clientAttemptId: "client-attempt-prior" });
  commitAttempt(before, prior);
  const after = structuredClone(before);
  after.revision = 6;
  const committed = attempt({ beforeRevision: 5, committedRevision: 6 });
  commitAttempt(after, committed);
  assert.equal(validateStudyQuestionAttemptReadBack({ before, after, turnId: "turn-1", submittedAnswer: "A", attempt: committed }), false);
});
