import type { DialogueTurnRecord, StudySessionRecord } from "@vibe-learner/shared";

export class StudySessionDecodeError extends Error {
  readonly code = "study_session_response_decode_error";
  readonly path: string;

  constructor(path: string, reason: string) {
    super(`${reason} at ${path}`);
    this.name = "StudySessionDecodeError";
    this.path = path;
  }
}

export function isStudySessionDecodeError(
  error: unknown,
): error is StudySessionDecodeError {
  return error instanceof StudySessionDecodeError || (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    error.code === "study_session_response_decode_error"
  );
}

export type StudySessionDecodeNoticeContext = "history" | "response" | "update";

const STUDY_SESSION_DECODE_NOTICES: Record<StudySessionDecodeNoticeContext, string> = {
  history:
    "历史学习会话格式异常，已停止载入以保护记录。请刷新；若仍出现，请查看调试信息。",
  response:
    "回复校验失败，已停止更新页面以保护会话记录。请先刷新恢复最新会话，不要重复发送本次消息；详细原因已记录到调试信息。",
  update:
    "会话更新结果校验失败，已停止更新页面以保护记录。请先刷新确认最新状态，不要重复操作；详细原因已记录到调试信息。",
};

export function resolveStudySessionErrorNotice(
  error: unknown,
  fallback: string,
  context: StudySessionDecodeNoticeContext,
): string {
  return isStudySessionDecodeError(error)
    ? STUDY_SESSION_DECODE_NOTICES[context]
    : fallback;
}

export interface StudyChatFailurePresentation {
  detail: string;
  retryAllowed: boolean;
}

export function resolveStudyChatFailurePresentation(
  error: unknown,
): StudyChatFailurePresentation | null {
  if (isStudySessionDecodeError(error)) {
    // The server may already have committed the visible turn. Keep the raw
    // decoder path in telemetry only and do not offer a blind replay.
    return null;
  }
  return {
    detail: String(error),
    retryAllowed: true,
  };
}

function record(raw: unknown, path: string): Record<string, unknown> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new StudySessionDecodeError(path, "expected_object");
  }
  return raw as Record<string, unknown>;
}

function required(value: Record<string, unknown>, key: string, path: string): unknown {
  if (!Object.prototype.hasOwnProperty.call(value, key)) {
    throw new StudySessionDecodeError(`${path}.${key}`, "missing_required_field");
  }
  return value[key];
}

function nonEmptyString(raw: unknown, path: string): string {
  if (typeof raw !== "string" || !raw.trim()) {
    throw new StudySessionDecodeError(path, "expected_non_empty_string");
  }
  return raw;
}

function safeInteger(raw: unknown, path: string, minimum: number): number {
  if (!Number.isSafeInteger(raw) || (raw as number) < minimum) {
    throw new StudySessionDecodeError(path, `expected_safe_integer_at_least_${minimum}`);
  }
  return raw as number;
}

function decodeTurnIdentity(
  raw: unknown,
  index: number,
  path: string,
): Pick<DialogueTurnRecord, "id" | "sequence"> {
  const value = record(raw, path);
  const sequence = safeInteger(required(value, "sequence", path), `${path}.sequence`, 1);
  if (sequence !== index + 1) {
    throw new StudySessionDecodeError(`${path}.sequence`, `expected_contiguous_sequence_${index + 1}`);
  }
  return {
    id: nonEmptyString(required(value, "id", path), `${path}.id`),
    sequence,
  };
}

export interface StudySessionCommittedIdentity {
  revision: number;
  lastTurnSequence: number;
  turns: Array<Pick<DialogueTurnRecord, "id" | "sequence">>;
}

export function decodeStudySessionCommittedIdentity(
  raw: unknown,
  path = "study_session",
): StudySessionCommittedIdentity {
  const value = record(raw, path);
  const revision = safeInteger(required(value, "revision", path), `${path}.revision`, 0);
  const lastTurnSequence = safeInteger(
    required(value, "last_turn_sequence", path),
    `${path}.last_turn_sequence`,
    0,
  );
  const rawTurns = required(value, "turns", path);
  if (!Array.isArray(rawTurns)) {
    throw new StudySessionDecodeError(`${path}.turns`, "expected_array");
  }
  const turns = rawTurns.map((turn, index) =>
    decodeTurnIdentity(turn, index, `${path}.turns[${index}]`)
  );
  const ids = turns.map((turn) => turn.id);
  if (new Set(ids).size !== ids.length) {
    throw new StudySessionDecodeError(`${path}.turns`, "expected_unique_turn_ids");
  }
  if (lastTurnSequence !== turns.length) {
    throw new StudySessionDecodeError(
      `${path}.last_turn_sequence`,
      `expected_turn_count_${turns.length}`,
    );
  }
  return { revision, lastTurnSequence, turns };
}

export function orderStudySessionTurns(
  turns: StudySessionRecord["turns"],
): StudySessionRecord["turns"] {
  return [...turns].sort((left, right) => left.sequence - right.sequence);
}
