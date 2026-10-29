import assert from "node:assert/strict";
import { test } from "node:test";
import { sendStudyMessage, getStudyChatOperation } from "../lib/api.ts";
import {
  STUDY_SEND_WAIT_MS,
  STUDY_QUERY_WAIT_MS,
  StudyRequestWaitExpired,
} from "../lib/study-request-deadline.ts";

test("a stalled Study POST times out locally, aborts transport and never issues another POST", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const original = globalThis.fetch;
  const requests = [];
  let finish;
  globalThis.fetch = async (_url, init) => {
    requests.push(init);
    return new Promise((resolve) => {
      finish = resolve;
    });
  };
  try {
    const pending = sendStudyMessage({
      sessionId: "session",
      clientRequestId: "timeout-original",
      expectedSessionRevision: 0,
      message: "Keep original identity",
    });
    const rejected = assert.rejects(pending, StudyRequestWaitExpired);
    t.mock.timers.tick(STUDY_SEND_WAIT_MS);
    await rejected;
    assert.equal(requests.length, 1);
    assert.equal(requests[0].signal.aborted, true);
    finish(Response.json({ detail: "late" }, { status: 503 }));
    await Promise.resolve();
    assert.equal(requests.length, 1);
  } finally {
    globalThis.fetch = original;
  }
});

test("read-back has a shorter deadline that also covers a stalled response body", async (t) => {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const original = globalThis.fetch;
  let signal;
  globalThis.fetch = async (_url, init) => {
    signal = init.signal;
    return new Response(new ReadableStream({ start() {} }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };
  try {
    const pending = getStudyChatOperation({
      sessionId: "session",
      clientRequestId: "timeout-original",
    });
    const rejected = assert.rejects(pending, StudyRequestWaitExpired);
    await Promise.resolve();
    t.mock.timers.tick(STUDY_QUERY_WAIT_MS);
    await rejected;
    assert.equal(signal.aborted, true);
  } finally {
    globalThis.fetch = original;
  }
});
