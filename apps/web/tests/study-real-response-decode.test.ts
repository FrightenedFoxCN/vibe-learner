import assert from "node:assert/strict";
import test from "node:test";

import { decodeStudyChatOperationReceipt } from "../lib/study-chat-operation-decode.ts";
import { decodeStudyChatExchange } from "../lib/study-session-decode.ts";

const apiBaseUrl = process.env.STUDY_TEST_API_URL;
const sessionId = process.env.STUDY_TEST_SESSION_ID;
const clientRequestId = process.env.STUDY_TEST_CLIENT_REQUEST_ID;
const configured = Boolean(apiBaseUrl && sessionId && clientRequestId);

test("strict Study decoders accept one live committed operation read-back", {
  skip: !configured,
}, async () => {
  assert.ok(apiBaseUrl && sessionId && clientRequestId);
  const response = await fetch(
    `${apiBaseUrl}/study-sessions/${encodeURIComponent(sessionId)}` +
      `/chat-operations/${encodeURIComponent(clientRequestId)}`,
  );
  assert.equal(response.ok, true);
  const payload: unknown = await response.json();
  const receipt = decodeStudyChatOperationReceipt(payload, {
    expectedSessionId: sessionId,
    expectedClientRequestId: clientRequestId,
    decodeResult: (raw, path, evidence) =>
      decodeStudyChatExchange(raw, {
        path,
        expectedSessionId: sessionId,
        evidence,
      }),
  });
  assert.equal(receipt.status, "committed");
  assert.ok(receipt.result);
  assert.equal(receipt.result.session.id, sessionId);
});
