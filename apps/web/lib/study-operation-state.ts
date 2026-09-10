import { createStudyChatRequestId } from "./client-request-id";
import type { StudyChatOperationStatus } from "./study-chat-operation-decode";
import type { StudyChatOperationResponse } from "./data/study-sessions";

export type ChatFailureState = {
  message: string;
  studyUnitId: string;
  detail: string;
  attachments: File[];
  sessionId: string;
  clientRequestId: string;
  expectedSessionRevision: number;
  messageKind: string;
  followUpId?: string;
  hiddenMessagePrefix?: string;
  operationStatus: StudyChatOperationStatus | "unresolved";
  canQuery: boolean;
  canResend: boolean;
  canRefreshSession: boolean;
};

export type StudyChatDraft = Omit<
  ChatFailureState,
  "detail" | "operationStatus" | "canQuery" | "canResend" | "canRefreshSession"
>;

export type PendingStudyOperationIdentity = Pick<
  StudyChatDraft,
  "sessionId" | "clientRequestId" | "expectedSessionRevision"
> & {
  messageKind?: string;
  studyUnitId?: string;
};

const PENDING_STUDY_OPERATION_STORAGE_KEY = "vibe-learner:pending-study-chat-operation:v1";
const AUTOMATIC_STUDY_REQUEST_STORAGE_KEY = "vibe-learner:automatic-study-chat-requests:v1";

export function presentStudyChatOperation(receipt: StudyChatOperationResponse): {
  detail: string;
  canQuery: boolean;
  canResend: boolean;
} {
  switch (receipt.status) {
    case "admitted":
      return {
        detail: "本次请求已接收，尚未开始生成。请查询本次请求结果，不要重新发送。",
        canQuery: true,
        canResend: false,
      };
    case "running":
      return {
        detail: "本次回复仍在生成。请稍后查询本次请求结果，不要重新发送。",
        canQuery: true,
        canResend: false,
      };
    case "uncertain":
      return {
        detail: "系统暂时无法确认本次请求是否已产生影响。请继续查询，不要重新发送。",
        canQuery: true,
        canResend: false,
      };
    case "not_committed":
      return {
        detail: receipt.safeToRetry
          ? "已确认本次请求没有写入会话。你可以重新发送，新发送会使用新的请求身份。"
          : "本次请求未写入会话，但当前不允许重新发送。",
        canQuery: false,
        canResend: receipt.safeToRetry,
      };
    case "committed":
      return { detail: "本次回复已完成。", canQuery: false, canResend: false };
  }
}


export type StudyOperationStorage = Pick<Storage, "getItem" | "setItem" | "removeItem">;
export function createStudyOperationStore(
  resolveStorage: () => StudyOperationStorage | null,
  createRequestId: (scope: string) => string = createStudyChatRequestId,
) {
  const getStorage = () => {
    try { return resolveStorage(); } catch { return null; }
  };
  function getOrCreateAutomaticRequestId(
    requests: Map<string, string>,
    key: string,
    scope: string,
  ): { clientRequestId: string; queryExisting: boolean } {
    const existing = requests.get(key);
    if (existing) {
      return { clientRequestId: existing, queryExisting: true };
    }
    const persisted = readAutomaticStudyRequestIds();
    const persistedId = persisted[key];
    if (persistedId) {
      requests.set(key, persistedId);
      return { clientRequestId: persistedId, queryExisting: true };
    }
    const created = createRequestId(scope);
    requests.set(key, created);
    persistAutomaticStudyRequestId(key, created, persisted);
    return { clientRequestId: created, queryExisting: false };
  }

  function forgetAutomaticStudyRequestId(requests: Map<string, string>, key: string): void {
    requests.delete(key);
    if (!getStorage()) {
      return;
    }
    try {
      const persisted = readAutomaticStudyRequestIds();
      delete persisted[key];
      getStorage()!.setItem(
        AUTOMATIC_STUDY_REQUEST_STORAGE_KEY,
        JSON.stringify(persisted),
      );
    } catch {
      // A fresh page may rediscover the terminal receipt before creating a new request.
    }
  }

  function readAutomaticStudyRequestIds(): Record<string, string> {
    if (!getStorage()) {
      return {};
    }
    try {
      const raw = getStorage()!.getItem(AUTOMATIC_STUDY_REQUEST_STORAGE_KEY);
      if (!raw) {
        return {};
      }
      const parsed = JSON.parse(raw) as Record<string, unknown>;
      return Object.fromEntries(
        Object.entries(parsed).filter((entry): entry is [string, string] =>
          Boolean(entry[0] && typeof entry[1] === "string" && entry[1].trim())
        ),
      );
    } catch {
      return {};
    }
  }

  function persistAutomaticStudyRequestId(
    key: string,
    requestId: string,
    current: Record<string, string>,
  ): void {
    if (!getStorage()) {
      return;
    }
    try {
      const entries = Object.entries({ ...current, [key]: requestId }).slice(-64);
      getStorage()!.setItem(
        AUTOMATIC_STUDY_REQUEST_STORAGE_KEY,
        JSON.stringify(Object.fromEntries(entries)),
      );
    } catch {
      // The mounted controller Map still preserves identity for this page lifetime.
    }
  }

  function persistPendingStudyOperation(operation: PendingStudyOperationIdentity): void {
    if (!getStorage()) {
      return;
    }
    try {
      getStorage()!.setItem(
        PENDING_STUDY_OPERATION_STORAGE_KEY,
        JSON.stringify({
          sessionId: operation.sessionId,
          clientRequestId: operation.clientRequestId,
          expectedSessionRevision: operation.expectedSessionRevision,
          messageKind: operation.messageKind,
          studyUnitId: operation.studyUnitId,
        }),
      );
    } catch {
      // Recovery remains available for this mounted page even when storage is unavailable.
    }
  }

  function readPendingStudyOperation(): PendingStudyOperationIdentity | null {
    if (!getStorage()) {
      return null;
    }
    try {
      const raw = getStorage()!.getItem(PENDING_STUDY_OPERATION_STORAGE_KEY);
      if (!raw) {
        return null;
      }
      const value = JSON.parse(raw) as Record<string, unknown>;
      if (
        typeof value.sessionId !== "string" ||
        !value.sessionId.trim() ||
        typeof value.clientRequestId !== "string" ||
        !value.clientRequestId.trim() ||
        !Number.isSafeInteger(value.expectedSessionRevision) ||
        Number(value.expectedSessionRevision) < 0
      ) {
        return null;
      }
      return {
        sessionId: value.sessionId,
        clientRequestId: value.clientRequestId,
        expectedSessionRevision: Number(value.expectedSessionRevision),
        messageKind: typeof value.messageKind === "string" ? value.messageKind : undefined,
        studyUnitId: typeof value.studyUnitId === "string" ? value.studyUnitId : undefined,
      };
    } catch {
      return null;
    }
  }

  function clearPendingStudyOperation(operation: Pick<PendingStudyOperationIdentity, "sessionId" | "clientRequestId">): void {
    if (!getStorage()) {
      return;
    }
    const pending = readPendingStudyOperation();
    if (
      pending?.sessionId !== operation.sessionId ||
      pending.clientRequestId !== operation.clientRequestId
    ) {
      return;
    }
    try {
      getStorage()!.removeItem(PENDING_STUDY_OPERATION_STORAGE_KEY);
    } catch {
      // Ignore storage failures after the in-memory state has already converged.
    }
  }

  return { getOrCreateAutomaticRequestId, forgetAutomaticStudyRequestId,
    persistPendingStudyOperation, readPendingStudyOperation, clearPendingStudyOperation };
}
export const studyOperationStore = createStudyOperationStore(() => typeof window === "undefined" ? null : window.localStorage);
export type StudyOperationStore = ReturnType<typeof createStudyOperationStore>;
