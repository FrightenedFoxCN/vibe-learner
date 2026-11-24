import assert from "node:assert/strict";
import { test } from "node:test";
import type { InteractiveQuestion, StudySessionRecord } from "@vibe-learner/shared";
import {
  decodeStudyQuestionAttemptResponse,
  decideStudyQuestionAttemptApply,
  advanceStudyQuestionAttemptOperation,
  studyQuestionAttemptDisplayAnswer,
  studyQuestionAttemptKey,
  type StudyQuestionAttemptOperation,
} from "../lib/study-question-attempt.ts";
import { StudyAsyncViewFence } from "../lib/async-result-fence.ts";

const expected = {
  sessionId: "session",
  turnId: "turn",
  clientAttemptId: "client",
  expectedSessionRevision: 0,
  submittedAnswer: " A ",
};
const attempt = {
  schema_version: "study-question-attempt-response-v1",
  attempt_id: "attempt",
  client_attempt_id: "client",
  session_id: "session",
  turn_id: "turn",
  submitted_answer: "A",
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

test("attempt binds the normalized answer but preserves feedback and timestamp text", () => {
  assert.deepEqual(decode(attempt), {
    schemaVersion: "study-question-attempt-response-v1",
    attemptId: "attempt",
    clientAttemptId: "client",
    sessionId: "session",
    turnId: "turn",
    submittedAnswer: "A",
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
    { submitted_answer: "B" },
    { before_revision: 1, committed_revision: 2 },
    { committed_revision: 2 },
  ])
    rejects({ ...attempt, ...override }, "binding_mismatch");
});

const question: InteractiveQuestion = {
  schemaVersion: "study-interactive-question-v2",
  callBack: false,
  questionType: "multiple_choice",
  prompt: "Choose A or B",
  options: [
    { key: "A", text: "First" },
    { key: "B", text: "Second" },
  ],
  topic: "example",
  difficulty: "easy",
  result: null,
};
const receipt = decode(attempt);
const answered: InteractiveQuestion = {
  ...question,
  result: { ...receipt, schemaVersion: "study-question-result-v1" },
};
function makeSession(id: string, revision: number, interactiveQuestion = question) {
  return {
    id,
    studyUnitId: id,
    revision,
    lastTurnSequence: 1,
    turns: [{ id: "turn", sequence: 1, interactiveQuestion }],
  } as StudySessionRecord;
}

const before = makeSession(expected.sessionId, 0);
const after = makeSession(expected.sessionId, 1, answered);

test("a persisted receipt guards GET retries, stale readback, and changed drafts", async () => {
  const operation: StudyQuestionAttemptOperation = { before, request: { ...expected } };
  const events: string[] = [];
  const port = {
    submit: async (request: typeof expected) => {
      events.push("POST");
      assert.deepEqual(request, expected);
      return receipt;
    },
    readSession: async (sessionId: string) => {
      assert.equal(sessionId, expected.sessionId);
      assert.equal(operation.receipt, receipt);
      events.push("GET");
      switch (events.filter((event) => event === "GET").length) {
        case 1:
          throw new Error("read failed");
        case 2:
          return before;
        case 3:
          return makeSession(before.id, 1, {
            ...answered,
            result: { ...answered.result!, submittedAnswer: "B" },
          });
        default:
          return after;
      }
    },
  };
  const run = () =>
    advanceStudyQuestionAttemptOperation(operation, port, () => events.push("receipt"));
  await assert.rejects(run, /read failed/);
  assert.equal(operation.receipt, receipt);
  assert.equal(
    studyQuestionAttemptDisplayAnswer(
      question,
      { phase: "retry_read", submittedAnswer: receipt.submittedAnswer },
      "B",
    ),
    "A",
  );
  const stale = await run();
  assert.equal(
    decideStudyQuestionAttemptApply({ ...stale, current: before }),
    "reject",
  );
  const mismatch = await run();
  assert.equal(
    decideStudyQuestionAttemptApply({ ...mismatch, current: before }),
    "reject",
  );
  const recovered = await run();
  assert.equal(
    decideStudyQuestionAttemptApply({ ...recovered, current: before }),
    "apply_returned",
  );
  assert.deepEqual(events, [
    "POST",
    "receipt",
    "GET",
    "receipt",
    "GET",
    "receipt",
    "GET",
    "receipt",
    "GET",
  ]);
});

test("an unconfirmed POST retries the same identity, revision, and answer", async () => {
  const operation: StudyQuestionAttemptOperation = { before, request: { ...expected } };
  const submitted: (typeof expected)[] = [];
  const run = () =>
    advanceStudyQuestionAttemptOperation(
      operation,
      {
        submit: async (request) => {
          submitted.push(request);
          if (submitted.length === 1) throw new Error("response lost");
          return receipt;
        },
        readSession: async () => after,
      },
      () => {},
    );
  await assert.rejects(run, /response lost/);
  assert.equal(operation.receipt, undefined);
  const readBack = await run();
  assert.deepEqual(submitted, [expected, expected]);
  assert.equal(
    decideStudyQuestionAttemptApply({ ...readBack, current: before }),
    "apply_returned",
  );
});

test("late reads do not publish to another session or a replaced view", async () => {
  const view = new StudyAsyncViewFence({ session: before });
  const viewRevision = view.viewRevision;
  const operation: StudyQuestionAttemptOperation = { before, request: { ...expected } };
  const other = makeSession("other-session", 0);
  assert.notEqual(
    studyQuestionAttemptKey(before.id, "turn"),
    studyQuestionAttemptKey(other.id, "turn"),
  );
  const readBack = await advanceStudyQuestionAttemptOperation(
    operation,
    {
      submit: async () => receipt,
      readSession: async (sessionId) => {
        assert.equal(sessionId, before.id);
        view.activateSession(other);
        return after;
      },
    },
    () => {},
  );
  assert.equal(
    decideStudyQuestionAttemptApply({ ...readBack, current: view.session }),
    "committed_in_inactive_session",
  );
  view.activateSession(before);
  assert.notEqual(view.viewRevision, viewRevision);
  assert.equal(
    decideStudyQuestionAttemptApply({
      ...readBack,
      current: view.viewRevision === viewRevision ? view.session : null,
    }),
    "committed_in_inactive_session",
  );
  const retried = await advanceStudyQuestionAttemptOperation(
    operation,
    {
      submit: async () => {
        throw new Error("must not POST on return");
      },
      readSession: async (sessionId) => {
        assert.equal(sessionId, before.id);
        return after;
      },
    },
    () => {},
  );
  assert.equal(
    decideStudyQuestionAttemptApply({ ...retried, current: view.session }),
    "apply_returned",
  );
  const newer = makeSession(before.id, 2, answered);
  assert.equal(
    decideStudyQuestionAttemptApply({ ...readBack, current: newer }),
    "keep_current",
  );
});

test("read-back answers override stale drafts for both choices and blanks", () => {
  for (const questionType of ["multiple_choice", "fill_blank"] as const) {
    assert.equal(
      studyQuestionAttemptDisplayAnswer(
        { ...answered, questionType },
        { phase: "retry_read", submittedAnswer: "C" },
        "B",
      ),
      "A",
    );
    assert.equal(
      studyQuestionAttemptDisplayAnswer(
        { ...question, questionType },
        { phase: "failed" },
        "B",
      ),
      "B",
    );
  }
});
