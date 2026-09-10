"use client";

import { useEffect, useRef, useState } from "react";
import type { StudySessionRecord } from "@vibe-learner/shared";
import { getStudyChatOperation, sendStudyMessage, type StudyChatOperationResponse } from "../lib/data/study-sessions";
import { studyOperationStore, presentStudyChatOperation, type StudyChatDraft, type StudyOperationStore } from "../lib/study-operation-state";
import { StudyAsyncViewFence } from "../lib/async-result-fence";
import { createStudyChatRequestId } from "../lib/client-request-id";
import { resolveStudySessionErrorNotice } from "../lib/study-session-decode";
import { isDefiniteStudyChatPreAdmissionError, studyChatPreAdmissionNotice } from "../lib/http-error";
import { logWorkspaceError, logWorkspaceInfo } from "../lib/learning-workspace-telemetry";
import type { useStudyChatRecovery } from "./use-study-chat-recovery";
import type { useStudySessionNavigation } from "./use-study-session-navigation";

interface StudyMessageOptions {
  view: StudyAsyncViewFence<StudySessionRecord>;
  recovery: Pick<ReturnType<typeof useStudyChatRecovery>, "chatFailure" | "setChatFailure" | "beginStudyResponseTicket" | "isCurrentStudyResponseTicket" | "applyStudyChatOperation">;
  ensureSessionForSection: ReturnType<typeof useStudySessionNavigation>["ensureSessionForSection"];
  isDialogueInterruptedForSession: (id: string) => boolean;
  peekDeferredInteractiveCallbackPrefix: (id: string) => string;
  clearInterruptedDialogueState: (id: string, consumedPrefix: string) => void;
  onNotice: (notice: string) => void;
}
export interface StudyMessagePort {
  getStudyChatOperation: typeof getStudyChatOperation;
  sendStudyMessage: typeof sendStudyMessage;
}
const defaultPort: StudyMessagePort = { getStudyChatOperation, sendStudyMessage };
export function useStudyMessages(options: StudyMessageOptions, port: StudyMessagePort = defaultPort,
  store: StudyOperationStore = studyOperationStore) {
  const latest = useRef(options);
  latest.current = options;
  const { view } = options;
  const mounted = useRef(false);
  const learnerInFlight = useRef(false);
  const [pendingCount, setPendingCount] = useState(0);
  const automaticRequests = useRef(new Map<string, string>());
  const automaticStudyRequest = (key: string, scope: string) => store.getOrCreateAutomaticRequestId(automaticRequests.current, key, scope);
  const forgetAutomaticStudyRequest = (key: string) => store.forgetAutomaticStudyRequestId(automaticRequests.current, key);
  const { persistPendingStudyOperation, clearPendingStudyOperation } = store;
  const { setChatFailure, beginStudyResponseTicket, isCurrentStudyResponseTicket, applyStudyChatOperation } = options.recovery;
  useEffect(() => { mounted.current = true; return () => { mounted.current = false; }; }, []);

  const sendHiddenSessionMessage = async (input: {
    session: StudySessionRecord;
    clientRequestId: string;
    operationKey: string;
    queryExisting: boolean;
    message: string;
    messageKind: "session_prelude" | "scheduled_follow_up" | "interactive_callback";
    followUpId?: string;
    diagnosticFlowId?: string | null;
  }) => {
    if (!mounted.current) return null;
    const draft: StudyChatDraft = {
      sessionId: input.session.id,
      clientRequestId: input.clientRequestId,
      expectedSessionRevision: input.session.revision,
      message: input.message,
      studyUnitId: input.session.studyUnitId,
      attachments: [],
      messageKind: input.messageKind,
      followUpId: input.followUpId,
    };
    persistPendingStudyOperation(draft);
    const ticket = beginStudyResponseTicket(draft);
    let next: StudyChatOperationResponse;
    try {
      next = input.queryExisting
        ? await port.getStudyChatOperation({
            sessionId: input.session.id,
            clientRequestId: input.clientRequestId,
            ...(input.diagnosticFlowId ? { diagnosticFlowId: input.diagnosticFlowId } : {}),
          })
        : await port.sendStudyMessage({
            sessionId: input.session.id,
            clientRequestId: input.clientRequestId,
            expectedSessionRevision: input.session.revision,
            message: input.message,
            messageKind: input.messageKind,
            followUpId: input.followUpId,
            ...(input.diagnosticFlowId ? { diagnosticFlowId: input.diagnosticFlowId } : {}),
          });
    } catch (error) {
      if (!isCurrentStudyResponseTicket(ticket)) {
        view.settle(ticket);
        return null;
      }
      view.settle(ticket);
      if (isDefiniteStudyChatPreAdmissionError(error)) {
        clearPendingStudyOperation(draft);
        forgetAutomaticStudyRequest(input.operationKey);
        setChatFailure({
          ...draft,
          detail: studyChatPreAdmissionNotice(error),
          operationStatus: "unresolved",
          canQuery: false,
          canResend: false,
          canRefreshSession: true,
        });
        throw error;
      }
      setChatFailure({
        ...draft,
        detail: "未能确认这次自动消息的结果。请查询本次请求，不要重复执行。",
        operationStatus: "unresolved",
        canQuery: true,
        canResend: false,
        canRefreshSession: false,
      });
      throw error;
    }
    if (next.status === "not_committed" && next.safeToRetry) {
      forgetAutomaticStudyRequest(input.operationKey);
    }
    const shouldApply = isCurrentStudyResponseTicket(ticket, next.clientRequestId);
    if (!applyStudyChatOperation(next, draft, ticket) && shouldApply) {
      throw new Error(`study_chat_operation_${next.status}`);
    }
    return next;
  };

  const handleAsk = async (message: string, attachments: File[] = []) => {
    if (!view.session) {
      return false;
    }
    return handleAskForSection(message, view.session.studyUnitId, attachments);
  };

  const handleAskForSection = async (message: string, studyUnitId: string, attachments: File[] = []) => {
    const failure = latest.current.recovery.chatFailure;
    if (!mounted.current || learnerInFlight.current || failure?.canQuery || failure?.canRefreshSession) return false;
    learnerInFlight.current = true;
    setPendingCount(count => count + 1);
    try { return await sendLearnerMessage(message, studyUnitId, attachments); }
    finally { learnerInFlight.current = false; if (mounted.current) setPendingCount(count => count - 1); }
  };

  const sendLearnerMessage = async (message: string, studyUnitId: string, attachments: File[]) => {
    setChatFailure(null);
    let targetSession: StudySessionRecord | null;
    try {
      targetSession = await latest.current.ensureSessionForSection(studyUnitId, {
        clearResponseOnSwitch: false,
      });
    } catch (error) {
      if (!mounted.current) return false;
      latest.current.onNotice(resolveStudySessionErrorNotice(
          error,
          `打开学习会话失败：${String(error)}`,
          "history",
        ));
      logWorkspaceError("workflow:study_session:open_error", error);
      return false;
    }
    if (!mounted.current || !targetSession || view.session?.id !== targetSession.id || view.session.studyUnitId !== studyUnitId) {
      return false;
    }
    const hiddenMessagePrefix =
      latest.current.isDialogueInterruptedForSession(targetSession.id)
        ? latest.current.peekDeferredInteractiveCallbackPrefix(targetSession.id)
        : "";
    const draft: StudyChatDraft = {
      sessionId: targetSession.id,
      clientRequestId: createStudyChatRequestId("learner"),
      expectedSessionRevision: targetSession.revision,
      message,
      studyUnitId,
      attachments,
      messageKind: "learner",
      hiddenMessagePrefix,
    };
    persistPendingStudyOperation(draft);
    const ticket = beginStudyResponseTicket(draft);
    try {
      logWorkspaceInfo("workflow:study_chat:start", {
        sessionId: targetSession.id,
        messageLength: message.length
      });
      const next = await port.sendStudyMessage({
        sessionId: draft.sessionId,
        clientRequestId: draft.clientRequestId,
        expectedSessionRevision: draft.expectedSessionRevision,
        message: draft.message,
        messageKind: draft.messageKind,
        hiddenMessagePrefix: draft.hiddenMessagePrefix,
        attachments: draft.attachments,
      });
      const shouldApply = isCurrentStudyResponseTicket(
        ticket,
        next.clientRequestId,
      );
      const applied = applyStudyChatOperation(next, draft, ticket);
      if (!applied) {
        if (shouldApply) {
          latest.current.onNotice(presentStudyChatOperation(next).detail);
        }
        return false;
      }
      latest.current.clearInterruptedDialogueState(targetSession.id, draft.hiddenMessagePrefix ?? "");
      logWorkspaceInfo("workflow:study_chat:done", {
        sessionId: targetSession.id,
        citations: next.result?.citations.length ?? 0,
        characterEvents: next.result?.characterEvents.length ?? 0,
      });
      return true;
    } catch (error) {
      if (!isCurrentStudyResponseTicket(ticket)) {
        return false;
      }
      if (isDefiniteStudyChatPreAdmissionError(error)) {
        clearPendingStudyOperation(draft);
        setChatFailure({
          ...draft,
          detail: studyChatPreAdmissionNotice(error),
          operationStatus: "unresolved",
          canQuery: false,
          canResend: false,
          canRefreshSession: true,
        });
        latest.current.onNotice("消息尚未被服务端接收；请先刷新会话状态。");
        logWorkspaceError("workflow:study_chat:pre_admission_rejected", error);
        return false;
      }
      setChatFailure({
        ...draft,
        detail: "未能确认本次请求结果。请查询本次请求，不要重新发送。",
        operationStatus: "unresolved",
        canQuery: true,
        canResend: false,
        canRefreshSession: false,
      });
      persistPendingStudyOperation(draft);
      latest.current.onNotice("未能确认本次请求结果；已保留请求身份，请先查询，不要重复发送。");
      logWorkspaceError("workflow:study_chat:error", error);
      return false;
    } finally {
      view.settle(ticket);
    }
  };

  const retryFailedAsk = async () => {
    const chatFailure = latest.current.recovery.chatFailure;
    if (!chatFailure?.canResend) {
      return;
    }
    await handleAskForSection(chatFailure.message, chatFailure.studyUnitId, chatFailure.attachments);
  };


  return { handleAsk, handleAskForSection, retryFailedAsk, sendHiddenSessionMessage,
    automaticStudyRequest, forgetAutomaticStudyRequest, isSending: pendingCount > 0 };
}
