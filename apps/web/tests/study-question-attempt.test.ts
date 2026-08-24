import assert from "node:assert/strict";
import test from "node:test";

import type { StudySessionRecord } from "@vibe-learner/shared";

import {
  decideStudyQuestionAttemptApply,
  validateStudyQuestionAttemptReadBack,
} from "../lib/study-question-attempt.ts";

function session(): StudySessionRecord {
  return {
    id: "session-1",
    documentId: "doc-1",
    personaId: "persona-1",
    planId: "plan-1",
    studyUnitId: "unit-1",
    studyUnitTitle: "Unit",
    themeHint: "",
    sessionSystemPrompt: "",
    status: "active",
    revision: 4,
    lastTurnSequence: 1,
    turns: [{
      id: "turn-1",
      sequence: 1,
      learnerMessage: "question",
      assistantReply: "answer",
      citations: [],
      characterEvents: [],
      interactiveQuestion: {
        questionType: "multiple_choice",
        prompt: "2 + 2?",
        difficulty: "easy",
        topic: "math",
        options: [{ key: "A", text: "4" }],
        acceptedAnswers: ["A"],
        explanation: "",
      },
      createdAt: "2026-08-13T00:00:00Z",
    }],
    preparedStudyUnitIds: [],
    pendingFollowUps: [],
    sessionMemory: [],
    planConfirmations: [],
    updatedAt: "2026-08-13T00:00:00Z",
    createdAt: "2026-08-13T00:00:00Z",
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
    createdAt: "2026-08-13T00:00:01Z",
  });
  target.lastTurnSequence = 2;
}

test("attempt read-back accepts the same committed turn and answer", () => {
  const before = session();
  const after = structuredClone(before);
  after.revision = 5;
  const question = after.turns[0]!.interactiveQuestion!;
  question.submittedAnswer = "A";
  question.isCorrect = true;
  question.feedbackText = "回答正确";
  assert.equal(validateStudyQuestionAttemptReadBack({ before, after, turnId: "turn-1", submittedAnswer: "A" }), true);
});

test("attempt read-back rejects wrong session, turn, answer, and missing verdict", () => {
  const before = session();
  const after = structuredClone(before);
  after.revision = 5;
  const question = after.turns[0]!.interactiveQuestion!;
  question.submittedAnswer = "B";
  question.isCorrect = false;
  question.feedbackText = "回答不正确";
  assert.equal(validateStudyQuestionAttemptReadBack({ before, after, turnId: "turn-1", submittedAnswer: "A" }), false);
  assert.equal(validateStudyQuestionAttemptReadBack({ before, after: { ...after, id: "session-2" }, turnId: "turn-1", submittedAnswer: "B" }), false);
  assert.equal(validateStudyQuestionAttemptReadBack({ before, after, turnId: "turn-missing", submittedAnswer: "B" }), false);
  question.feedbackText = "";
  assert.equal(validateStudyQuestionAttemptReadBack({ before, after, turnId: "turn-1", submittedAnswer: "B" }), false);
});

test("a late lower-revision response cannot replace a newer committed snapshot", () => {
  const before = session();
  const after = structuredClone(before);
  after.revision = 5;
  const returnedQuestion = after.turns[0]!.interactiveQuestion!;
  returnedQuestion.submittedAnswer = "A";
  returnedQuestion.isCorrect = true;
  returnedQuestion.feedbackText = "回答正确";

  const current = structuredClone(after);
  current.revision = 6;
  current.updatedAt = "2026-08-13T00:00:02Z";

  assert.equal(decideStudyQuestionAttemptApply({
    before,
    after,
    current,
    turnId: "turn-1",
    submittedAnswer: "A",
  }), "keep_current");

  current.turns[0]!.interactiveQuestion!.submittedAnswer = "B";
  assert.equal(decideStudyQuestionAttemptApply({
    before,
    after,
    current,
    turnId: "turn-1",
    submittedAnswer: "A",
  }), "reject");
});

test("read-back applies only to the active Session and only when it advances state", () => {
  const before = session();
  const after = structuredClone(before);
  after.revision = 5;
  const question = after.turns[0]!.interactiveQuestion!;
  question.submittedAnswer = "A";
  question.isCorrect = true;
  question.feedbackText = "回答正确";

  assert.equal(decideStudyQuestionAttemptApply({
    before,
    after,
    current: before,
    turnId: "turn-1",
    submittedAnswer: "A",
  }), "apply_returned");
  assert.equal(decideStudyQuestionAttemptApply({
    before,
    after,
    current: { ...before, id: "session-2" },
    turnId: "turn-1",
    submittedAnswer: "A",
  }), "committed_in_inactive_session");
  assert.equal(decideStudyQuestionAttemptApply({
    before,
    after,
    current: after,
    turnId: "turn-1",
    submittedAnswer: "A",
  }), "keep_current");
});

test("an attempt read-back accepts a legitimate concurrently appended Turn", () => {
  const before = session();
  const after = structuredClone(before);
  after.revision = 6;
  appendTurn(after);
  const question = after.turns[0]!.interactiveQuestion!;
  question.submittedAnswer = "A";
  question.isCorrect = true;
  question.feedbackText = "回答正确";

  assert.equal(validateStudyQuestionAttemptReadBack({
    before,
    after,
    turnId: "turn-1",
    submittedAnswer: "A",
  }), true);
  assert.equal(decideStudyQuestionAttemptApply({
    before,
    after,
    current: { ...before, revision: 5 },
    turnId: "turn-1",
    submittedAnswer: "A",
  }), "apply_returned");
});

test("read-back rejects committed Turn prefix drift and invalid watermarks", () => {
  const before = session();
  const after = structuredClone(before);
  after.revision = 6;
  appendTurn(after);
  const question = after.turns[0]!.interactiveQuestion!;
  question.submittedAnswer = "A";
  question.isCorrect = true;
  question.feedbackText = "回答正确";

  after.turns[0]!.assistantReply = "tampered";
  assert.equal(validateStudyQuestionAttemptReadBack({ before, after, turnId: "turn-1", submittedAnswer: "A" }), false);
  after.turns[0]!.assistantReply = before.turns[0]!.assistantReply;
  after.lastTurnSequence = 1;
  assert.equal(validateStudyQuestionAttemptReadBack({ before, after, turnId: "turn-1", submittedAnswer: "A" }), false);
});

test("a question with any prior committed verdict cannot be submitted again", () => {
  const before = session();
  const beforeQuestion = before.turns[0]!.interactiveQuestion!;
  beforeQuestion.isCorrect = false;
  beforeQuestion.feedbackText = "回答不正确";
  const after = structuredClone(before);
  after.revision = 5;
  const afterQuestion = after.turns[0]!.interactiveQuestion!;
  afterQuestion.submittedAnswer = "A";
  afterQuestion.isCorrect = true;
  afterQuestion.feedbackText = "回答正确";
  assert.equal(validateStudyQuestionAttemptReadBack({ before, after, turnId: "turn-1", submittedAnswer: "A" }), false);
});
