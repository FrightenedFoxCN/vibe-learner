import assert from "node:assert/strict";
import test from "node:test";

import {
  consumeVersionedStream,
  decodeStreamEvent,
  decodeStreamReport,
  StreamDecodeError,
  StrictStreamStateMachine,
  type ExpectedStreamScope,
} from "../lib/stream-decode.ts";

const DOCUMENT_SCOPE: ExpectedStreamScope = {
  streamKind: "document_process",
  subject: { subjectType: "document", subjectId: "doc-1" },
};
const PLAN_SCOPE: ExpectedStreamScope = {
  streamKind: "learning_plan",
  subject: { subjectType: "document", subjectId: "doc-1" },
};
const GOAL_PLAN_SCOPE: ExpectedStreamScope = {
  streamKind: "learning_plan",
  subject: {
    subjectType: "learning_plan_request",
    subjectId: "plan-request-1",
  },
};

function digest(seed: number): string {
  return seed.toString(16).padStart(64, "0");
}

function eventFixture(input: {
  scope: ExpectedStreamScope;
  sequence: number;
  stage: string;
  operationId?: string;
  payloadDigest?: string;
  payload?: Record<string, unknown>;
}) {
  const operationId = input.operationId ?? "stream-1";
  const isCompleted = input.stage === "stream_completed";
  const isTerminal = isCompleted || input.stage === "stream_error" || input.stage === "stream_cancelled";
  const isDocument = input.scope.streamKind === "document_process";
  const documentId = input.scope.subject.subjectType === "document"
    ? input.scope.subject.subjectId
    : "";
  const resourceId = isDocument ? documentId : "plan-1";
  const payload = input.payload ?? (
    input.stage === "learning_plan_completed"
      ? {
          document_id: documentId,
          plan_id: resourceId,
          creation_mode: documentId ? "document" : "goal_only",
        }
      : isCompleted
      ? isDocument
        ? { document_id: documentId, status: "processed" }
        : {
            document_id: documentId,
            plan_id: resourceId,
            creation_mode: documentId ? "document" : "goal_only",
          }
      : { document_id: documentId }
  );
  return {
    event_schema_version: "stream-event-v1",
    operation_id: operationId,
    event_id: `${operationId}:event:${input.sequence}`,
    event_sequence: input.sequence,
    stream_kind: input.scope.streamKind,
    subject: {
      subject_type: input.scope.subject.subjectType,
      subject_id: input.scope.subject.subjectId,
    },
    stage: input.stage,
    payload_contract_version: isDocument
      ? "document-process-stream-payload-v1"
      : "learning-plan-stream-payload-v1",
    payload_digest: input.payloadDigest ?? digest(input.sequence),
    payload,
    terminal_evidence: isTerminal
      ? isCompleted
        ? {
            commit_status: "committed",
            domain_operation_id: isDocument
              ? "document-process-op-1"
              : "learning-plan-op-1",
            domain_operation_status: "committed",
            evidence_scope: "primary_output_only",
            resource_type: isDocument ? "document" : "learning_plan",
            resource_id: resourceId,
            commit_contract_version: isDocument
              ? "document-process-commit-v1"
              : "learning-plan-commit-v1",
            projection_contract_version: isDocument
              ? "document-record-v1"
              : "learning-plan-record-v1",
            projection_digest: digest(999),
          }
        : {
            commit_status: "not_committed",
            domain_operation_id: isDocument
              ? "document-process-op-1"
              : "learning-plan-op-1",
            domain_operation_status: input.stage === "stream_cancelled"
              ? "interrupted"
              : "not_committed",
            evidence_scope: "primary_output_only",
            resource_type: null,
            resource_id: null,
            commit_contract_version: null,
            projection_contract_version: null,
            projection_digest: null,
          }
      : null,
    committed_projection: isCompleted ? { id: resourceId } : null,
    created_at: `2026-08-25T00:00:${String(input.sequence).padStart(2, "0")}+00:00`,
  };
}

function documentLifecycle() {
  return [
    "document_processing_started",
    "parser_started",
    "margin_patterns_detected",
    "sections_built",
    "chunks_built",
    "study_units_built",
    "document_processing_completed",
    "stream_completed",
  ].map((stage, index) => eventFixture({ scope: DOCUMENT_SCOPE, sequence: index + 1, stage }));
}

function planLifecycle(scope = PLAN_SCOPE) {
  return [
    "learning_plan_started",
    "study_units_ready",
    "heuristic_plan_built",
    "model_plan_applied",
    "learning_plan_completed",
    "stream_completed",
  ].map((stage, index) => eventFixture({ scope, sequence: index + 1, stage }));
}

test("document state machine accepts only the committed terminal and ignores an exact duplicate", () => {
  const machine = new StrictStreamStateMachine(DOCUMENT_SCOPE);
  const events = documentLifecycle();

  assert.ok(machine.accept(events[0]));
  assert.equal(machine.accept(structuredClone(events[0])), null);
  for (const event of events.slice(1)) assert.ok(machine.accept(event));

  const terminal = machine.finish();
  assert.equal(terminal.stage, "stream_completed");
  assert.equal(terminal.terminalEvidence?.commitStatus, "committed");
  assert.equal(terminal.committedProjection?.id, "doc-1");
});

test("same event identity with a different supplied digest fails closed", () => {
  const machine = new StrictStreamStateMachine(DOCUMENT_SCOPE);
  const first = documentLifecycle()[0];
  machine.accept(first);
  const conflict = structuredClone(first);
  conflict.payload_digest = digest(777);

  assert.throws(
    () => machine.accept(conflict),
    (error: unknown) =>
      error instanceof StreamDecodeError && error.reason === "duplicate_event_digest_conflict",
  );
});

test("cross-operation, cross-subject, sequence gap, and unknown stage frames are rejected", () => {
  const first = documentLifecycle()[0];
  const crossOperation = eventFixture({
    scope: DOCUMENT_SCOPE,
    sequence: 2,
    stage: "parser_started",
    operationId: "stream-attacker",
  });
  const operationMachine = new StrictStreamStateMachine(DOCUMENT_SCOPE);
  operationMachine.accept(first);
  assert.throws(() => operationMachine.accept(crossOperation), /identity_mismatch/);

  const crossSubject = structuredClone(first);
  crossSubject.subject.subject_id = "doc-attacker";
  crossSubject.payload.document_id = "doc-attacker";
  assert.throws(
    () => decodeStreamEvent(crossSubject, DOCUMENT_SCOPE),
    /identity_mismatch/,
  );

  const gapMachine = new StrictStreamStateMachine(DOCUMENT_SCOPE);
  gapMachine.accept(first);
  assert.throws(
    () => gapMachine.accept(eventFixture({
      scope: DOCUMENT_SCOPE,
      sequence: 3,
      stage: "parser_started",
    })),
    /identity_mismatch/,
  );

  const unknown = structuredClone(first);
  unknown.stage = "atomic_commit";
  assert.throws(() => decodeStreamEvent(unknown, DOCUMENT_SCOPE), /unexpected_enum/);
});

test("illegal transitions and new frames after terminal are rejected while terminal replay is idempotent", () => {
  const illegalMachine = new StrictStreamStateMachine(DOCUMENT_SCOPE);
  illegalMachine.accept(documentLifecycle()[0]);
  assert.throws(
    () => illegalMachine.accept(eventFixture({
      scope: DOCUMENT_SCOPE,
      sequence: 2,
      stage: "sections_built",
    })),
    /illegal_transition/,
  );

  const machine = new StrictStreamStateMachine(DOCUMENT_SCOPE);
  const events = documentLifecycle();
  for (const event of events) machine.accept(event);
  assert.equal(machine.accept(structuredClone(events.at(-1))), null);
  assert.throws(
    () => machine.accept(eventFixture({
      scope: DOCUMENT_SCOPE,
      sequence: events.length + 1,
      stage: "stream_error",
    })),
    /event_after_terminal/,
  );
});

test("EOF without a terminal is a typed failure, including a final line without newline", async () => {
  const first = JSON.stringify(documentLifecycle()[0]);
  const body = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(new TextEncoder().encode(first));
      controller.close();
    },
  });
  const seen: string[] = [];

  await assert.rejects(
    consumeVersionedStream(
      body,
      new StrictStreamStateMachine(DOCUMENT_SCOPE),
      (event) => seen.push(event.stage),
    ),
    (error: unknown) =>
      error instanceof StreamDecodeError && error.reason === "eof_before_terminal",
  );
  assert.deepEqual(seen, ["document_processing_started"]);
});

test("planning state machines bind document and goal-only request subjects", () => {
  for (const scope of [PLAN_SCOPE, GOAL_PLAN_SCOPE]) {
    const machine = new StrictStreamStateMachine(scope);
    for (const event of planLifecycle(scope)) machine.accept(event);
    const terminal = machine.finish();
    assert.equal(terminal.stage, "stream_completed");
    assert.equal(terminal.committedProjection?.id, "plan-1");
  }
});

test("trimmed v1 reports remain decidable and legacy reports do not gain invented evidence", () => {
  const lifecycle = documentLifecycle();
  const trimmedEvents = lifecycle.slice(4);
  const report = decodeStreamReport(
    {
      report_schema_version: "stream-report-v1",
      operation_id: "stream-1",
      subject: { subject_type: "document", subject_id: "doc-1" },
      document_id: "doc-1",
      stream_kind: "document_process",
      status: "completed",
      last_event_sequence: lifecycle.length,
      created_at: "2026-08-25T00:00:00+00:00",
      updated_at: "2026-08-25T00:00:08+00:00",
      events: trimmedEvents,
    },
    { expectedDocumentId: "doc-1", expectedStreamKind: "document_process" },
  );
  assert.equal(report.lastEventSequence, 8);
  assert.deepEqual(report.events.map((event) => event.eventSequence), [5, 6, 7, 8]);

  const legacy = decodeStreamReport(
    {
      document_id: "doc-1",
      stream_kind: "document_process",
      status: "completed",
      created_at: "2026-08-01T00:00:00+00:00",
      updated_at: "2026-08-01T00:01:00+00:00",
      events: [
        {
          stage: "stream_completed",
          payload: { document_id: "doc-1" },
          created_at: "2026-08-01T00:01:00+00:00",
        },
      ],
    },
    { expectedDocumentId: "doc-1", expectedStreamKind: "document_process" },
  );
  assert.equal(legacy.reportSchemaVersion, null);
  assert.equal(legacy.operationId, null);
  assert.equal(legacy.events[0].payloadDigest, null);
});

test("unknown versions and false committed terminals do not downgrade or succeed", () => {
  const unknownVersion = documentLifecycle()[0];
  unknownVersion.event_schema_version = "stream-event-v2";
  assert.throws(() => decodeStreamEvent(unknownVersion, DOCUMENT_SCOPE), /unexpected_enum/);

  const terminal = documentLifecycle().at(-1);
  assert.ok(terminal);
  assert.ok(terminal.terminal_evidence);
  terminal.terminal_evidence.commit_status = "not_committed";
  terminal.terminal_evidence.resource_type = null;
  terminal.terminal_evidence.resource_id = null;
  terminal.terminal_evidence.commit_contract_version = null;
  terminal.terminal_evidence.projection_contract_version = null;
  terminal.terminal_evidence.projection_digest = null;
  terminal.committed_projection = null;
  assert.throws(
    () => decodeStreamEvent(terminal, DOCUMENT_SCOPE),
    /completed_stream_commit_evidence_required/,
  );
});
