import assert from "node:assert/strict";
import { test } from "node:test";
import {
  decodeStudyChatOperationReceipt,
  isStudyChatOperationDecodeError,
  StudyChatOperationDecodeError,
  type StudyChatCommittedResultEvidence,
} from "../lib/study-chat-operation-decode.ts";

const created = "2024-02-29T00:00:00+02:00";
const updated = "2024-02-28T22:00:01Z";
const completed = "2024-02-28T22:00:02.123456Z";
const options = {
  path: "receipt",
  expectedSessionId: "session",
  expectedClientRequestId: "request",
  decodeResult: (
    _raw: Record<string, unknown>,
    _path: string,
    evidence: StudyChatCommittedResultEvidence,
  ) => evidence,
};
const running = {
  operation_id: "operation",
  session_id: "session",
  client_request_id: "request",
  status: "running",
  safe_to_retry: false,
  admitted_session_revision: 0,
  committed_session_revision: null,
  committed_turn_id: null,
  committed_turn_sequence: null,
  result: null,
  completed_at: null,
  created_at: created,
  updated_at: updated,
  error_code: "",
};
const session = {
  id: "session",
  revision: 1,
  last_turn_sequence: 1,
  turns: [{ id: "turn", sequence: 1 }],
};
const committed = {
  ...running,
  status: "committed",
  committed_session_revision: 1,
  committed_turn_id: "turn",
  committed_turn_sequence: 1,
  result: { session },
  completed_at: completed,
};

function rejects(raw: unknown, path: string, reason: string) {
  assert.throws(
    () => decodeStudyChatOperationReceipt(raw, options),
    (error) => {
      assert.ok(error instanceof StudyChatOperationDecodeError);
      assert.ok(isStudyChatOperationDecodeError(error));
      assert.equal(error.code, "study_chat_operation_response_decode_error");
      assert.equal(error.path, path);
      assert.equal(error.message, reason + " at " + path);
      return true;
    },
  );
}

test("committed receipt passes bound evidence to the nested decoder", () => {
  const receipt = decodeStudyChatOperationReceipt(committed, {
    ...options,
    decodeResult(raw, path, evidence) {
      assert.equal(raw, committed.result);
      assert.equal(path, "receipt.result");
      return evidence;
    },
  });
  assert.deepEqual(receipt.result, {
    operationId: "operation",
    sessionId: "session",
    clientRequestId: "request",
    admittedSessionRevision: 0,
    committedSessionRevision: 1,
    committedTurnId: "turn",
    committedTurnSequence: 1,
  });
  assert.equal(receipt.createdAt, created);
  assert.equal(receipt.completedAt, completed);
});

test("uncommitted receipts keep exact retry policy and do not decode results", () => {
  for (const status of ["admitted", "running", "not_committed", "uncertain"] as const) {
    const terminal = status === "not_committed" || status === "uncertain";
    const safeToRetry = status === "not_committed";
    const receipt = decodeStudyChatOperationReceipt(
      {
        ...running,
        status,
        safe_to_retry: safeToRetry,
        completed_at: terminal ? completed : null,
        error_code: terminal ? " error " : " ",
        extra: true,
      },
      { ...options, decodeResult: () => assert.fail("unexpected result decode") },
    );
    assert.equal(receipt.status, status);
    assert.equal(receipt.safeToRetry, safeToRetry);
    assert.equal(receipt.result, null);
    assert.equal(receipt.errorCode, terminal ? " error " : " ");
  }
});

test("receipt shape errors preserve exact path, code and reason", () => {
  const { completed_at: _completed, ...missing } = running;
  rejects([], "receipt", "expected_object");
  rejects(missing, "receipt.completed_at", "missing_required_field");
  rejects(
    { ...running, completed_at: undefined },
    "receipt.completed_at",
    "expected_string",
  );
  rejects(
    { ...running, status: "unknown" },
    "receipt.status",
    "expected_registered_status",
  );
  rejects(
    { ...running, status: Object.create(null) },
    "receipt.status",
    "expected_registered_status",
  );
  rejects(
    { ...running, safe_to_retry: 0 },
    "receipt.safe_to_retry",
    "expected_boolean",
  );
  rejects(
    { ...running, admitted_session_revision: Number.MAX_SAFE_INTEGER + 1 },
    "receipt.admitted_session_revision",
    "expected_safe_integer_at_least_0",
  );
  rejects(
    { ...committed, committed_turn_sequence: 0 },
    "receipt.committed_turn_sequence",
    "expected_safe_integer_at_least_1",
  );
  rejects(
    { ...running, operation_id: " " },
    "receipt.operation_id",
    "expected_non_empty_string",
  );
  rejects(
    { ...running, client_request_id: "a".repeat(81) },
    "receipt.client_request_id",
    "expected_length_at_most_80",
  );
});

test("receipt requires timestamp, status and committed projection invariants", () => {
  rejects(
    { ...running, created_at: "2023-02-29T00:00:00Z" },
    "receipt.created_at",
    "expected_rfc3339_timestamp",
  );
  rejects(
    { ...running, updated_at: "2024-02-28T21:00:00Z" },
    "receipt.updated_at",
    "timestamp_before_prior_state",
  );
  rejects(
    { ...running, session_id: "different" },
    "receipt.session_id",
    "session_identity_mismatch",
  );
  rejects(
    { ...running, safe_to_retry: true },
    "receipt.safe_to_retry",
    "expected_false_for_running",
  );
  rejects(
    { ...running, completed_at: completed },
    "receipt.completed_at",
    "expected_null_before_terminal",
  );
  rejects({ ...running, result: {} }, "receipt.result", "expected_null_for_running");
  rejects(
    { ...committed, result: { session: { ...session, revision: 2 } } },
    "receipt.result.session.revision",
    "committed_result_revision_mismatch",
  );
  rejects(
    { ...committed, result: { session: { ...session, turns: {} } } },
    "receipt.result.session.turns",
    "expected_array",
  );
  rejects(
    {
      ...committed,
      result: { session: { ...session, turns: [...session.turns, ...session.turns] } },
    },
    "receipt.result.session.turns",
    "expected_exact_committed_turn_binding",
  );
  rejects(
    { ...committed, result: { session: { ...session, turns: [{ id: "turn" }] } } },
    "receipt.result.session.turns[0].sequence",
    "missing_required_field",
  );
});

test("nested decoder keeps typed failure identity and wraps untyped failures", () => {
  const sessionError = Object.assign(new Error("session failed"), {
    code: "study_session_response_decode_error",
  });
  const operationError = new StudyChatOperationDecodeError("nested", "failure");
  for (const error of [sessionError, operationError]) {
    assert.throws(
      () =>
        decodeStudyChatOperationReceipt(committed, {
          ...options,
          decodeResult() {
            throw error;
          },
        }),
      (actual) => actual === error,
    );
  }
  assert.throws(
    () =>
      decodeStudyChatOperationReceipt(committed, {
        ...options,
        decodeResult() {
          throw new Error("unexpected");
        },
      }),
    {
      name: "StudyChatOperationDecodeError",
      message: "committed_result_decode_failed at receipt.result",
    },
  );
});
