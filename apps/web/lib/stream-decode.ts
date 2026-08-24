import type {
  StreamEvent,
  StreamKind,
  StreamReport,
  StreamSubject,
  StreamTerminalEvidence,
} from "@vibe-learner/shared";

import { StrictResponseDecoder } from "./strict-response-decode.ts";

const STREAM_EVENT_SCHEMA_VERSION = "stream-event-v1" as const;
const STREAM_REPORT_SCHEMA_VERSION = "stream-report-v1" as const;
const SHA256_PATTERN = /^[0-9a-f]{64}$/;

const DOCUMENT_STAGES = [
  "document_processing_started",
  "parser_started",
  "page_parsed",
  "margin_patterns_detected",
  "sections_built",
  "chunks_built",
  "study_units_built",
  "document_processing_completed",
  "stream_completed",
  "stream_error",
  "stream_cancelled",
] as const;
const PLAN_STAGES = [
  "learning_plan_started",
  "study_units_ready",
  "heuristic_plan_built",
  "model_round_started",
  "model_tool_call",
  "model_round_completed",
  "model_round_failed",
  "model_recovery_attempt",
  "model_fallback_started",
  "model_fallback_succeeded",
  "model_plan_applied",
  "learning_plan_completed",
  "stream_completed",
  "stream_error",
  "stream_cancelled",
] as const;
const TERMINAL_STAGES = ["stream_completed", "stream_error", "stream_cancelled"] as const;
const DOMAIN_OPERATION_STATUSES = [
  "not_admitted",
  "read_back_failed",
  "running",
  "committed",
  "failed",
  "interrupted",
  "not_committed",
  "uncertain",
] as const;

const DOCUMENT_TRANSITIONS: Readonly<Record<string, readonly string[]>> = {
  __start__: ["document_processing_started"],
  document_processing_started: ["parser_started"],
  parser_started: ["page_parsed", "margin_patterns_detected"],
  page_parsed: ["page_parsed", "margin_patterns_detected"],
  margin_patterns_detected: ["sections_built"],
  sections_built: ["chunks_built"],
  chunks_built: ["study_units_built"],
  study_units_built: ["document_processing_completed"],
  document_processing_completed: ["stream_completed"],
};

const PLAN_TRANSITIONS: Readonly<Record<string, readonly string[]>> = {
  __start__: ["learning_plan_started"],
  learning_plan_started: ["study_units_ready"],
  study_units_ready: ["heuristic_plan_built"],
  heuristic_plan_built: [
    "model_round_started",
    "model_fallback_started",
    "model_plan_applied",
  ],
  model_round_started: [
    "model_tool_call",
    "model_round_completed",
    "model_round_failed",
    "model_recovery_attempt",
    "model_fallback_started",
  ],
  model_tool_call: [
    "model_tool_call",
    "model_round_completed",
    "model_fallback_started",
  ],
  model_round_completed: [
    "model_round_started",
    "model_recovery_attempt",
    "model_fallback_started",
    "model_fallback_succeeded",
    "model_plan_applied",
  ],
  model_round_failed: [
    "model_recovery_attempt",
    "model_round_started",
    "model_fallback_started",
  ],
  model_recovery_attempt: [
    "model_recovery_attempt",
    "model_round_started",
    "model_fallback_started",
  ],
  model_fallback_started: ["model_round_started", "model_fallback_succeeded"],
  model_fallback_succeeded: ["model_plan_applied"],
  model_plan_applied: ["learning_plan_completed"],
  learning_plan_completed: ["stream_completed"],
};

export class StreamDecodeError extends Error {
  readonly code = "stream_response_decode_error";
  readonly path: string;
  readonly reason: string;

  constructor(path: string, reason: string) {
    super(`${reason} at ${path}`);
    this.name = "StreamDecodeError";
    this.path = path;
    this.reason = reason;
  }
}

const decoder = new StrictResponseDecoder((path, reason) => {
  throw new StreamDecodeError(path, reason);
});

export interface ExpectedStreamScope {
  streamKind: StreamKind;
  subject: StreamSubject;
}

interface StreamMachineOptions extends ExpectedStreamScope {
  expectedOperationId?: string;
  resumeAfterSequence?: number;
  allowTruncatedStart?: boolean;
}

function exactKeys(
  value: Record<string, unknown>,
  allowed: readonly string[],
  path: string,
): void {
  const allowedSet = new Set(allowed);
  for (const key of Object.keys(value)) {
    if (!allowedSet.has(key)) {
      throw new StreamDecodeError(`${path}.${key}`, "unexpected_field");
    }
  }
}

function nullableField<T>(
  value: Record<string, unknown>,
  key: string,
  path: string,
  decode: (raw: unknown, fieldPath: string) => T,
): T | null {
  return decoder.nullable(
    decoder.field(value, key, path),
    `${path}.${key}`,
    decode,
  );
}

function digest(raw: unknown, path: string): string {
  const value = decoder.string(raw, path);
  if (!SHA256_PATTERN.test(value)) {
    throw new StreamDecodeError(path, "expected_sha256_digest");
  }
  return value;
}

function timestamp(raw: unknown, path: string, allowEmpty = false): string {
  const value = decoder.string(raw, path, allowEmpty);
  if (value || !allowEmpty) {
    const parsed = Date.parse(value);
    if (!Number.isFinite(parsed) || !/(?:Z|[+-]\d{2}:\d{2})$/.test(value)) {
      throw new StreamDecodeError(path, "expected_rfc3339_timestamp");
    }
  }
  return value;
}

function decodeSubject(raw: unknown, path: string): StreamSubject {
  const value = decoder.record(raw, path);
  exactKeys(value, ["subject_type", "subject_id"], path);
  return {
    subjectType: decoder.enumeration(
      decoder.field(value, "subject_type", path),
      ["document", "learning_plan_request"] as const,
      `${path}.subject_type`,
    ),
    subjectId: decoder.string(
      decoder.field(value, "subject_id", path),
      `${path}.subject_id`,
    ),
  };
}

function decodeTerminalEvidence(
  raw: unknown,
  path: string,
): StreamTerminalEvidence {
  const value = decoder.record(raw, path);
  exactKeys(
    value,
    [
      "commit_status",
      "domain_operation_id",
      "domain_operation_status",
      "evidence_scope",
      "resource_type",
      "resource_id",
      "commit_contract_version",
      "projection_contract_version",
      "projection_digest",
    ],
    path,
  );
  const evidence: StreamTerminalEvidence = {
    commitStatus: decoder.enumeration(
      decoder.field(value, "commit_status", path),
      ["committed", "not_committed", "uncertain"] as const,
      `${path}.commit_status`,
    ),
    domainOperationId: decoder.string(
      decoder.field(value, "domain_operation_id", path),
      `${path}.domain_operation_id`,
      true,
    ),
    domainOperationStatus: decoder.enumeration(
      decoder.field(value, "domain_operation_status", path),
      DOMAIN_OPERATION_STATUSES,
      `${path}.domain_operation_status`,
    ),
    evidenceScope: decoder.enumeration(
      decoder.field(value, "evidence_scope", path),
      ["primary_output_only"] as const,
      `${path}.evidence_scope`,
    ),
    resourceType: nullableField(value, "resource_type", path, (item, itemPath) =>
      decoder.enumeration(item, ["document", "learning_plan"] as const, itemPath)
    ),
    resourceId: nullableField(value, "resource_id", path, (item, itemPath) =>
      decoder.string(item, itemPath)
    ),
    commitContractVersion: nullableField(
      value,
      "commit_contract_version",
      path,
      (item, itemPath) => decoder.string(item, itemPath),
    ),
    projectionContractVersion: nullableField(
      value,
      "projection_contract_version",
      path,
      (item, itemPath) => decoder.string(item, itemPath),
    ),
    projectionDigest: nullableField(value, "projection_digest", path, digest),
  };

  const projectionFields = [
    evidence.resourceType,
    evidence.resourceId,
    evidence.commitContractVersion,
    evidence.projectionContractVersion,
    evidence.projectionDigest,
  ];
  if (evidence.commitStatus === "committed") {
    if (
      !evidence.domainOperationId ||
      evidence.domainOperationStatus !== "committed" ||
      projectionFields.some((item) => item === null)
    ) {
      throw new StreamDecodeError(path, "committed_terminal_evidence_incomplete");
    }
  } else if (projectionFields.some((item) => item !== null)) {
    throw new StreamDecodeError(path, "uncommitted_terminal_has_projection_evidence");
  }
  if (
    evidence.domainOperationStatus === "not_admitted" &&
    evidence.domainOperationId !== ""
  ) {
    throw new StreamDecodeError(
      `${path}.domain_operation_id`,
      "not_admitted_operation_identity_mismatch",
    );
  }
  if (
    evidence.domainOperationStatus !== "not_admitted" &&
    !evidence.domainOperationId
  ) {
    throw new StreamDecodeError(
      `${path}.domain_operation_id`,
      "domain_operation_identity_required",
    );
  }
  return evidence;
}

function validatePayloadSubject(
  payload: Record<string, unknown>,
  scope: ExpectedStreamScope,
  path: string,
): void {
  if (!Object.prototype.hasOwnProperty.call(payload, "document_id")) {
    return;
  }
  const documentId = decoder.string(payload.document_id, `${path}.document_id`, true);
  const expectedDocumentId =
    scope.subject.subjectType === "document" ? scope.subject.subjectId : "";
  decoder.equal(documentId, expectedDocumentId, `${path}.document_id`);
  if (Object.prototype.hasOwnProperty.call(payload, "creation_mode")) {
    const creationMode = decoder.enumeration(
      payload.creation_mode,
      ["document", "goal_only"] as const,
      `${path}.creation_mode`,
    );
    decoder.equal(
      creationMode,
      expectedDocumentId ? "document" : "goal_only",
      `${path}.creation_mode`,
    );
  }
}

export function decodeStreamEvent(
  raw: unknown,
  scope: ExpectedStreamScope,
  path = "stream.event",
): StreamEvent {
  const value = decoder.record(raw, path);
  exactKeys(
    value,
    [
      "event_schema_version",
      "operation_id",
      "event_id",
      "event_sequence",
      "stream_kind",
      "subject",
      "stage",
      "payload_contract_version",
      "payload_digest",
      "payload",
      "terminal_evidence",
      "committed_projection",
      "created_at",
    ],
    path,
  );
  const eventSchemaVersion = decoder.enumeration(
    decoder.field(value, "event_schema_version", path),
    [STREAM_EVENT_SCHEMA_VERSION] as const,
    `${path}.event_schema_version`,
  );
  const operationId = decoder.string(
    decoder.field(value, "operation_id", path),
    `${path}.operation_id`,
  );
  const eventSequence = decoder.integer(
    decoder.field(value, "event_sequence", path),
    `${path}.event_sequence`,
    1,
  );
  const eventId = decoder.string(
    decoder.field(value, "event_id", path),
    `${path}.event_id`,
  );
  decoder.equal(
    eventId,
    `${operationId}:event:${eventSequence}`,
    `${path}.event_id`,
  );
  const streamKind = decoder.enumeration(
    decoder.field(value, "stream_kind", path),
    ["document_process", "learning_plan"] as const,
    `${path}.stream_kind`,
  );
  decoder.equal(streamKind, scope.streamKind, `${path}.stream_kind`);
  const subject = decodeSubject(decoder.field(value, "subject", path), `${path}.subject`);
  decoder.equal(
    subject.subjectType,
    scope.subject.subjectType,
    `${path}.subject.subject_type`,
  );
  decoder.equal(subject.subjectId, scope.subject.subjectId, `${path}.subject.subject_id`);
  const stages = streamKind === "document_process" ? DOCUMENT_STAGES : PLAN_STAGES;
  const stage = decoder.enumeration(
    decoder.field(value, "stage", path),
    stages,
    `${path}.stage`,
  );
  const expectedPayloadContract =
    streamKind === "document_process"
      ? "document-process-stream-payload-v1"
      : "learning-plan-stream-payload-v1";
  const payloadContractVersion = decoder.string(
    decoder.field(value, "payload_contract_version", path),
    `${path}.payload_contract_version`,
  );
  decoder.equal(
    payloadContractVersion,
    expectedPayloadContract,
    `${path}.payload_contract_version`,
  );
  const payloadDigest = digest(
    decoder.field(value, "payload_digest", path),
    `${path}.payload_digest`,
  );
  const payload = decoder.record(decoder.field(value, "payload", path), `${path}.payload`);
  validatePayloadSubject(payload, scope, `${path}.payload`);
  const terminalEvidence = nullableField(
    value,
    "terminal_evidence",
    path,
    decodeTerminalEvidence,
  );
  const committedProjection = nullableField(
    value,
    "committed_projection",
    path,
    (item, itemPath) => decoder.record(item, itemPath),
  );
  const isTerminal = TERMINAL_STAGES.includes(stage as (typeof TERMINAL_STAGES)[number]);
  if (isTerminal !== (terminalEvidence !== null)) {
    throw new StreamDecodeError(`${path}.terminal_evidence`, "terminal_evidence_mismatch");
  }
  if (stage === "stream_completed") {
    if (
      terminalEvidence?.commitStatus !== "committed" ||
      committedProjection === null
    ) {
      throw new StreamDecodeError(path, "completed_stream_commit_evidence_required");
    }
    const expectedResourceType =
      streamKind === "document_process" ? "document" : "learning_plan";
    const expectedProjectionContract =
      streamKind === "document_process" ? "document-record-v1" : "learning-plan-record-v1";
    const expectedCommitContract =
      streamKind === "document_process"
        ? "document-process-commit-v1"
        : "learning-plan-commit-v1";
    decoder.equal(
      terminalEvidence.resourceType ?? "",
      expectedResourceType,
      `${path}.terminal_evidence.resource_type`,
    );
    decoder.equal(
      terminalEvidence.projectionContractVersion ?? "",
      expectedProjectionContract,
      `${path}.terminal_evidence.projection_contract_version`,
    );
    decoder.equal(
      terminalEvidence.commitContractVersion ?? "",
      expectedCommitContract,
      `${path}.terminal_evidence.commit_contract_version`,
    );
    const projectionId = decoder.string(
      decoder.field(committedProjection, "id", `${path}.committed_projection`),
      `${path}.committed_projection.id`,
    );
    decoder.equal(
      projectionId,
      terminalEvidence.resourceId ?? "",
      `${path}.committed_projection.id`,
    );
    if (streamKind === "document_process") {
      decoder.equal(projectionId, subject.subjectId, `${path}.committed_projection.id`);
      decoder.equal(
        decoder.string(payload.status, `${path}.payload.status`),
        "processed",
        `${path}.payload.status`,
      );
    } else {
      decoder.equal(
        decoder.string(payload.plan_id, `${path}.payload.plan_id`),
        projectionId,
        `${path}.payload.plan_id`,
      );
      decoder.equal(
        decoder.string(payload.creation_mode, `${path}.payload.creation_mode`),
        subject.subjectType === "document" ? "document" : "goal_only",
        `${path}.payload.creation_mode`,
      );
    }
  } else if (isTerminal) {
    if (
      terminalEvidence?.commitStatus === "committed" ||
      committedProjection !== null
    ) {
      throw new StreamDecodeError(path, "failed_stream_must_not_claim_commit");
    }
  } else if (terminalEvidence !== null || committedProjection !== null) {
    throw new StreamDecodeError(path, "nonterminal_stream_has_terminal_projection");
  }

  return {
    eventSchemaVersion,
    operationId,
    eventId,
    eventSequence,
    streamKind,
    subject,
    stage,
    payloadContractVersion,
    payloadDigest,
    payload,
    terminalEvidence,
    committedProjection,
    createdAt: timestamp(decoder.field(value, "created_at", path), `${path}.created_at`),
  };
}

function replaySignature(event: StreamEvent): string {
  return [
    event.operationId,
    event.eventSequence,
    event.stage,
    event.payloadContractVersion,
    event.payloadDigest,
    event.terminalEvidence?.commitStatus ?? "",
    event.terminalEvidence?.projectionDigest ?? "",
    event.terminalEvidence?.resourceId ?? "",
  ].join("|");
}

function validateTransition(
  streamKind: StreamKind,
  previousStage: string | null,
  nextStage: string,
  allowTruncatedStart: boolean,
): void {
  if (previousStage === null && allowTruncatedStart) {
    return;
  }
  if (nextStage === "stream_error" || nextStage === "stream_cancelled") {
    return;
  }
  const transitions =
    streamKind === "document_process" ? DOCUMENT_TRANSITIONS : PLAN_TRANSITIONS;
  const allowed = transitions[previousStage ?? "__start__"] ?? [];
  if (!allowed.includes(nextStage)) {
    throw new StreamDecodeError(
      "stream.transition",
      `illegal_transition_${previousStage ?? "start"}_to_${nextStage}`,
    );
  }
}

export class StrictStreamStateMachine {
  private readonly options: StreamMachineOptions;
  private readonly seenEvents = new Map<string, string>();
  private operationId: string | null;
  private nextSequence: number;
  private previousStage: string | null = null;
  private terminalEvent: StreamEvent | null = null;
  private acceptedCount = 0;
  private announcedResourceId: string | null = null;

  constructor(options: StreamMachineOptions) {
    this.options = options;
    this.operationId = options.expectedOperationId ?? null;
    this.nextSequence = (options.resumeAfterSequence ?? 0) + 1;
  }

  accept(raw: unknown, path = "stream.event"): StreamEvent | null {
    const event = decodeStreamEvent(raw, this.options, path);
    const eventId = event.eventId as string;
    const signature = replaySignature(event);
    const seenSignature = this.seenEvents.get(eventId);
    if (seenSignature !== undefined) {
      if (seenSignature !== signature) {
        throw new StreamDecodeError(`${path}.event_id`, "duplicate_event_digest_conflict");
      }
      return null;
    }
    if (this.terminalEvent !== null) {
      throw new StreamDecodeError(path, "event_after_terminal");
    }
    const expectedOperationId = this.operationId ?? (event.operationId as string);
    this.operationId = expectedOperationId;
    decoder.equal(
      event.operationId as string,
      expectedOperationId,
      `${path}.operation_id`,
    );
    decoder.equal(
      event.eventSequence as number,
      this.nextSequence,
      `${path}.event_sequence`,
    );
    validateTransition(
      this.options.streamKind,
      this.previousStage,
      event.stage,
      Boolean(this.options.allowTruncatedStart && this.acceptedCount === 0),
    );
    if (
      this.options.streamKind === "learning_plan" &&
      event.stage === "learning_plan_completed"
    ) {
      this.announcedResourceId = decoder.string(
        event.payload.plan_id,
        `${path}.payload.plan_id`,
      );
    }
    if (
      this.options.streamKind === "learning_plan" &&
      event.stage === "stream_completed" &&
      this.announcedResourceId !== null
    ) {
      decoder.equal(
        event.terminalEvidence?.resourceId ?? "",
        this.announcedResourceId,
        `${path}.terminal_evidence.resource_id`,
      );
    }
    this.seenEvents.set(eventId, signature);
    this.nextSequence += 1;
    this.previousStage = event.stage;
    this.acceptedCount += 1;
    if (TERMINAL_STAGES.includes(event.stage as (typeof TERMINAL_STAGES)[number])) {
      this.terminalEvent = event;
    }
    return event;
  }

  finish(path = "stream"): StreamEvent {
    if (this.terminalEvent === null) {
      throw new StreamDecodeError(path, "eof_before_terminal");
    }
    return this.terminalEvent;
  }

  currentTerminal(): StreamEvent | null {
    return this.terminalEvent;
  }
}

export async function consumeVersionedStream(
  body: ReadableStream<Uint8Array>,
  machine: StrictStreamStateMachine,
  onEvent: (event: StreamEvent) => void,
): Promise<StreamEvent> {
  const reader = body.getReader();
  const textDecoder = new TextDecoder();
  let buffer = "";
  let lineNumber = 0;

  const consumeLine = (line: string) => {
    const trimmed = line.trim();
    if (!trimmed) return;
    lineNumber += 1;
    let raw: unknown;
    try {
      raw = JSON.parse(trimmed);
    } catch {
      throw new StreamDecodeError(`stream.line[${lineNumber}]`, "invalid_json");
    }
    const event = machine.accept(raw, `stream.line[${lineNumber}]`);
    if (event !== null) onEvent(event);
  };

  while (true) {
    const { done, value } = await reader.read();
    buffer += textDecoder.decode(value ?? new Uint8Array(), { stream: !done });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";
    for (const line of lines) consumeLine(line);
    if (done) {
      consumeLine(buffer);
      break;
    }
  }
  return machine.finish();
}

function decodeLegacyEvent(raw: unknown, path: string): StreamEvent {
  const value = decoder.record(raw, path);
  exactKeys(
    value,
    [
      "event_schema_version",
      "operation_id",
      "event_id",
      "event_sequence",
      "stream_kind",
      "subject",
      "stage",
      "payload_contract_version",
      "payload_digest",
      "payload",
      "terminal_evidence",
      "committed_projection",
      "created_at",
    ],
    path,
  );
  for (const field of [
    "event_schema_version",
    "operation_id",
    "event_id",
    "event_sequence",
    "stream_kind",
    "subject",
    "payload_contract_version",
    "payload_digest",
    "terminal_evidence",
    "committed_projection",
  ]) {
    if (Object.prototype.hasOwnProperty.call(value, field) && value[field] !== null) {
      throw new StreamDecodeError(`${path}.${field}`, "legacy_event_has_v1_evidence");
    }
  }
  return {
    eventSchemaVersion: null,
    operationId: null,
    eventId: null,
    eventSequence: null,
    streamKind: null,
    subject: null,
    stage: decoder.string(decoder.field(value, "stage", path), `${path}.stage`),
    payloadContractVersion: null,
    payloadDigest: null,
    payload: decoder.record(decoder.field(value, "payload", path), `${path}.payload`),
    terminalEvidence: null,
    committedProjection: null,
    createdAt: timestamp(decoder.field(value, "created_at", path), `${path}.created_at`),
  };
}

export function decodeStreamReport(
  raw: unknown,
  options: { expectedDocumentId: string; expectedStreamKind: StreamKind },
): StreamReport {
  const path = "stream_report";
  const value = decoder.record(raw, path);
  exactKeys(
    value,
    [
      "report_schema_version",
      "operation_id",
      "subject",
      "document_id",
      "stream_kind",
      "status",
      "last_event_sequence",
      "created_at",
      "updated_at",
      "events",
    ],
    path,
  );
  const reportVersion = Object.prototype.hasOwnProperty.call(value, "report_schema_version")
    ? value.report_schema_version
    : null;
  const documentId = decoder.string(
    decoder.field(value, "document_id", path),
    `${path}.document_id`,
  );
  decoder.equal(documentId, options.expectedDocumentId, `${path}.document_id`);
  const streamKind = decoder.enumeration(
    decoder.field(value, "stream_kind", path),
    ["document_process", "learning_plan"] as const,
    `${path}.stream_kind`,
  );
  decoder.equal(streamKind, options.expectedStreamKind, `${path}.stream_kind`);
  const status = decoder.enumeration(
    decoder.field(value, "status", path),
    ["idle", "running", "completed", "error", "cancelled"] as const,
    `${path}.status`,
  );
  const rawEvents = decoder.field(value, "events", path);

  if (reportVersion === null) {
    for (const field of ["operation_id", "subject", "last_event_sequence"]) {
      if (Object.prototype.hasOwnProperty.call(value, field) && value[field] !== null) {
        throw new StreamDecodeError(`${path}.${field}`, "legacy_report_has_v1_evidence");
      }
    }
    return {
      reportSchemaVersion: null,
      operationId: null,
      subject: null,
      documentId,
      streamKind,
      status,
      lastEventSequence: null,
      createdAt: timestamp(
        decoder.field(value, "created_at", path),
        `${path}.created_at`,
        status === "idle",
      ),
      updatedAt: timestamp(
        decoder.field(value, "updated_at", path),
        `${path}.updated_at`,
        status === "idle",
      ),
      events: decoder.array(rawEvents, `${path}.events`, decodeLegacyEvent),
    };
  }

  decoder.equal(
    decoder.string(reportVersion, `${path}.report_schema_version`),
    STREAM_REPORT_SCHEMA_VERSION,
    `${path}.report_schema_version`,
  );
  if (status === "idle") {
    throw new StreamDecodeError(`${path}.status`, "versioned_report_cannot_be_idle");
  }
  const operationId = decoder.string(
    decoder.field(value, "operation_id", path),
    `${path}.operation_id`,
  );
  const subject = decodeSubject(decoder.field(value, "subject", path), `${path}.subject`);
  const expectedSubject: StreamSubject = {
    subjectType: "document",
    subjectId: options.expectedDocumentId,
  };
  decoder.equal(subject.subjectType, expectedSubject.subjectType, `${path}.subject.subject_type`);
  decoder.equal(subject.subjectId, expectedSubject.subjectId, `${path}.subject.subject_id`);
  const lastEventSequence = decoder.integer(
    decoder.field(value, "last_event_sequence", path),
    `${path}.last_event_sequence`,
  );
  const eventPayloads = decoder.array(rawEvents, `${path}.events`, (item) => item);
  const firstSequence = lastEventSequence - eventPayloads.length + 1;
  if (firstSequence < 1 && eventPayloads.length > 0) {
    throw new StreamDecodeError(`${path}.events`, "invalid_trimmed_event_window");
  }
  if (eventPayloads.length === 0 && lastEventSequence !== 0) {
    throw new StreamDecodeError(`${path}.last_event_sequence`, "empty_report_sequence_mismatch");
  }
  const machine = new StrictStreamStateMachine({
    streamKind,
    subject,
    expectedOperationId: operationId,
    resumeAfterSequence: Math.max(firstSequence - 1, 0),
    allowTruncatedStart: firstSequence > 1,
  });
  const events: StreamEvent[] = [];
  for (const [index, eventPayload] of eventPayloads.entries()) {
    const event = machine.accept(eventPayload, `${path}.events[${index}]`);
    if (event === null) {
      throw new StreamDecodeError(`${path}.events[${index}]`, "duplicate_event_in_report");
    }
    events.push(event);
  }
  const expectedStatus =
    machine.currentTerminal()?.stage === "stream_completed"
      ? "completed"
      : machine.currentTerminal()?.stage === "stream_error"
        ? "error"
        : machine.currentTerminal()?.stage === "stream_cancelled"
          ? "cancelled"
          : "running";
  decoder.equal(status, expectedStatus, `${path}.status`);
  if (status !== "running") machine.finish(path);

  return {
    reportSchemaVersion: STREAM_REPORT_SCHEMA_VERSION,
    operationId,
    subject,
    documentId,
    streamKind,
    status,
    lastEventSequence,
    createdAt: timestamp(decoder.field(value, "created_at", path), `${path}.created_at`),
    updatedAt: timestamp(decoder.field(value, "updated_at", path), `${path}.updated_at`),
    events,
  };
}
