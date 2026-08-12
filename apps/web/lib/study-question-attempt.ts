import type { StudySessionRecord } from "@vibe-learner/shared";

export interface StudyQuestionAttemptReadBackInput {
  before: StudySessionRecord;
  after: StudySessionRecord;
  turnId: string;
  submittedAnswer: string;
}

export function validateStudyQuestionAttemptReadBack(
  input: StudyQuestionAttemptReadBackInput
): boolean {
  if (
    input.after.id !== input.before.id ||
    input.after.revision <= input.before.revision ||
    input.after.lastTurnSequence !== input.before.lastTurnSequence
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
    beforeQuestion.submittedAnswer ||
    afterQuestion.prompt !== beforeQuestion.prompt ||
    afterQuestion.submittedAnswer !== input.submittedAnswer.trim() ||
    typeof afterQuestion.isCorrect !== "boolean" ||
    !afterQuestion.feedbackText?.trim()
  ) {
    return false;
  }
  return true;
}
