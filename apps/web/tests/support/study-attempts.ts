import type { StudySessionRecord } from "@vibe-learner/shared";
import type { StudyQuestionAttemptResponse } from "../../lib/study-question-attempt";

export function session(): StudySessionRecord {
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

export function attempt(overrides: Partial<StudyQuestionAttemptResponse> = {}): StudyQuestionAttemptResponse {
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

export function commitAttempt(target: StudySessionRecord, committed: StudyQuestionAttemptResponse): void {
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
