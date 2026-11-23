import assert from "node:assert/strict";
import { test } from "node:test";
import { decodeStudyQuestionAttemptResponse } from "../lib/study-question-attempt.ts";

const expected = {
  sessionId: "session",
  turnId: "turn",
  clientAttemptId: "client",
  expectedSessionRevision: 0,
};
const attempt = {
  schema_version: "study-question-attempt-response-v1",
  attempt_id: "attempt",
  client_attempt_id: "client",
  session_id: "session",
  turn_id: "turn",
  submitted_answer: " A ",
  is_correct: false,
  feedback_text: " Try again ",
  explanation: "",
  before_revision: 0,
  committed_revision: 1,
  committed_at: " legacy non-empty timestamp ",
};
const decode = (raw: unknown) => decodeStudyQuestionAttemptResponse(raw, expected);

function rejects(raw: unknown, suffix: string) {
  assert.throws(() => decode(raw), {
    message: "study_question_attempt_response_" + suffix,
  });
}

test("attempt keeps text untouched and only requires committed_at to be nonblank", () => {
  assert.deepEqual(decode(attempt), {
    schemaVersion: "study-question-attempt-response-v1",
    attemptId: "attempt",
    clientAttemptId: "client",
    sessionId: "session",
    turnId: "turn",
    submittedAnswer: " A ",
    isCorrect: false,
    feedbackText: " Try again ",
    explanation: "",
    beforeRevision: 0,
    committedRevision: 1,
    committedAt: " legacy non-empty timestamp ",
  });
});

test("attempt shape failures retain generic, extra-field and field-specific errors", () => {
  const { feedback_text: _feedback, ...missing } = attempt;
  rejects(null, "invalid");
  rejects({ ...attempt, schema_version: "v0" }, "invalid");
  rejects({ ...attempt, is_correct: 0 }, "invalid");
  rejects({ ...attempt, explanation: null }, "invalid");
  rejects({ ...attempt, answer_key: "A", is_correct: null }, "extra_field");
  rejects(missing, "feedback_text_invalid");
  rejects({ ...attempt, committed_at: "  " }, "committed_at_invalid");
  rejects({ ...attempt, submitted_answer: 1 }, "submitted_answer_invalid");
  rejects({ ...attempt, before_revision: "0" }, "before_revision_invalid");
  rejects({ ...attempt, before_revision: -1 }, "before_revision_invalid");
  rejects(
    { ...attempt, committed_revision: Number.MAX_SAFE_INTEGER + 1 },
    "committed_revision_invalid",
  );
});

test("attempt rejects mismatched request identity or revision increment", () => {
  for (const override of [
    { session_id: "other" },
    { turn_id: "other" },
    { client_attempt_id: "other" },
    { before_revision: 1, committed_revision: 2 },
    { committed_revision: 2 },
  ])
    rejects({ ...attempt, ...override }, "binding_mismatch");
});
