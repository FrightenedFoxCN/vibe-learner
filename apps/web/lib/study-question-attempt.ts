import type { StudySessionRecord } from "@vibe-learner/shared";

export interface StudyQuestionAttemptReadBackInput {
  before: StudySessionRecord;
  after: StudySessionRecord;
  turnId: string;
  submittedAnswer: string;
}

export interface StudyQuestionAttemptApplyInput extends StudyQuestionAttemptReadBackInput {
  current: StudySessionRecord | null;
}

export type StudyQuestionAttemptApplyDecision =
  | "apply_returned"
  | "keep_current"
  | "committed_in_inactive_session"
  | "reject";

export function validateStudyQuestionAttemptReadBack(
  input: StudyQuestionAttemptReadBackInput
): boolean {
  if (
    input.after.id !== input.before.id ||
    input.after.revision <= input.before.revision ||
    input.before.lastTurnSequence !== input.before.turns.length ||
    input.after.lastTurnSequence !== input.after.turns.length ||
    input.after.lastTurnSequence < input.before.lastTurnSequence ||
    !hasStableTurnPrefix(input.before, input.after)
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
    Boolean(beforeQuestion.submittedAnswer) ||
    typeof beforeQuestion.isCorrect === "boolean" ||
    Boolean(beforeQuestion.feedbackText) ||
    afterQuestion.prompt !== beforeQuestion.prompt ||
    afterQuestion.submittedAnswer !== input.submittedAnswer.trim() ||
    typeof afterQuestion.isCorrect !== "boolean" ||
    !afterQuestion.feedbackText?.trim()
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
    const previousQuestion = turn.interactiveQuestion;
    if (!previousQuestion?.submittedAnswer) {
      return true;
    }
    const currentQuestion = candidate.interactiveQuestion;
    return Boolean(
      currentQuestion &&
      currentQuestion.submittedAnswer === previousQuestion.submittedAnswer &&
      currentQuestion.isCorrect === previousQuestion.isCorrect &&
      currentQuestion.feedbackText === previousQuestion.feedbackText
    );
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
      submittedAnswer: undefined,
      isCorrect: undefined,
      feedbackText: undefined,
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
  input: Pick<StudyQuestionAttemptReadBackInput, "turnId" | "submittedAnswer">
): boolean {
  const question = session.turns.find(
    (turn) => turn.id === input.turnId
  )?.interactiveQuestion;
  return Boolean(
    question &&
    question.submittedAnswer === input.submittedAnswer.trim() &&
    typeof question.isCorrect === "boolean" &&
    question.feedbackText?.trim()
  );
}
