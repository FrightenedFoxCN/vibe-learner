"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { StudyChatResponse, StudySessionRecord } from "@vibe-learner/shared";
import { StudyAsyncViewFence, type AsyncResultTicket } from "../lib/async-result-fence";
import {
  getStudyChatOperation,
  listStudySessions,
  type StudyChatOperationResponse,
} from "../lib/data/study-sessions";
import { isMissingStudyChatOperationError } from "../lib/http-error";
import {
  withStudyRequestDeadline,
  STUDY_QUERY_WAIT_MS,
} from "../lib/study-request-deadline";
import {
  logWorkspaceError,
  logWorkspaceInfo,
} from "../lib/learning-workspace-telemetry";
import {
  studyOperationStore,
  presentStudyChatOperation,
  type StudyOperationStore,
  type StudyChatDraft,
  type ChatFailureState,
} from "../lib/study-operation-state";

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

// Six background reads per operation/view. Foreground recovery remains available.
export const STUDY_RECOVERY_QUERY_DELAYS_MS = [
  2000, 4000, 8000, 15000, 30000, 30000,
] as const;

export function useStudyChatRecovery(
  options: StudyRecoveryOptions,
  port: StudyRecoveryPort = defaultPort,
  store: StudyOperationStore = studyOperationStore,
) {
  const { session, view } = options;
  const optionsRef = useRef(options);
  optionsRef.current = options;
  const portRef = useRef(port);
  portRef.current = port;
  const [chatFailure, setChatFailure] = useState<ChatFailureState | null>(null);
  const failureRef = useRef(chatFailure);
  failureRef.current = chatFailure;
  const [pendingCount, setPendingCount] = useState(0);
  const [online, setOnline] = useState(
    () => typeof navigator === "undefined" || navigator.onLine !== false,
  );
  const [transportPaused, setTransportPaused] = useState(false);
  const [automaticQueries, setAutomaticQueries] = useState({ key: "", count: 0 });
  const restoredStudyOperationRef = useRef("");
  const queryInFlight = useRef<AsyncResultTicket | null>(null);
  const mountedRef = useRef(false);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
      view.transition("study-recovery:unmounted", true);
    };
  }, [view]);

  const resetStudyRecovery = useCallback(() => {
    restoredStudyOperationRef.current = "";
    setChatFailure(null);
    setTransportPaused(false);
  }, []);

  const beginStudyResponseTicket = useCallback(
    (draft: StudyChatDraft): AsyncResultTicket => {
      // An operation started by this mounted view must not be mistaken for a
      // restored request when a parent rerenders or the transport port changes.
      restoredStudyOperationRef.current = draft.clientRequestId;
      return view.begin(draft.sessionId, draft.clientRequestId);
    },
    [view],
  );

  const isCurrentStudyResponseTicket = useCallback(
    (ticket: AsyncResultTicket, resultOperationId = ticket.operationId) =>
      mountedRef.current &&
      view.decide(ticket, optionsRef.current.getSelectedPlanId(), resultOperationId) ===
        "apply",
    [view],
  );

  const applyStudyChatOperation = useCallback(
    (
      receipt: StudyChatOperationResponse,
      draft: StudyChatDraft,
      ticket: AsyncResultTicket,
    ): boolean => {
      try {
        if (!isCurrentStudyResponseTicket(ticket, receipt.clientRequestId)) {
          if (receipt.status === "committed") store.clearPendingStudyOperation(receipt);
          logWorkspaceInfo("workflow:study_chat:stale_result_discarded", {
            sessionId: receipt.sessionId,
            clientRequestId: receipt.clientRequestId,
          });
          return false;
        }
        if (receipt.status === "committed" && receipt.result) {
          const currentSession = view.session;
          if (currentSession?.id !== receipt.sessionId) {
            store.clearPendingStudyOperation(receipt);
            return false;
          }
          if (currentSession.revision <= receipt.result.session.revision) {
            optionsRef.current.onExchange(receipt.result);
          }
          setChatFailure(null);
          store.clearPendingStudyOperation(receipt);
          store.clearLastNotCommittedStudyOperation(receipt);
          return true;
        }
        const presentation = presentStudyChatOperation(receipt);
        const canResend =
          presentation.canResend &&
          draft.messageKind === "learner" &&
          Boolean(draft.message.trim());
        setChatFailure({
          ...draft,
          detail:
            presentation.canResend && !canResend
              ? draft.messageKind === "learner"
                ? "已确认本次请求没有写入会话。恢复记录不保存原消息或附件，请检查输入框并重新选择附件后发送新请求。"
                : "已确认这次自动消息没有写入会话；流程继续时会使用新的请求身份安全重试。"
              : presentation.detail,
          operationStatus: receipt.status,
          canQuery: presentation.canQuery,
          canResend,
          canRefreshSession: false,
        });
        if (receipt.status === "not_committed") {
          store.clearPendingStudyOperation(receipt);
          store.rememberNotCommittedStudyOperation(draft);
        } else {
          store.persistPendingStudyOperation(draft);
        }
        return false;
      } finally {
        view.settle(ticket);
      }
    },
    [isCurrentStudyResponseTicket, store, view],
  );

  const readBack = useCallback(
    async (draft: StudyChatDraft): Promise<boolean> => {
      if (
        !mountedRef.current ||
        view.session?.id !== draft.sessionId ||
        view.session.studyUnitId !== draft.studyUnitId
      )
        return false;
      if (typeof navigator !== "undefined" && navigator.onLine === false) {
        optionsRef.current.onNotice(
          "浏览器当前离线，已保留请求身份。联网后只查询原请求，不重新生成。",
        );
        return false;
      }
      if (
        queryInFlight.current?.subjectId === draft.sessionId &&
        queryInFlight.current.operationId === draft.clientRequestId
      )
        return false;
      const ticket = beginStudyResponseTicket(draft);
      queryInFlight.current = ticket;
      setTransportPaused(false);
      setPendingCount((count) => count + 1);
      try {
        const receipt = await portRef.current.getStudyChatOperation({
          sessionId: draft.sessionId,
          clientRequestId: draft.clientRequestId,
        });
        const applied = applyStudyChatOperation(receipt, draft, ticket);
        if (applied)
          optionsRef.current.onNotice("已找回本次已保存的回复，会话内容已同步。");
        return applied;
      } catch (error) {
        if (!isCurrentStudyResponseTicket(ticket)) return false;
        if (isMissingStudyChatOperationError(error)) {
          store.clearPendingStudyOperation(draft);
          store.clearLastNotCommittedStudyOperation(draft);
          setChatFailure({
            ...draft,
            detail: "服务器确认没有找到这次请求。请刷新会话状态后重新发送。",
            operationStatus: "unresolved",
            canQuery: false,
            canResend: false,
            canRefreshSession: true,
          });
          optionsRef.current.onNotice("没有找到这次请求；请先刷新会话状态。");
          return false;
        }
        setTransportPaused(true);
        setChatFailure((current) =>
          current &&
          current.sessionId === draft.sessionId &&
          current.clientRequestId === draft.clientRequestId
            ? {
                ...current,
                detail:
                  "查询未能确认本次请求结果，后台查询已暂停。请求身份仍保留；请稍后手动查询，勿重新发送。",
                canQuery: true,
                canResend: false,
                canRefreshSession: false,
              }
            : current,
        );
        optionsRef.current.onNotice("查询未成功；已保留请求身份，请勿重复发送。");
        logWorkspaceError("workflow:study_chat:operation_query_error", error);
        return false;
      } finally {
        view.settle(ticket);
        if (queryInFlight.current === ticket) queryInFlight.current = null;
        if (mountedRef.current) setPendingCount((count) => count - 1);
      }
    },
    [
      applyStudyChatOperation,
      beginStudyResponseTicket,
      isCurrentStudyResponseTicket,
      store,
      view,
    ],
  );

  const queryStudyChatOperation = useCallback(() => {
    const failure = failureRef.current;
    return failure?.canQuery ? readBack(failure) : Promise.resolve(false);
  }, [readBack]);

  useEffect(() => {
    const sync = () => {
      const connected = navigator.onLine !== false;
      setOnline(connected);
      // Reconnection issues one GET for the retained identity, never a POST.
      if (connected && failureRef.current?.canQuery) void readBack(failureRef.current);
    };
    window.addEventListener("online", sync);
    window.addEventListener("offline", sync);
    return () => {
      window.removeEventListener("online", sync);
      window.removeEventListener("offline", sync);
    };
  }, [readBack]);

  useEffect(() => {
    const pending =
      store.readPendingStudyOperation() ?? store.readLastNotCommittedStudyOperation();
    if (
      !session ||
      !pending ||
      pending.sessionId !== session.id ||
      (pending.studyUnitId && pending.studyUnitId !== session.studyUnitId) ||
      restoredStudyOperationRef.current === pending.clientRequestId
    )
      return;
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
      detail: "正在查询离开页面前尚未确认的请求，只读取已保存结果，请勿重新发送。",
      operationStatus: "unresolved",
      canQuery: true,
      canResend: false,
      canRefreshSession: false,
    });
    void readBack(restoredDraft);
  }, [session, readBack, store]);

  useEffect(() => {
    if (
      !chatFailure?.canQuery ||
      !session ||
      session.id !== chatFailure.sessionId ||
      session.studyUnitId !== chatFailure.studyUnitId
    )
      return;
    const key = `${chatFailure.sessionId}:${chatFailure.clientRequestId}`;
    if (automaticQueries.key !== key) {
      setAutomaticQueries({ key, count: 0 });
      setTransportPaused(false);
      return;
    }
    if (
      !online ||
      pendingCount > 0 ||
      transportPaused ||
      !["admitted", "running"].includes(chatFailure.operationStatus) ||
      automaticQueries.count >= STUDY_RECOVERY_QUERY_DELAYS_MS.length
    )
      return;
    const timer = setTimeout(() => {
      setAutomaticQueries((current) => ({ ...current, count: current.count + 1 }));
      void readBack(chatFailure);
    }, STUDY_RECOVERY_QUERY_DELAYS_MS[automaticQueries.count]);
    return () => clearTimeout(timer);
  }, [
    automaticQueries,
    chatFailure,
    online,
    pendingCount,
    readBack,
    transportPaused,
    session,
  ]);

  const refreshStudySessionAfterRejectedAdmission = async () => {
    const failure = failureRef.current;
    const currentSession = view.session;
    if (
      !mountedRef.current ||
      !failure?.canRefreshSession ||
      !currentSession ||
      queryInFlight.current
    )
      return false;
    const ticket = beginStudyResponseTicket(failure);
    queryInFlight.current = ticket;
    try {
      setPendingCount((count) => count + 1);
      const sessions = await withStudyRequestDeadline(STUDY_QUERY_WAIT_MS, (signal) =>
        portRef.current.listStudySessions({
          documentId: currentSession.planId ? undefined : currentSession.documentId,
          planId: currentSession.planId ?? undefined,
          personaId: currentSession.personaId,
          studyUnitId: currentSession.studyUnitId,
          signal,
        }),
      );
      if (!isCurrentStudyResponseTicket(ticket)) return false;
      const refreshed = sessions.find((item) => item.id === currentSession.id) ?? null;
      store.clearPendingStudyOperation(failure);
      store.clearLastNotCommittedStudyOperation(failure);
      setChatFailure(null);
      if (!refreshed) {
        optionsRef.current.onResetView();
        optionsRef.current.onSession(null, true);
        optionsRef.current.onNotice(
          "原学习会话已不存在。请先创建或选择会话，再检查草稿后发送。",
        );
        return false;
      }
      optionsRef.current.onSession(refreshed, false);
      optionsRef.current.onNotice(
        "会话状态已刷新。请确认草稿后重新发送；新发送会使用新的请求身份。",
      );
      return true;
    } catch (error) {
      if (!isCurrentStudyResponseTicket(ticket)) return false;
      setChatFailure((current) =>
        current
          ? {
              ...current,
              detail:
                "刷新会话状态失败，请稍后重试；当前输入仍保留，附件需在刷新页面后重新选择。",
              canQuery: false,
              canResend: false,
              canRefreshSession: true,
            }
          : current,
      );
      logWorkspaceError("workflow:study_chat:refresh_after_rejection_error", error);
      return false;
    } finally {
      view.settle(ticket);
      if (queryInFlight.current === ticket) queryInFlight.current = null;
      if (mountedRef.current) setPendingCount((count) => count - 1);
    }
  };

  const autoPaused =
    automaticQueries.key ===
      `${chatFailure?.sessionId}:${chatFailure?.clientRequestId}` &&
    automaticQueries.count >= STUDY_RECOVERY_QUERY_DELAYS_MS.length &&
    chatFailure &&
    ["admitted", "running"].includes(chatFailure.operationStatus) &&
    pendingCount === 0;
  const displayFailure = chatFailure
    ? {
        ...chatFailure,
        detail:
          !online && chatFailure.canQuery
            ? "浏览器当前离线，无法确认请求结果。已保留原请求身份；联网后只查询已保存结果，请勿重新发送。"
            : autoPaused
              ? `${chatFailure.detail} 自动查询已暂停（已查询 ${automaticQueries.count} 次）。长时间等待不代表失败或未写入；可稍后手动查询。`
              : chatFailure.detail,
      }
    : null;

  return {
    chatFailure: displayFailure,
    setChatFailure,
    resetStudyRecovery,
    beginStudyResponseTicket,
    isCurrentStudyResponseTicket,
    applyStudyChatOperation,
    queryStudyChatOperation,
    refreshStudySessionAfterRejectedAdmission,
    isQuerying: pendingCount > 0,
  };
}
