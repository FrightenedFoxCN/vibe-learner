import assert from "node:assert/strict";
import test from "node:test";

import type { StudySessionRecord } from "@vibe-learner/shared";

import { validateStudyQuestionAttemptReadBack } from "../lib/study-question-attempt.ts";

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
