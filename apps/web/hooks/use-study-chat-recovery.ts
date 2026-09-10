"use client";

import { useEffect, useRef, useState } from "react";
import type { StudyChatResponse, StudySessionRecord } from "@vibe-learner/shared";
import { StudyAsyncViewFence, type AsyncResultTicket } from "../lib/async-result-fence";
import { getStudyChatOperation, listStudySessions, type StudyChatOperationResponse } from "../lib/data/study-sessions";
import { isMissingStudyChatOperationError } from "../lib/http-error";
import { logWorkspaceError, logWorkspaceInfo } from "../lib/learning-workspace-telemetry";
import { studyOperationStore, presentStudyChatOperation, type StudyOperationStore, type StudyChatDraft, type ChatFailureState } from "../lib/study-operation-state";

interface StudyRecoveryOptions {
  session: StudySessionRecord | null;
  view: StudyAsyncViewFence<StudySessionRecord>;
  getSelectedPlanId: () => string;
  onExchange: (result: StudyChatResponse & { session: StudySessionRecord }) => void;
  onSession: (session: StudySessionRecord | null, clearResponse: boolean) => void;
  onResetView: () => void;
  onNotice: (notice: string) => void;
}
export interface StudyRecoveryPort {
  getStudyChatOperation: typeof getStudyChatOperation;
  listStudySessions: typeof listStudySessions;
}
const defaultPort: StudyRecoveryPort = { getStudyChatOperation, listStudySessions };

export function useStudyChatRecovery(options: StudyRecoveryOptions,
  port: StudyRecoveryPort = defaultPort, store: StudyOperationStore = studyOperationStore) {
  const { session, view } = options;
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const [chatFailure, setChatFailure] = useState<ChatFailureState | null>(null);
  const [pendingCount, setPendingCount] = useState(0);
  const restoredStudyOperationRef = useRef("");
  const mountedRef = useRef(false);
  const { persistPendingStudyOperation, readPendingStudyOperation, clearPendingStudyOperation } = store;
  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; view.transition("study-recovery:unmounted", true); };
  }, [view]);
  const resetStudyRecovery = () => {
    restoredStudyOperationRef.current = "";
    setChatFailure(null);
  };

  const beginStudyResponseTicket = (draft: StudyChatDraft): AsyncResultTicket =>
    view.begin(
      draft.sessionId,
      draft.clientRequestId,
    );

  const isCurrentStudyResponseTicket = (
    ticket: AsyncResultTicket,
    resultOperationId = ticket.operationId,
  ) =>
    mountedRef.current && view.decide(
      ticket,
      optionsRef.current.getSelectedPlanId(),
      resultOperationId,
    ) === "apply";

  const applyStudyChatOperation = (
    receipt: StudyChatOperationResponse,
    draft: StudyChatDraft,
    ticket: AsyncResultTicket,
  ): boolean => {
    try {
      if (
        !isCurrentStudyResponseTicket(ticket, receipt.clientRequestId)
      ) {
        if (receipt.status === "committed") {
          clearPendingStudyOperation(receipt);
        }
        logWorkspaceInfo("workflow:study_chat:stale_result_discarded", {
          sessionId: receipt.sessionId,
          clientRequestId: receipt.clientRequestId,
        });
        return false;
      }
      if (receipt.status === "committed" && receipt.result) {
        const currentSession = view.session;
        if (currentSession?.id !== receipt.sessionId) {
          clearPendingStudyOperation(receipt);
          return false;
        }
        if (currentSession.revision <= receipt.result.session.revision) {
          optionsRef.current.onExchange(receipt.result);
        }
        setChatFailure(null);
        clearPendingStudyOperation(receipt);
        return true;
      }

      const presentation = presentStudyChatOperation(receipt);
      const canResend = presentation.canResend &&
        draft.messageKind === "learner" &&
        Boolean(draft.message.trim());
      setChatFailure({
        ...draft,
        detail: presentation.canResend && !canResend
          ? draft.messageKind === "learner"
            ? "已确认本次请求没有写入会话。刷新后原消息或附件不可恢复，请重新填写后再发送。"
            : "已确认这次自动消息没有写入会话；流程继续时会使用新的请求身份安全重试。"
          : presentation.detail,
        operationStatus: receipt.status,
        canQuery: presentation.canQuery,
        canResend,
        canRefreshSession: false,
      });
      if (receipt.status === "not_committed") {
        clearPendingStudyOperation(receipt);
      } else {
        persistPendingStudyOperation(draft);
      }
      return false;
    } finally {
      view.settle(ticket);
    }
  };

  const queryStudyChatOperation = async () => {
    if (!mountedRef.current || !chatFailure?.canQuery) {
      return false;
    }
    const ticket = beginStudyResponseTicket(chatFailure);
    try {
      setPendingCount(count => count + 1);
      const receipt = await port.getStudyChatOperation({
        sessionId: chatFailure.sessionId,
        clientRequestId: chatFailure.clientRequestId,
      });
      const applied = applyStudyChatOperation(receipt, chatFailure, ticket);
      if (applied) {
        optionsRef.current.onNotice("已找回并载入本次回复。");
      }
      return applied;
    } catch (error) {
      if (!isCurrentStudyResponseTicket(ticket)) {
        return false;
      }
      if (isMissingStudyChatOperationError(error)) {
        clearPendingStudyOperation(chatFailure);
        setChatFailure((current) => current ? {
          ...current,
          detail: "服务器确认没有找到这次请求。请刷新会话状态后重新发送。",
          canQuery: false,
          canResend: false,
          canRefreshSession: true,
        } : current);
        optionsRef.current.onNotice("没有找到这次请求；请先刷新会话状态。");
        return false;
      }
      setChatFailure((current) => current ? {
        ...current,
        detail: "暂时无法确认本次请求结果。请稍后继续查询，不要重新发送。",
        canQuery: true,
        canResend: false,
        canRefreshSession: false,
      } : current);
      optionsRef.current.onNotice("暂时无法查询本次请求；已保留请求身份，请不要重复发送。");
      logWorkspaceError("workflow:study_chat:operation_query_error", error);
      return false;
    } finally {
      view.settle(ticket);
      if (mountedRef.current) setPendingCount(count => count - 1);
    }
  };

  useEffect(() => {
    const pending = readPendingStudyOperation();
    if (
      !session ||
      !pending ||
      pending.sessionId !== session.id ||
      Boolean(
        pending.studyUnitId &&
        pending.studyUnitId !== session.studyUnitId
      ) ||
      restoredStudyOperationRef.current === pending.clientRequestId
    ) {
      return;
    }
    restoredStudyOperationRef.current = pending.clientRequestId;
    const restoredDraft: StudyChatDraft = {
      ...pending,
      message: "",
      studyUnitId: pending.studyUnitId || session.studyUnitId,
      attachments: [],
      messageKind: pending.messageKind || "learner",
    };
    setChatFailure({
      ...restoredDraft,
      detail: "正在查询刷新前尚未确认的请求结果，请不要重新发送。",
      operationStatus: "unresolved",
      canQuery: true,
      canResend: false,
      canRefreshSession: false,
    });
    const ticket = beginStudyResponseTicket(restoredDraft);
    void (async () => {
      try {
        const receipt = await port.getStudyChatOperation(pending);
        applyStudyChatOperation(receipt, restoredDraft, ticket);
      } catch (error) {
        if (!isCurrentStudyResponseTicket(ticket)) {
          return;
        }
        if (isMissingStudyChatOperationError(error)) {
          clearPendingStudyOperation(pending);
          setChatFailure((current) => current ? {
            ...current,
            detail: "服务器没有找到刷新前的请求。请刷新会话状态后重新发送。",
            canQuery: false,
            canResend: false,
            canRefreshSession: true,
          } : current);
          return;
        }
        setChatFailure((current) => current ? {
          ...current,
          detail: "尚未确认刷新前请求的结果。请点击“查询本次请求结果”，不要重新发送。",
          canQuery: true,
          canResend: false,
          canRefreshSession: false,
        } : current);
        logWorkspaceError("workflow:study_chat:operation_restore_error", error);
      } finally {
        view.settle(ticket);
      }
    })();
  }, [session?.id, session?.studyUnitId]);

  const refreshStudySessionAfterRejectedAdmission = async () => {
    const failure = chatFailure;
    const currentSession = view.session;
    if (!mountedRef.current || !failure?.canRefreshSession || !currentSession) {
      return false;
    }
    const ticket = beginStudyResponseTicket(failure);
    try {
      setPendingCount(count => count + 1);
      const sessions = await port.listStudySessions({
        documentId: currentSession.planId ? undefined : currentSession.documentId,
        planId: currentSession.planId ?? undefined,
        personaId: currentSession.personaId,
        studyUnitId: currentSession.studyUnitId,
      });
      if (!isCurrentStudyResponseTicket(ticket)) {
        return false;
      }
      const refreshed = sessions.find((item) => item.id === currentSession.id) ?? null;
      clearPendingStudyOperation(failure);
      setChatFailure(null);
      if (!refreshed) {
        optionsRef.current.onResetView();
        optionsRef.current.onSession(null, true);
        optionsRef.current.onNotice("原学习会话已不存在。请先创建或选择会话，再重新发送保留的草稿。");
        return false;
      }
      optionsRef.current.onSession(refreshed, false);
      optionsRef.current.onNotice("会话状态已刷新。请确认草稿后重新发送；新发送会使用新的请求身份。");
      return true;
    } catch (error) {
      if (!isCurrentStudyResponseTicket(ticket)) {
        return false;
      }
      setChatFailure((current) => current ? {
        ...current,
        detail: "刷新会话状态失败，草稿仍保留。请稍后重试刷新。",
        canQuery: false,
        canResend: false,
        canRefreshSession: true,
      } : current);
      optionsRef.current.onNotice("刷新会话状态失败，草稿仍保留。");
      logWorkspaceError("workflow:study_chat:refresh_after_rejection_error", error);
      return false;
    } finally {
      view.settle(ticket);
      if (mountedRef.current) setPendingCount(count => count - 1);
    }
  };

  return { chatFailure, setChatFailure, resetStudyRecovery, beginStudyResponseTicket,
    isCurrentStudyResponseTicket, applyStudyChatOperation, queryStudyChatOperation,
    refreshStudySessionAfterRejectedAdmission, isQuerying: pendingCount > 0 };
}
