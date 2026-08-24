import assert from "node:assert/strict";
import test from "node:test";

import {
  decodeStudyChatOperationReceipt,
  isStudyChatOperationDecodeError,
  STUDY_CHAT_OPERATION_STATUSES,
  StudyChatOperationDecodeError,
} from "../lib/study-chat-operation-decode.ts";
import { StudySessionDecodeError } from "../lib/study-session-decode.ts";

const terminalTimestamp = "2026-08-12T13:00:02+00:00";

function operationWire(
  status: (typeof STUDY_CHAT_OPERATION_STATUSES)[number] = "admitted",
): Record<string, unknown> {
  const committed = status === "committed";
  const terminal = committed || status === "not_committed" || status === "uncertain";
  return {
    operation_id: "study-chat-op-1",
    session_id: "session-1",
    client_request_id: "request-1",
    status,
    safe_to_retry: status === "not_committed",
    admitted_session_revision: 7,
    committed_session_revision: committed ? 8 : null,
    committed_turn_id: committed ? "turn-4" : null,
    committed_turn_sequence: committed ? 4 : null,
    result: committed ? {
      reply: "answer",
      session: {
        id: "session-1",
        revision: 8,
        last_turn_sequence: 4,
        turns: [
          { id: "turn-1", sequence: 1 },
          { id: "turn-2", sequence: 2 },
          { id: "turn-3", sequence: 3 },
          { id: "turn-4", sequence: 4 },
        ],
      },
    } : null,
    error_code: status === "uncertain"
      ? "study_chat_execution_uncertain"
      : status === "not_committed"
        ? "study_chat_not_committed"
        : "",
    created_at: "2026-08-12T13:00:00+00:00",
    updated_at: terminal ? terminalTimestamp : "2026-08-12T13:00:01+00:00",
    completed_at: terminal ? terminalTimestamp : null,
  };
}

function decode(
  raw: unknown,
  options: {
    expectedSessionId?: string;
    expectedClientRequestId?: string;
    decodeResult?: (
      raw: Record<string, unknown>,
      path: string,
      evidence: Parameters<
        NonNullable<Parameters<typeof decodeStudyChatOperationReceipt>[1]>["decodeResult"]
      >[2],
    ) => unknown;
  } = {},
) {
  return decodeStudyChatOperationReceipt(raw, {
    expectedSessionId: options.expectedSessionId ?? "session-1",
    expectedClientRequestId: options.expectedClientRequestId ?? "request-1",
    decodeResult: options.decodeResult ?? ((result) => result),
  });
}

test("Study Chat operation decoder accepts every frozen status", () => {
  for (const status of STUDY_CHAT_OPERATION_STATUSES) {
    const decoded = decode(operationWire(status));
    assert.equal(decoded.status, status);
    assert.equal(decoded.operationId, "study-chat-op-1");
    assert.equal(decoded.sessionId, "session-1");
    assert.equal(decoded.clientRequestId, "request-1");
    assert.equal(decoded.safeToRetry, status === "not_committed");
    assert.equal(decoded.result === null, status !== "committed");
  }
});

test("Study Chat operation decoder requires every public field", () => {
  for (const field of Object.keys(operationWire("committed"))) {
    const payload = operationWire("committed");
    delete payload[field];
    assert.throws(
      () => decode(payload),
      (error: unknown) =>
        error instanceof StudyChatOperationDecodeError &&
        error.path === `study_chat_operation.${field}`,
      `expected missing ${field} to fail closed`,
    );
  }
});

test("Study Chat operation decoder rejects unregistered or coerced statuses", () => {
  for (const status of ["completed", "failed", "pending", "", null, 1]) {
    assert.throws(
      () => decode({ ...operationWire(), status }),
      (error: unknown) =>
        error instanceof StudyChatOperationDecodeError &&
        error.path === "study_chat_operation.status",
    );
  }
});

test("Study Chat operation decoder rejects empty or non-string identities", () => {
  for (const field of ["operation_id", "session_id", "client_request_id"] as const) {
    for (const value of ["", "   ", null, 17, true]) {
      assert.throws(
        () => decode({ ...operationWire(), [field]: value }),
        (error: unknown) =>
          error instanceof StudyChatOperationDecodeError &&
          error.path === `study_chat_operation.${field}`,
      );
    }
  }
});

test("Study Chat operation decoder rejects unsafe revision and sequence evidence", () => {
  for (const admittedRevision of [-1, 1.5, Number.NaN, Number.MAX_SAFE_INTEGER + 1, "7", true]) {
    assert.throws(
      () => decode({
        ...operationWire("committed"),
        admitted_session_revision: admittedRevision,
      }),
      StudyChatOperationDecodeError,
    );
  }
  for (const committedRevision of [-1, 1.5, Number.NaN, "8", true]) {
    assert.throws(
      () => decode({
        ...operationWire("committed"),
        committed_session_revision: committedRevision,
      }),
      StudyChatOperationDecodeError,
    );
  }
  for (const turnSequence of [0, -1, 1.5, Number.NaN, "4", true]) {
    assert.throws(
      () => decode({
        ...operationWire("committed"),
        committed_turn_sequence: turnSequence,
      }),
      StudyChatOperationDecodeError,
    );
  }
  assert.throws(
    () => decode({
      ...operationWire("committed"),
      committed_session_revision: 6,
    }),
    (error: unknown) =>
      error instanceof StudyChatOperationDecodeError &&
      error.path === "study_chat_operation.committed_session_revision",
  );
});

test("committed requires complete result, Turn, revision, and terminal evidence", () => {
  const attacks: Array<[string, unknown]> = [
    ["committed_session_revision", null],
    ["committed_turn_id", null],
    ["committed_turn_id", ""],
    ["committed_turn_sequence", null],
    ["result", null],
    ["result", []],
    ["result", "answer"],
    ["completed_at", null],
  ];
  for (const [field, value] of attacks) {
    assert.throws(
      () => decode({
        ...operationWire("committed"),
        [field]: value,
      }),
      (error: unknown) =>
        error instanceof StudyChatOperationDecodeError &&
        error.path === `study_chat_operation.${field}`,
      `expected invalid committed ${field} to fail closed`,
    );
  }
});

test("non-committed statuses reject fabricated result or commit evidence", () => {
  for (const status of ["admitted", "running", "not_committed", "uncertain"] as const) {
    const attacks: Array<[string, unknown]> = [
      ["committed_session_revision", 8],
      ["committed_turn_id", "turn-4"],
      ["committed_turn_sequence", 4],
      ["result", { reply: "fabricated" }],
    ];
    for (const [field, value] of attacks) {
      assert.throws(
        () => decode({
          ...operationWire(status),
          [field]: value,
        }),
        StudyChatOperationDecodeError,
        `${status} must reject fabricated ${field}`,
      );
    }
  }
});

test("safe_to_retry is true only for not_committed and never for running or uncertain", () => {
  for (const status of STUDY_CHAT_OPERATION_STATUSES) {
    const expected = status === "not_committed";
    assert.throws(
      () => decode({
        ...operationWire(status),
        safe_to_retry: !expected,
      }),
      (error: unknown) =>
        error instanceof StudyChatOperationDecodeError &&
        error.path === "study_chat_operation.safe_to_retry",
    );
  }
  for (const status of ["running", "uncertain"] as const) {
    assert.equal(
      decode(operationWire(status)).safeToRetry,
      false,
    );
  }
});

test("terminal timestamp nullability follows the operation state", () => {
  for (const status of ["admitted", "running"] as const) {
    assert.throws(
      () => decode({
        ...operationWire(status),
        completed_at: terminalTimestamp,
      }),
      StudyChatOperationDecodeError,
    );
  }
  for (const status of ["committed", "not_committed", "uncertain"] as const) {
    assert.throws(
      () => decode({
        ...operationWire(status),
        completed_at: null,
      }),
      StudyChatOperationDecodeError,
    );
  }
});

test("operation timestamps reject impossible dates and reversed state time", () => {
  for (const [field, value] of [
    ["created_at", "2026-02-31T13:00:00Z"],
    ["updated_at", "2025-02-29T13:00:00Z"],
    ["completed_at", "2026-08-12T24:00:00Z"],
    ["completed_at", "2026-08-12T13:00:00+24:00"],
  ] as const) {
    assert.throws(
      () => decode({ ...operationWire("committed"), [field]: value }),
      (error: unknown) =>
        error instanceof StudyChatOperationDecodeError &&
        error.path === `study_chat_operation.${field}`,
    );
  }
  assert.throws(
    () => decode({
      ...operationWire("committed"),
      updated_at: "2026-08-12T12:59:59Z",
    }),
    StudyChatOperationDecodeError,
  );
  assert.throws(
    () => decode({
      ...operationWire("committed"),
      completed_at: "2026-08-12T12:59:59Z",
    }),
    StudyChatOperationDecodeError,
  );
});

test("nested committed result is delegated to the caller's existing decoder", () => {
  let calls = 0;
  const decoded = decodeStudyChatOperationReceipt(operationWire("committed"), {
    path: "operation",
    expectedSessionId: "session-1",
    expectedClientRequestId: "request-1",
    decodeResult(raw, path, evidence) {
      calls += 1;
      assert.equal(path, "operation.result");
      assert.deepEqual(raw, {
        reply: "answer",
        session: {
          id: "session-1",
          revision: 8,
          last_turn_sequence: 4,
          turns: [
            { id: "turn-1", sequence: 1 },
            { id: "turn-2", sequence: 2 },
            { id: "turn-3", sequence: 3 },
            { id: "turn-4", sequence: 4 },
          ],
        },
      });
      assert.deepEqual(evidence, {
        operationId: "study-chat-op-1",
        sessionId: "session-1",
        clientRequestId: "request-1",
        admittedSessionRevision: 7,
        committedSessionRevision: 8,
        committedTurnId: "turn-4",
        committedTurnSequence: 4,
      });
      return { normalized: true as const };
    },
  });
  assert.equal(calls, 1);
  assert.deepEqual(decoded.result, { normalized: true });

  calls = 0;
  const running = decodeStudyChatOperationReceipt(operationWire("running"), {
    expectedSessionId: "session-1",
    expectedClientRequestId: "request-1",
    decodeResult() {
      calls += 1;
      return { normalized: true as const };
    },
  });
  assert.equal(calls, 0);
  assert.equal(running.result, null);
});

test("outer receipt identity is fenced to the requested Session and request", () => {
  assert.throws(
    () => decode(operationWire(), { expectedSessionId: "session-2" }),
    (error: unknown) =>
      error instanceof StudyChatOperationDecodeError &&
      error.path === "study_chat_operation.session_id",
  );
  assert.throws(
    () => decode(operationWire(), { expectedClientRequestId: "request-2" }),
    (error: unknown) =>
      error instanceof StudyChatOperationDecodeError &&
      error.path === "study_chat_operation.client_request_id",
  );
  assert.throws(
    () => decode(operationWire(), { expectedSessionId: " " }),
    StudyChatOperationDecodeError,
  );
});

test("committed result decoder is mandatory and cannot return nullish output", () => {
  assert.throws(
    () => decode(operationWire("committed"), { decodeResult: () => null }),
    (error: unknown) =>
      error instanceof StudyChatOperationDecodeError &&
      error.path === "study_chat_operation.result",
  );
  assert.throws(
    () => decode(operationWire("committed"), { decodeResult: () => undefined }),
    StudyChatOperationDecodeError,
  );
  assert.throws(
    () => decodeStudyChatOperationReceipt(operationWire("committed"), {
      expectedSessionId: "session-1",
      expectedClientRequestId: "request-1",
    } as never),
    (error: unknown) => error instanceof StudyChatOperationDecodeError,
  );
  assert.throws(
    () => decode(operationWire("committed"), {
      decodeResult() {
        throw new TypeError("nested_decoder_failed");
      },
    }),
    (error: unknown) =>
      error instanceof StudyChatOperationDecodeError &&
      error.path === "study_chat_operation.result",
  );
  assert.throws(
    () => decode(operationWire("committed"), {
      decodeResult() {
        throw new StudySessionDecodeError(
          "study_chat_operation.result.citations[0]",
          "citation_source_identity_invalid",
        );
      },
    }),
    (error: unknown) => error instanceof StudySessionDecodeError &&
      error.path === "study_chat_operation.result.citations[0]",
  );
});

test("committed result is bound to the receipt Session, revision, and exact Turn", () => {
  const attacks: Array<[string, (payload: Record<string, unknown>) => void]> = [
    ["foreign Session", (payload) => {
      (payload.session as Record<string, unknown>).id = "session-2";
    }],
    ["foreign revision", (payload) => {
      (payload.session as Record<string, unknown>).revision = 99;
    }],
    ["missing committed Turn", (payload) => {
      (payload.session as Record<string, unknown>).turns = [
        { id: "turn-other", sequence: 4 },
      ];
    }],
    ["wrong committed Turn sequence", (payload) => {
      ((payload.session as Record<string, unknown>).turns as Array<Record<string, unknown>>)[3]!
        .sequence = 5;
    }],
    ["committed Turn beyond watermark", (payload) => {
      (payload.session as Record<string, unknown>).last_turn_sequence = 3;
    }],
    ["snapshot contains a later Turn watermark", (payload) => {
      const session = payload.session as Record<string, unknown>;
      session.last_turn_sequence = 5;
      (session.turns as Array<Record<string, unknown>>).push({
        id: "turn-5",
        sequence: 5,
      });
    }],
  ];
  for (const [label, attack] of attacks) {
    const wire = operationWire("committed");
    const result = structuredClone(wire.result as Record<string, unknown>);
    attack(result);
    assert.throws(
      () => decode({ ...wire, result }, { decodeResult: (raw) => raw }),
      StudyChatOperationDecodeError,
      `expected ${label} to fail before a permissive nested decoder can accept it`,
    );
  }
  assert.throws(
    () => decode({ ...operationWire("committed"), result: {} }),
    (error: unknown) =>
      error instanceof StudyChatOperationDecodeError &&
      error.path === "study_chat_operation.result.session",
  );
});

test("Study Chat operation decode errors are identifiable without trusting realms", () => {
  const local = new StudyChatOperationDecodeError(
    "study_chat_operation.status",
    "expected_registered_status",
  );
  assert.equal(isStudyChatOperationDecodeError(local), true);
  assert.equal(isStudyChatOperationDecodeError({
    code: "study_chat_operation_response_decode_error",
  }), true);
  assert.equal(isStudyChatOperationDecodeError(new Error("offline")), false);
});
