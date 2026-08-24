import type { StudySessionRecord } from "@vibe-learner/shared";

export interface StudyQuestionAttemptResponse {
  schemaVersion: "study-question-attempt-response-v1";
  attemptId: string;
  clientAttemptId: string;
  sessionId: string;
  turnId: string;
  submittedAnswer: string;
  isCorrect: boolean;
  feedbackText: string;
  explanation: string;
  beforeRevision: number;
  committedRevision: number;
  committedAt: string;
}

export interface StudyQuestionAttemptReadBackInput {
  before: StudySessionRecord;
  after: StudySessionRecord;
  turnId: string;
  submittedAnswer: string;
  attempt: StudyQuestionAttemptResponse;
}

export interface StudyQuestionAttemptApplyInput extends StudyQuestionAttemptReadBackInput {
  current: StudySessionRecord | null;
}

export type StudyQuestionAttemptApplyDecision =
  | "apply_returned"
  | "keep_current"
  | "committed_in_inactive_session"
  | "reject";

export function decodeStudyQuestionAttemptResponse(
  raw: unknown,
  expected: {
    sessionId: string;
    turnId: string;
    clientAttemptId: string;
    expectedSessionRevision: number;
  }
): StudyQuestionAttemptResponse {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new Error("study_question_attempt_response_invalid");
  }
  const value = raw as Record<string, unknown>;
  const allowed = new Set([
    "schema_version",
    "attempt_id",
    "client_attempt_id",
    "session_id",
    "turn_id",
    "submitted_answer",
    "is_correct",
    "feedback_text",
    "explanation",
    "before_revision",
    "committed_revision",
    "committed_at",
  ]);
  if (Object.keys(value).some((key) => !allowed.has(key))) {
    throw new Error("study_question_attempt_response_extra_field");
  }
  const requiredString = (field: string) => {
    const candidate = value[field];
    if (typeof candidate !== "string" || !candidate.trim()) {
      throw new Error(`study_question_attempt_response_${field}_invalid`);
    }
    return candidate;
  };
  const requiredRevision = (field: string) => {
    const candidate = value[field];
    if (!Number.isSafeInteger(candidate) || Number(candidate) < 0) {
      throw new Error(`study_question_attempt_response_${field}_invalid`);
    }
    return Number(candidate);
  };
  if (
    value.schema_version !== "study-question-attempt-response-v1" ||
    typeof value.is_correct !== "boolean" ||
    typeof value.explanation !== "string"
  ) {
    throw new Error("study_question_attempt_response_invalid");
  }
  const response: StudyQuestionAttemptResponse = {
    schemaVersion: value.schema_version,
    attemptId: requiredString("attempt_id"),
    clientAttemptId: requiredString("client_attempt_id"),
    sessionId: requiredString("session_id"),
    turnId: requiredString("turn_id"),
    submittedAnswer: requiredString("submitted_answer"),
    isCorrect: value.is_correct,
    feedbackText: requiredString("feedback_text"),
    explanation: value.explanation,
    beforeRevision: requiredRevision("before_revision"),
    committedRevision: requiredRevision("committed_revision"),
    committedAt: requiredString("committed_at"),
  };
  if (
    response.sessionId !== expected.sessionId ||
    response.turnId !== expected.turnId ||
    response.clientAttemptId !== expected.clientAttemptId ||
    response.beforeRevision !== expected.expectedSessionRevision ||
    response.committedRevision !== response.beforeRevision + 1
  ) {
    throw new Error("study_question_attempt_response_binding_mismatch");
  }
  return response;
}

export function validateStudyQuestionAttemptReadBack(
  input: StudyQuestionAttemptReadBackInput
): boolean {
  if (
    input.after.id !== input.before.id ||
    input.after.revision <= input.before.revision ||
    input.before.lastTurnSequence !== input.before.turns.length ||
    input.after.lastTurnSequence !== input.after.turns.length ||
    input.after.lastTurnSequence < input.before.lastTurnSequence ||
    !hasStableTurnPrefix(input.before, input.after) ||
    input.attempt.sessionId !== input.before.id ||
    input.attempt.turnId !== input.turnId ||
    input.attempt.beforeRevision !== input.before.revision ||
    input.attempt.committedRevision !== input.before.revision + 1 ||
    input.after.revision < input.attempt.committedRevision ||
    input.attempt.submittedAnswer !== input.submittedAnswer.trim()
  ) {
    return false;
  }
  const beforeTurn = input.before.turns.find((turn) => turn.id === input.turnId);
  const afterTurn = input.after.turns.find((turn) => turn.id === input.turnId);
  const beforeQuestion = beforeTurn?.interactiveQuestion;
  const afterQuestion = afterTurn?.interactiveQuestion;
  if (
    !beforeQuestion ||
    !afterQuestion ||
    beforeQuestion.result !== null ||
    afterQuestion.prompt !== beforeQuestion.prompt ||
    !matchesAttemptResult(afterQuestion.result, input.attempt)
  ) {
    return false;
  }
  return true;
}

export function decideStudyQuestionAttemptApply(
  input: StudyQuestionAttemptApplyInput
): StudyQuestionAttemptApplyDecision {
  if (!validateStudyQuestionAttemptReadBack(input)) {
    return "reject";
  }
  if (!input.current || input.current.id !== input.before.id) {
    return "committed_in_inactive_session";
  }
  if (
    input.current.revision < input.before.revision ||
    input.current.lastTurnSequence !== input.current.turns.length ||
    !hasStableTurnPrefix(input.before, input.current)
  ) {
    return "reject";
  }
  if (input.current.revision <= input.after.revision) {
    return input.current.revision === input.after.revision
      ? hasCommittedStudyQuestionAttempt(input.current, input)
        ? "keep_current"
        : "reject"
      : "apply_returned";
  }
  return hasCommittedStudyQuestionAttempt(input.current, input)
    ? "keep_current"
    : "reject";
}

function hasStableTurnPrefix(
  before: StudySessionRecord,
  after: StudySessionRecord
): boolean {
  if (after.turns.length < before.turns.length) {
    return false;
  }
  return before.turns.every((turn, index) => {
    const candidate = after.turns[index];
    if (
      !candidate ||
      candidate.id !== turn.id ||
      candidate.sequence !== turn.sequence ||
      !sameValue(withoutAnswerState(candidate), withoutAnswerState(turn))
    ) {
      return false;
    }
    const previousResult = turn.interactiveQuestion?.result;
    if (!previousResult) {
      return true;
    }
    return sameValue(candidate.interactiveQuestion?.result, previousResult);
  });
}

function withoutAnswerState(turn: StudySessionRecord["turns"][number]) {
  const question = turn.interactiveQuestion;
  if (!question) {
    return turn;
  }
  return {
    ...turn,
    interactiveQuestion: {
      ...question,
      result: null,
    },
  };
}

function sameValue(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) {
    return true;
  }
  if (Array.isArray(left) || Array.isArray(right)) {
    return Boolean(
      Array.isArray(left) &&
      Array.isArray(right) &&
      left.length === right.length &&
      left.every((item, index) => sameValue(item, right[index]))
    );
  }
  if (!left || !right || typeof left !== "object" || typeof right !== "object") {
    return false;
  }
  const leftRecord = left as Record<string, unknown>;
  const rightRecord = right as Record<string, unknown>;
  const keys = new Set([...Object.keys(leftRecord), ...Object.keys(rightRecord)]);
  return [...keys].every((key) => sameValue(leftRecord[key], rightRecord[key]));
}

function hasCommittedStudyQuestionAttempt(
  session: StudySessionRecord,
  input: Pick<StudyQuestionAttemptReadBackInput, "turnId" | "attempt">
): boolean {
  const question = session.turns.find(
    (turn) => turn.id === input.turnId
  )?.interactiveQuestion;
  return matchesAttemptResult(question?.result ?? null, input.attempt);
}

function matchesAttemptResult(
  result: NonNullable<StudySessionRecord["turns"][number]["interactiveQuestion"]>["result"],
  attempt: StudyQuestionAttemptResponse
): boolean {
  return Boolean(
    result &&
    result.attemptId === attempt.attemptId &&
    result.clientAttemptId === attempt.clientAttemptId &&
    result.submittedAnswer === attempt.submittedAnswer &&
    result.isCorrect === attempt.isCorrect &&
    result.feedbackText === attempt.feedbackText &&
    result.explanation === attempt.explanation &&
    result.beforeRevision === attempt.beforeRevision &&
    result.committedRevision === attempt.committedRevision &&
    result.committedAt === attempt.committedAt
  );
}
