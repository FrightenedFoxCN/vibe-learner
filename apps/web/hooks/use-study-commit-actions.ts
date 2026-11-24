"use client";

import { useEffect, useRef, useState } from "react";
import type { LearningPlan, StudySessionRecord } from "@vibe-learner/shared";
import {
  readStudyQuestionAttemptSession,
  submitStudyQuestionAttempt,
  resolveStudyPlanConfirmation,
} from "../lib/data/study-sessions";
import { StudyAsyncViewFence } from "../lib/async-result-fence";
import {
  decideStudyQuestionAttemptApply,
  advanceStudyQuestionAttemptOperation,
  studyQuestionAttemptKey,
  type StudyQuestionAttemptCardState,
  type StudyQuestionAttemptOperation,
} from "../lib/study-question-attempt";
import { isApiHttpError } from "../lib/http-error";
import { resolveStudySessionErrorNotice } from "../lib/study-session-decode";
import { createDiagnosticId, diagnosticContext } from "../lib/diagnostics";
import { logWorkspaceError } from "../lib/learning-workspace-telemetry";

interface StudyCommitOptions {
  view: StudyAsyncViewFence<StudySessionRecord>;
  automaticStudyRequest: (
    key: string,
    scope: string,
  ) => { clientRequestId: string; queryExisting: boolean };
  forgetAutomaticStudyRequest: (key: string) => void;
  onSession: (session: StudySessionRecord) => void;
  onPlan: (plan: LearningPlan) => void;
  onNotice: (notice: string) => void;
}
export interface StudyCommitPort {
  submitStudyQuestionAttempt: typeof submitStudyQuestionAttempt;
  readStudyQuestionAttemptSession: typeof readStudyQuestionAttemptSession;
  resolveStudyPlanConfirmation: typeof resolveStudyPlanConfirmation;
}
const defaultPort: StudyCommitPort = {
  submitStudyQuestionAttempt,
  readStudyQuestionAttemptSession,
  resolveStudyPlanConfirmation,
};
function isRejectedQuestionAttempt(error: unknown): boolean {
  if (!isApiHttpError(error)) return false;
  // A transport error or an unrecognized server response does not prove the
  // POST failed. Only an explicit, pre-write rejection unlocks the draft.
  return (
    error.status === 422 ||
    ((error.status === 404 || error.status === 409) &&
      [
        "session_not_found",
        "study_question_attempt_turn_not_found",
        "study_question_attempt_grading_unavailable",
        "study_question_attempt_revision_conflict",
      ].includes(error.code || error.message))
  );
}

export function useStudyCommitActions(
  options: StudyCommitOptions,
  port: StudyCommitPort = defaultPort,
) {
  const latest = useRef(options);
  latest.current = options;
  const { view } = options;
  const mounted = useRef(false);
  const pending = useRef(new Set<string>());
  const attemptFlowIds = useRef(new Map<string, string>());
  const attempts = useRef(
    new Map<
      string,
      StudyQuestionAttemptOperation & {
        context: ReturnType<typeof diagnosticContext>;
      }
    >(),
  );
  const [questionAttemptStates, setQuestionAttemptStates] = useState<
    ReadonlyMap<string, StudyQuestionAttemptCardState>
  >(() => new Map());
  const [pendingCount, setPendingCount] = useState(0);
  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);
  const begin = (key: string) => {
    if (pending.current.has(key)) return false;
    pending.current.add(key);
    setPendingCount(pending.current.size);
    return true;
  };
  const finish = (key: string) => {
    pending.current.delete(key);
    if (mounted.current) setPendingCount(pending.current.size);
  };

  const handleSubmitQuestionAttempt = async (input: {
    sessionId: string;
    turnId: string;
    submittedAnswer: string;
  }) => {
    const currentSession = view.session;
    if (!mounted.current || currentSession?.id !== input.sessionId) return;
    const question = currentSession.turns.find(
      (turn) => turn.id === input.turnId,
    )?.interactiveQuestion;
    if (!question || question.result) return;
    const targetViewRevision = view.viewRevision;
    const inTargetView = () =>
      mounted.current &&
      view.viewRevision === targetViewRevision &&
      view.session?.id === currentSession.id;
    const key = studyQuestionAttemptKey(currentSession.id, input.turnId);
    const attemptKey = `attempt:${currentSession.id}:${input.turnId}`;
    const setAttemptState = (state?: StudyQuestionAttemptCardState) => {
      if (!mounted.current) return;
      setQuestionAttemptStates((previous) => {
        const next = new Map(previous);
        if (state) next.set(key, state);
        else next.delete(key);
        return next;
      });
    };
    const existing = attempts.current.get(key);
    const submittedAnswer =
      existing?.request.submittedAnswer ?? input.submittedAnswer.trim();
    if (!submittedAnswer || !begin(attemptKey)) return;
    try {
      const operation = existing ?? {
        before: currentSession,
        request: {
          sessionId: currentSession.id,
          turnId: input.turnId,
          expectedSessionRevision: currentSession.revision,
          clientAttemptId: latest.current.automaticStudyRequest(attemptKey, "attempt")
            .clientRequestId,
          submittedAnswer,
        },
        context: diagnosticContext(createDiagnosticId()),
      };
      attempts.current.set(key, operation);
      if (!operation.receipt) setAttemptState({ phase: "submitting", submittedAnswer });
      const readBack = await advanceStudyQuestionAttemptOperation(
        operation,
        {
          submit: (request) =>
            port.submitStudyQuestionAttempt(request, operation.context),
          readSession: (sessionId) =>
            port.readStudyQuestionAttemptSession(sessionId, operation.context),
        },
        () => setAttemptState({ phase: "reading_back", submittedAnswer }),
      );
      const applyDecision = decideStudyQuestionAttemptApply({
        ...readBack,
        current: inTargetView() ? view.session : null,
      });
      if (applyDecision === "reject") {
        throw new Error("study_question_attempt_read_back_mismatch");
      }
      if (operation.context.flow_id) {
        // Content-free, bounded correlation for a later explicit explanation.
        attemptFlowIds.current.delete(key);
        attemptFlowIds.current.set(key, operation.context.flow_id);
        if (attemptFlowIds.current.size > 128) {
          const oldest = attemptFlowIds.current.keys().next().value;
          if (oldest !== undefined) attemptFlowIds.current.delete(oldest);
        }
      }
      if (applyDecision === "committed_in_inactive_session") {
        // Preserve the receipt for a stale card if the learner returns later.
        setAttemptState({ phase: "retry_read", submittedAnswer });
        return;
      }
      if (applyDecision === "apply_returned") latest.current.onSession(readBack.after);
      latest.current.onNotice("答案已记录。需要进一步讲解时，可选择“生成答题讲解”。");
      attempts.current.delete(key);
      latest.current.forgetAutomaticStudyRequest(attemptKey);
      setAttemptState();
    } catch (error) {
      if (attempts.current.get(key)?.receipt) {
        setAttemptState({ phase: "retry_read", submittedAnswer });
        if (inTargetView())
          latest.current.onNotice(
            "答案已记录，但暂时无法读取学习记录。请重试读取结果，无需重新提交。",
          );
      } else if (isRejectedQuestionAttempt(error)) {
        attempts.current.delete(key);
        latest.current.forgetAutomaticStudyRequest(attemptKey);
        setAttemptState({ phase: "failed" });
        if (inTargetView())
          latest.current.onNotice(
            resolveStudySessionErrorNotice(
              error,
              `记录答案失败：${String(error)}`,
              "update",
            ),
          );
      } else {
        setAttemptState({ phase: "retry_submit", submittedAnswer });
        if (inTargetView())
          latest.current.onNotice("暂时无法确认答案是否已记录。请重试确认原答案。");
      }
      logWorkspaceError("workflow:study_attempt:error", error);
    } finally {
      finish(attemptKey);
    }
  };

  const handleResolvePlanConfirmation = async (input: {
    confirmationId: string;
    decision: "approve" | "reject";
    note?: string;
  }) => {
    const targetSession = view.session;
    if (!mounted.current || !targetSession) {
      return false;
    }
    const key = `confirmation:${targetSession.id}:${input.confirmationId}`;
    if (!begin(key)) return false;
    const targetViewRevision = view.viewRevision;
    try {
      const next = await port.resolveStudyPlanConfirmation({
        sessionId: targetSession.id,
        confirmationId: input.confirmationId,
        decision: input.decision,
        note: input.note,
      });
      if (
        !mounted.current ||
        view.session?.id !== targetSession.id ||
        view.viewRevision !== targetViewRevision
      ) {
        return false;
      }
      if (view.session.revision > next.session.revision) return false;
      latest.current.onSession(next.session);
      if (next.plan) {
        latest.current.onPlan(next.plan);
      }
      latest.current.onNotice(
        input.decision === "approve" ? "计划已更新。" : "已保留原计划。",
      );
      return true;
    } catch (error) {
      if (
        !mounted.current ||
        view.session?.id !== targetSession.id ||
        view.viewRevision !== targetViewRevision
      ) {
        return false;
      }
      latest.current.onNotice(
        resolveStudySessionErrorNotice(
          error,
          `处理计划变更失败：${String(error)}`,
          "update",
        ),
      );
      logWorkspaceError("workflow:study_plan_confirmation:error", error);
      return false;
    } finally {
      finish(key);
    }
  };

  const getQuestionAttemptDiagnosticFlowId = (sessionId: string, turnId: string) =>
    attemptFlowIds.current.get(studyQuestionAttemptKey(sessionId, turnId)) ?? null;

  return {
    handleSubmitQuestionAttempt,
    questionAttemptStates,
    handleResolvePlanConfirmation,
    getQuestionAttemptDiagnosticFlowId,
    isApplying: pendingCount > 0,
  };
}
