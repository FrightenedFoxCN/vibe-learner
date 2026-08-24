export const STUDY_CHAT_OPERATION_STATUSES = [
  "admitted",
  "running",
  "committed",
  "not_committed",
  "uncertain",
] as const;

export type StudyChatOperationStatus =
  (typeof STUDY_CHAT_OPERATION_STATUSES)[number];

export interface StudyChatOperationReceipt<TResult = Record<string, unknown>> {
  operationId: string;
  sessionId: string;
  clientRequestId: string;
  status: StudyChatOperationStatus;
  safeToRetry: boolean;
  admittedSessionRevision: number;
  committedSessionRevision: number | null;
  committedTurnId: string | null;
  committedTurnSequence: number | null;
  result: TResult | null;
  errorCode: string;
  createdAt: string;
  updatedAt: string;
  completedAt: string | null;
}

export class StudyChatOperationDecodeError extends Error {
  readonly code = "study_chat_operation_response_decode_error";
  readonly path: string;

  constructor(path: string, reason: string) {
    super(`${reason} at ${path}`);
    this.name = "StudyChatOperationDecodeError";
    this.path = path;
  }
}

export function isStudyChatOperationDecodeError(
  error: unknown,
): error is StudyChatOperationDecodeError {
  return error instanceof StudyChatOperationDecodeError || (
    typeof error === "object" &&
    error !== null &&
    "code" in error &&
    error.code === "study_chat_operation_response_decode_error"
  );
}

export interface StudyChatCommittedResultEvidence {
  operationId: string;
  sessionId: string;
  clientRequestId: string;
  admittedSessionRevision: number;
  committedSessionRevision: number;
  committedTurnId: string;
  committedTurnSequence: number;
}

export interface DecodeStudyChatOperationOptions<TResult> {
  path?: string;
  expectedSessionId: string;
  expectedClientRequestId: string;
  decodeResult: (
    raw: Record<string, unknown>,
    path: string,
    evidence: StudyChatCommittedResultEvidence,
  ) => TResult;
}

/**
 * Strictly decodes the public Study Chat operation receipt before callers use
 * it to decide whether a request may be recovered or sent again. The nested
 * committed chat result remains a separate contract boundary: api.ts can
 * inject its existing Study Chat/Session decoder through `decodeResult`.
 */
export function decodeStudyChatOperationReceipt<
  TResult,
>(
  raw: unknown,
  options: DecodeStudyChatOperationOptions<TResult>,
): StudyChatOperationReceipt<TResult> {
  const path = options?.path ?? "study_chat_operation";
  if (!options || typeof options.decodeResult !== "function") {
    throw new StudyChatOperationDecodeError(
      `${path}.result`,
      "committed_result_decoder_required",
    );
  }
  const value = record(raw, path);
  const operationId = boundedNonEmptyString(
    required(value, "operation_id", path),
    `${path}.operation_id`,
    64,
  );
  const sessionId = boundedNonEmptyString(
    required(value, "session_id", path),
    `${path}.session_id`,
    64,
  );
  const clientRequestId = boundedNonEmptyString(
    required(value, "client_request_id", path),
    `${path}.client_request_id`,
    80,
  );
  assertExpectedIdentity(
    sessionId,
    options.expectedSessionId,
    `${path}.session_id`,
    "session_identity_mismatch",
  );
  assertExpectedIdentity(
    clientRequestId,
    options.expectedClientRequestId,
    `${path}.client_request_id`,
    "client_request_identity_mismatch",
  );
  const status = operationStatus(
    required(value, "status", path),
    `${path}.status`,
  );
  const admittedSessionRevision = safeInteger(
    required(value, "admitted_session_revision", path),
    `${path}.admitted_session_revision`,
    0,
  );
  const safeToRetry = booleanValue(
    required(value, "safe_to_retry", path),
    `${path}.safe_to_retry`,
  );

  const committedSessionRevision = nullableSafeInteger(
    required(value, "committed_session_revision", path),
    `${path}.committed_session_revision`,
    0,
  );
  const committedTurnId = nullableNonEmptyString(
    required(value, "committed_turn_id", path),
    `${path}.committed_turn_id`,
  );
  const committedTurnSequence = nullableSafeInteger(
    required(value, "committed_turn_sequence", path),
    `${path}.committed_turn_sequence`,
    1,
  );
  const rawResult = required(value, "result", path);
  const completedAt = nullableTimestamp(
    required(value, "completed_at", path),
    `${path}.completed_at`,
  );

  const isCommitted = status === "committed";
  const isTerminal = isCommitted || status === "not_committed" || status === "uncertain";

  if (safeToRetry !== (status === "not_committed")) {
    throw new StudyChatOperationDecodeError(
      `${path}.safe_to_retry`,
      status === "not_committed"
        ? "expected_true_for_not_committed"
        : `expected_false_for_${status}`,
    );
  }
  if (isTerminal !== (completedAt !== null)) {
    throw new StudyChatOperationDecodeError(
      `${path}.completed_at`,
      isTerminal ? "expected_terminal_timestamp" : "expected_null_before_terminal",
    );
  }

  let result: TResult | null = null;
  if (isCommitted) {
    if (committedSessionRevision === null) {
      throw new StudyChatOperationDecodeError(
        `${path}.committed_session_revision`,
        "expected_integer_for_committed",
      );
    }
    if (committedSessionRevision < admittedSessionRevision) {
      throw new StudyChatOperationDecodeError(
        `${path}.committed_session_revision`,
        "expected_revision_not_before_admission",
      );
    }
    if (committedTurnId === null) {
      throw new StudyChatOperationDecodeError(
        `${path}.committed_turn_id`,
        "expected_non_empty_string_for_committed",
      );
    }
    if (committedTurnSequence === null) {
      throw new StudyChatOperationDecodeError(
        `${path}.committed_turn_sequence`,
        "expected_positive_integer_for_committed",
      );
    }
    const resultPath = `${path}.result`;
    const resultRecord = record(rawResult, resultPath);
    const evidence = {
      operationId,
      sessionId,
      clientRequestId,
      admittedSessionRevision,
      committedSessionRevision,
      committedTurnId,
      committedTurnSequence,
    };
    validateCommittedResultBinding(resultRecord, resultPath, evidence);
    try {
      result = options.decodeResult(resultRecord, resultPath, evidence);
    } catch (error) {
      if (isStudyChatOperationDecodeError(error) || isStudySessionDecodeError(error)) {
        throw error;
      }
      throw new StudyChatOperationDecodeError(
        resultPath,
        "committed_result_decode_failed",
      );
    }
    if (result === null || result === undefined) {
      throw new StudyChatOperationDecodeError(
        `${path}.result`,
        "decoded_committed_result_required",
      );
    }
  } else {
    assertNull(
      committedSessionRevision,
      `${path}.committed_session_revision`,
      `expected_null_for_${status}`,
    );
    assertNull(
      committedTurnId,
      `${path}.committed_turn_id`,
      `expected_null_for_${status}`,
    );
    assertNull(
      committedTurnSequence,
      `${path}.committed_turn_sequence`,
      `expected_null_for_${status}`,
    );
    assertNull(rawResult, `${path}.result`, `expected_null_for_${status}`);
  }

  const createdAt = timestamp(
    required(value, "created_at", path),
    `${path}.created_at`,
  );
  const updatedAt = timestamp(
    required(value, "updated_at", path),
    `${path}.updated_at`,
  );
  assertTimestampOrder(createdAt, updatedAt, `${path}.updated_at`);
  if (completedAt !== null) {
    assertTimestampOrder(updatedAt, completedAt, `${path}.completed_at`);
  }

  return {
    operationId,
    sessionId,
    clientRequestId,
    status,
    safeToRetry,
    admittedSessionRevision,
    committedSessionRevision,
    committedTurnId,
    committedTurnSequence,
    result,
    errorCode: operationErrorCode(
      required(value, "error_code", path),
      `${path}.error_code`,
      status,
    ),
    createdAt,
    updatedAt,
    completedAt,
  };
}

function isStudySessionDecodeError(error: unknown): boolean {
  return typeof error === "object" && error !== null && "code" in error &&
    error.code === "study_session_response_decode_error";
}

function record(raw: unknown, path: string): Record<string, unknown> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) {
    throw new StudyChatOperationDecodeError(path, "expected_object");
  }
  return raw as Record<string, unknown>;
}

function required(
  value: Record<string, unknown>,
  key: string,
  path: string,
): unknown {
  if (!Object.prototype.hasOwnProperty.call(value, key)) {
    throw new StudyChatOperationDecodeError(
      `${path}.${key}`,
      "missing_required_field",
    );
  }
  return value[key];
}

function stringValue(raw: unknown, path: string): string {
  if (typeof raw !== "string") {
    throw new StudyChatOperationDecodeError(path, "expected_string");
  }
  return raw;
}

function nonEmptyString(raw: unknown, path: string): string {
  const value = stringValue(raw, path);
  if (!value.trim()) {
    throw new StudyChatOperationDecodeError(path, "expected_non_empty_string");
  }
  return value;
}

function boundedNonEmptyString(
  raw: unknown,
  path: string,
  maximum: number,
): string {
  const value = nonEmptyString(raw, path);
  if (value.length > maximum) {
    throw new StudyChatOperationDecodeError(path, `expected_length_at_most_${maximum}`);
  }
  return value;
}

function nullableNonEmptyString(raw: unknown, path: string): string | null {
  return raw === null ? null : nonEmptyString(raw, path);
}

function booleanValue(raw: unknown, path: string): boolean {
  if (typeof raw !== "boolean") {
    throw new StudyChatOperationDecodeError(path, "expected_boolean");
  }
  return raw;
}

function safeInteger(raw: unknown, path: string, minimum: number): number {
  if (!Number.isSafeInteger(raw) || (raw as number) < minimum) {
    throw new StudyChatOperationDecodeError(
      path,
      `expected_safe_integer_at_least_${minimum}`,
    );
  }
  return raw as number;
}

function nullableSafeInteger(
  raw: unknown,
  path: string,
  minimum: number,
): number | null {
  return raw === null ? null : safeInteger(raw, path, minimum);
}

function operationStatus(raw: unknown, path: string): StudyChatOperationStatus {
  if (
    typeof raw !== "string" ||
    !STUDY_CHAT_OPERATION_STATUSES.includes(raw as StudyChatOperationStatus)
  ) {
    throw new StudyChatOperationDecodeError(path, "expected_registered_status");
  }
  return raw as StudyChatOperationStatus;
}

function operationErrorCode(
  raw: unknown,
  path: string,
  status: StudyChatOperationStatus,
): string {
  const value = stringValue(raw, path);
  const failureTerminal = status === "not_committed" || status === "uncertain";
  if (failureTerminal !== Boolean(value.trim())) {
    throw new StudyChatOperationDecodeError(
      path,
      failureTerminal
        ? `expected_non_empty_error_for_${status}`
        : `expected_empty_error_for_${status}`,
    );
  }
  return value;
}

function timestamp(raw: unknown, path: string): string {
  const value = nonEmptyString(raw, path);
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(Z|([+-])(\d{2}):(\d{2}))$/.exec(value);
  if (!match) {
    throw new StudyChatOperationDecodeError(path, "expected_rfc3339_timestamp");
  }
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const hour = Number(match[4]);
  const minute = Number(match[5]);
  const second = Number(match[6]);
  const offsetHour = match[7] === "Z" ? 0 : Number(match[9]);
  const offsetMinute = match[7] === "Z" ? 0 : Number(match[10]);
  const daysInMonth = month >= 1 && month <= 12
    ? [31, isLeapYear(year) ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1]!
    : 0;
  if (
    day < 1 ||
    day > daysInMonth ||
    hour > 23 ||
    minute > 59 ||
    second > 59 ||
    offsetHour > 23 ||
    offsetMinute > 59 ||
    !Number.isFinite(Date.parse(value))
  ) {
    throw new StudyChatOperationDecodeError(path, "expected_rfc3339_timestamp");
  }
  return value;
}

function isLeapYear(year: number): boolean {
  return year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
}

function nullableTimestamp(raw: unknown, path: string): string | null {
  return raw === null ? null : timestamp(raw, path);
}

function assertTimestampOrder(
  earlier: string,
  later: string,
  path: string,
): void {
  if (Date.parse(later) < Date.parse(earlier)) {
    throw new StudyChatOperationDecodeError(path, "timestamp_before_prior_state");
  }
}

function assertNull(raw: unknown, path: string, reason: string): asserts raw is null {
  if (raw !== null) {
    throw new StudyChatOperationDecodeError(path, reason);
  }
}

function assertExpectedIdentity(
  actual: string,
  expected: string,
  path: string,
  reason: string,
): void {
  if (!expected.trim()) {
    throw new StudyChatOperationDecodeError(path, "expected_identity_required");
  }
  if (actual !== expected) {
    throw new StudyChatOperationDecodeError(path, reason);
  }
}

function validateCommittedResultBinding(
  result: Record<string, unknown>,
  path: string,
  evidence: StudyChatCommittedResultEvidence,
): void {
  const sessionPath = `${path}.session`;
  const session = record(required(result, "session", path), sessionPath);
  const resultSessionId = boundedNonEmptyString(
    required(session, "id", sessionPath),
    `${sessionPath}.id`,
    64,
  );
  if (resultSessionId !== evidence.sessionId) {
    throw new StudyChatOperationDecodeError(
      `${sessionPath}.id`,
      "committed_result_session_mismatch",
    );
  }
  const resultRevision = safeInteger(
    required(session, "revision", sessionPath),
    `${sessionPath}.revision`,
    0,
  );
  if (resultRevision !== evidence.committedSessionRevision) {
    throw new StudyChatOperationDecodeError(
      `${sessionPath}.revision`,
      "committed_result_revision_mismatch",
    );
  }
  const lastTurnSequence = safeInteger(
    required(session, "last_turn_sequence", sessionPath),
    `${sessionPath}.last_turn_sequence`,
    1,
  );
  if (lastTurnSequence !== evidence.committedTurnSequence) {
    throw new StudyChatOperationDecodeError(
      `${sessionPath}.last_turn_sequence`,
      "committed_result_turn_watermark_mismatch",
    );
  }
  const turnsPath = `${sessionPath}.turns`;
  const rawTurns = required(session, "turns", sessionPath);
  if (!Array.isArray(rawTurns)) {
    throw new StudyChatOperationDecodeError(turnsPath, "expected_array");
  }
  const matchingTurns = rawTurns.filter((rawTurn, index) => {
    const turn = record(rawTurn, `${turnsPath}[${index}]`);
    const turnId = boundedNonEmptyString(
      required(turn, "id", `${turnsPath}[${index}]`),
      `${turnsPath}[${index}].id`,
      64,
    );
    const turnSequence = safeInteger(
      required(turn, "sequence", `${turnsPath}[${index}]`),
      `${turnsPath}[${index}].sequence`,
      1,
    );
    return turnId === evidence.committedTurnId &&
      turnSequence === evidence.committedTurnSequence;
  });
  if (matchingTurns.length !== 1) {
    throw new StudyChatOperationDecodeError(
      turnsPath,
      "expected_exact_committed_turn_binding",
    );
  }
}
