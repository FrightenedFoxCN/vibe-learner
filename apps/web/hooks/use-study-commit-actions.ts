"use client";

import { useEffect, useRef, useState } from "react";
import type { LearningPlan, StudySessionRecord } from "@vibe-learner/shared";
import { submitStudyQuestionAttempt, resolveStudyPlanConfirmation } from "../lib/data/study-sessions";
import { StudyAsyncViewFence } from "../lib/async-result-fence";
import { decideStudyQuestionAttemptApply } from "../lib/study-question-attempt";
import { resolveStudySessionErrorNotice } from "../lib/study-session-decode";
import { createDiagnosticId, diagnosticContext } from "../lib/diagnostics";
import { logWorkspaceError } from "../lib/learning-workspace-telemetry";

interface StudyCommitOptions {
  view: StudyAsyncViewFence<StudySessionRecord>;
  automaticStudyRequest: (key: string, scope: string) => { clientRequestId: string; queryExisting: boolean };
  forgetAutomaticStudyRequest: (key: string) => void;
  onSession: (session: StudySessionRecord) => void;
  onPlan: (plan: LearningPlan) => void;
  onCommittedQuestion: (session: StudySessionRecord, input: { turnId: string; diagnosticFlowId?: string | null }) => Promise<void>;
  onNotice: (notice: string) => void;
}
export interface StudyCommitPort {
  submitStudyQuestionAttempt: typeof submitStudyQuestionAttempt;
  resolveStudyPlanConfirmation: typeof resolveStudyPlanConfirmation;
}
const defaultPort: StudyCommitPort = { submitStudyQuestionAttempt, resolveStudyPlanConfirmation };
export function useStudyCommitActions(options: StudyCommitOptions, port: StudyCommitPort = defaultPort) {
  const latest = useRef(options);
  latest.current = options;
  const { view } = options;
  const mounted = useRef(false);
  const pending = useRef(new Set<string>());
  const [pendingCount, setPendingCount] = useState(0);
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);
  const begin = (key: string) => {
    if (pending.current.has(key)) return false;
    pending.current.add(key); setPendingCount(pending.current.size); return true;
  };
  const finish = (key: string) => {
    pending.current.delete(key);
    if (mounted.current) setPendingCount(pending.current.size);
  };

  const handleSubmitQuestionAttempt = async (input: {
    turnId: string;
    submittedAnswer: string;
  }) => {
    const currentSession = view.session;
    if (!mounted.current || !currentSession) {
      return false;
    }
    const targetViewRevision = view.viewRevision;
    const attemptKey = `attempt:${currentSession.id}:${input.turnId}`;
    if (!begin(attemptKey)) return false;
    try {
      const attemptIdentity = latest.current.automaticStudyRequest(attemptKey, "attempt");
      const context = diagnosticContext(createDiagnosticId());
      const committed = await port.submitStudyQuestionAttempt({
        sessionId: currentSession.id,
        turnId: input.turnId,
        expectedSessionRevision: currentSession.revision,
        clientAttemptId: attemptIdentity.clientRequestId,
        submittedAnswer: input.submittedAnswer,
      }, context);
      const nextSession = committed.session;
      const latestSession = mounted.current && view.viewRevision === targetViewRevision ? view.session : null;
      const applyDecision = decideStudyQuestionAttemptApply({
        before: currentSession,
        after: nextSession,
        current: latestSession,
        turnId: input.turnId,
        submittedAnswer: input.submittedAnswer,
        attempt: committed.attempt,
      });
      if (applyDecision === "reject") {
        throw new Error("study_question_attempt_read_back_mismatch");
      }
      if (applyDecision === "apply_returned") {
        if (mounted.current) latest.current.onSession(nextSession);
      }
      const authoritativeSession = applyDecision === "apply_returned"
        ? nextSession
        : applyDecision === "keep_current"
          ? latestSession
          : null;
      if (mounted.current && authoritativeSession) {
        void latest.current.onCommittedQuestion(authoritativeSession, {
          turnId: input.turnId,
          diagnosticFlowId: context.flow_id,
        });
      }
      latest.current.forgetAutomaticStudyRequest(
        attemptKey,
      );
      return true;
    } catch (error) {
      if (!mounted.current) return false;
      latest.current.onNotice(resolveStudySessionErrorNotice(
          error,
          `记录答案失败：${String(error)}`,
          "update",
        ));
      logWorkspaceError("workflow:study_attempt:error", error);
      return false;
    } finally { finish(attemptKey); }
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
        !mounted.current || view.session?.id !== targetSession.id ||
        view.viewRevision !== targetViewRevision
      ) {
        return false;
      }
      if (view.session.revision > next.session.revision) return false;
      latest.current.onSession(next.session);
      if (next.plan) {
        latest.current.onPlan(next.plan);
      }
      latest.current.onNotice(input.decision === "approve" ? "计划已更新。" : "已保留原计划。");
      return true;
    } catch (error) {
      if (
        !mounted.current || view.session?.id !== targetSession.id ||
        view.viewRevision !== targetViewRevision
      ) {
        return false;
      }
      latest.current.onNotice(resolveStudySessionErrorNotice(
          error,
          `处理计划变更失败：${String(error)}`,
          "update",
        ));
      logWorkspaceError("workflow:study_plan_confirmation:error", error);
      return false;
    } finally {
      finish(key);
    }
  };

  return { handleSubmitQuestionAttempt, handleResolvePlanConfirmation, isApplying: pendingCount > 0 };
}
