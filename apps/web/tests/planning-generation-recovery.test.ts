import assert from "node:assert/strict";
import test from "node:test";
import {
  decodePlanGenerationOperation,
  classifyPlanStreamFailure,
  PlanStreamTerminalError,
} from "../lib/plan-generation-outcome.ts";
import { ApiHttpError } from "../lib/http-error.ts";

const decode = (raw: unknown) =>
  decodePlanGenerationOperation(
    raw,
    identity,
    (plan, options) => {
      if (
        !plan ||
        typeof plan !== "object" ||
        !("id" in plan) ||
        plan.id !== options.expectedPlanId ||
        !("persona_id" in plan) ||
        typeof plan.persona_id !== "string"
      )
        throw new Error("invalid plan projection");
      return { personaId: plan.persona_id };
    },
    (path, reason) => {
      throw new Error(path + ": " + reason);
    },
  );

const identity = {
  clientRequestId: "audit-request",
  documentId: "doc-fixture",
  personaId: "persona-fixture",
};
const running = {
  contract_version: "learning-plan-operation-response-v1",
  operation_id: "plan-operation-fixture",
  client_request_id: identity.clientRequestId,
  document_id: identity.documentId,
  persona_id: identity.personaId,
  status: "running",
  projection_state: "pending",
  plan_id: "",
  plan: null,
};

test("clarifies all uncommitted operation outcomes without a plan", () => {
  assert.deepEqual(decode(running), {
    status: "running",
    planId: "",
  });
  for (const status of ["interrupted", "not_committed", "uncertain"]) {
    assert.deepEqual(
      decode({ ...running, status, projection_state: "not_committed" }),
      { status, planId: "" },
    );
  }
});

test("fails closed on mismatched identity, invalid state, or missing committed evidence", () => {
  for (const wrong of [
    { client_request_id: "other-request" },
    { document_id: "other-document" },
    { persona_id: "other-persona" },
    { plan_id: "unexpected" },
    { projection_state: "committed" },
    { status: "committed", projection_state: "committed", plan_id: "plan-fixture" },
  ]) {
    assert.throws(() => decode({ ...running, ...wrong }));
  }
});

test("only definite terminal evidence or known admission rejection permits another generation", () => {
  assert.equal(
    classifyPlanStreamFailure(
      new PlanStreamTerminalError("cancel", true, "not_committed"),
    ),
    "cancelled",
  );
  assert.equal(
    classifyPlanStreamFailure(new PlanStreamTerminalError("cancel", true, "uncertain")),
    "unconfirmed",
  );
  assert.equal(
    classifyPlanStreamFailure(
      new PlanStreamTerminalError("error", false, "not_committed"),
    ),
    "not_committed",
  );
  assert.equal(
    classifyPlanStreamFailure(new DOMException("cancel", "AbortError")),
    "unconfirmed",
  );
  assert.equal(
    classifyPlanStreamFailure(new Error("eof_before_terminal")),
    "unconfirmed",
  );
  assert.equal(
    classifyPlanStreamFailure(
      new ApiHttpError({ status: 404, message: "not found", payload: "gateway" }),
    ),
    "unconfirmed",
  );
});
