export class ApiHttpError extends Error {
  readonly status: number;
  readonly code: string;
  readonly payload: unknown;

  constructor(input: {
    status: number;
    code?: string;
    message: string;
    payload: unknown;
  }) {
    super(input.message);
    this.name = "ApiHttpError";
    this.status = input.status;
    this.code = input.code?.trim() ?? "";
    this.payload = input.payload;
  }
}

export function isApiHttpError(error: unknown): error is ApiHttpError {
  return error instanceof ApiHttpError || (
    typeof error === "object" &&
    error !== null &&
    "name" in error &&
    error.name === "ApiHttpError" &&
    "status" in error &&
    Number.isInteger(error.status) &&
    "code" in error &&
    typeof error.code === "string"
  );
}

export function extractApiErrorCode(payload: unknown): string {
  if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
    return "";
  }
  const record = payload as Record<string, unknown>;
  if (typeof record.code === "string") {
    return record.code.trim();
  }
  return extractApiErrorCode(record.detail);
}

const DEFINITE_STUDY_CHAT_PRE_ADMISSION_CODES = new Set([
  "session_not_found",
  "study_chat_session_revision_conflict",
  "study_chat_request_id_reused",
  "study_chat_operation_already_active",
]);

export function isDefiniteStudyChatPreAdmissionError(error: unknown): boolean {
  if (!isApiHttpError(error)) {
    return false;
  }
  if (error.status === 422) {
    return true;
  }
  return (error.status === 404 || error.status === 409) &&
    DEFINITE_STUDY_CHAT_PRE_ADMISSION_CODES.has(error.code);
}

export function isMissingStudyChatOperationError(error: unknown): boolean {
  return isApiHttpError(error) &&
    error.status === 404 &&
    error.code === "study_chat_operation_not_found";
}

export function studyChatPreAdmissionNotice(error: unknown): string {
  if (!isApiHttpError(error)) {
    return "本次请求尚未被接收。请刷新会话状态后再发送。";
  }
  if (error.code === "session_not_found") {
    return "原学习会话已不存在。请刷新会话状态，再决定是否新建会话。";
  }
  if (error.code === "study_chat_session_revision_conflict") {
    return "会话已在其他操作中更新。本次消息尚未发送，请刷新会话状态后再发送。";
  }
  if (error.code === "study_chat_request_id_reused") {
    return "本次请求身份与已有请求冲突，消息尚未发送。请刷新会话状态后重新发送。";
  }
  if (error.code === "study_chat_operation_already_active") {
    return "会话中已有请求正在处理，本次消息尚未发送。请刷新会话状态后继续。";
  }
  return "请求内容未通过服务端校验，消息尚未发送。请检查内容或刷新会话状态后再试。";
}
