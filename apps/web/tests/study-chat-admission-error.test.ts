import assert from "node:assert/strict";
import test from "node:test";

import {
  ApiHttpError,
  isDefiniteStudyChatPreAdmissionError,
  isMissingStudyChatOperationError,
} from "../lib/http-error.ts";

function httpError(status: number, code: string) {
  return new ApiHttpError({ status, code, message: code, payload: { detail: code } });
}

test("only explicit pre-admission HTTP failures unlock the original operation identity", () => {
  for (const [status, code] of [
    [404, "session_not_found"],
    [409, "study_chat_session_revision_conflict"],
    [409, "study_chat_request_id_reused"],
    [409, "study_chat_operation_already_active"],
    [422, "request_validation_failed"],
  ] as const) {
    assert.equal(isDefiniteStudyChatPreAdmissionError(httpError(status, code)), true);
  }
});

test("ambiguous transport and provider failures remain query-only", () => {
  assert.equal(isDefiniteStudyChatPreAdmissionError(new Error("network lost")), false);
  assert.equal(isDefiniteStudyChatPreAdmissionError(httpError(408, "request_timeout")), false);
  assert.equal(isDefiniteStudyChatPreAdmissionError(httpError(502, "provider_failed")), false);
  assert.equal(isDefiniteStudyChatPreAdmissionError(httpError(404, "unknown_proxy_route")), false);
});

test("a missing operation GET is distinct from a missing Session POST", () => {
  assert.equal(
    isMissingStudyChatOperationError(httpError(404, "study_chat_operation_not_found")),
    true,
  );
  assert.equal(isMissingStudyChatOperationError(httpError(404, "session_not_found")), false);
});
