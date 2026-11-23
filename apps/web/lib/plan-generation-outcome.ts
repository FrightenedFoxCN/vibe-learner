import { StrictResponseDecoder } from "./strict-response-decode.ts";
import { isApiHttpError } from "./http-error.ts";

export interface PlanGenerationIdentity {
  clientRequestId: string;
  documentId: string;
  personaId: string;
}

export function decodePlanGenerationOperation(
  raw: unknown,
  identity: PlanGenerationIdentity,
  decodePlan: (
    raw: unknown,
    options: { expectedPlanId: string; expectedDocumentId: string; path: string },
  ) => { personaId: string },
  fail: (field: string, reason: string) => never,
) {
  const path = "learning_plan_operation";
  const d = new StrictResponseDecoder(fail);
  const value = d.record(raw, path);
  const field = (key: string) => d.field(value, key, path);
  d.equal(
    field("contract_version"),
    "learning-plan-operation-response-v1",
    path + ".contract_version",
  );
  d.string(field("operation_id"), path + ".operation_id");
  d.equal(
    field("client_request_id"),
    identity.clientRequestId,
    path + ".client_request_id",
  );
  d.equal(field("document_id"), identity.documentId, path + ".document_id");
  d.equal(field("persona_id"), identity.personaId, path + ".persona_id");
  const status = d.enumeration(
    field("status"),
    ["running", "committed", "interrupted", "not_committed", "uncertain"],
    path + ".status",
  );
  const projectionState =
    status === "committed"
      ? "committed"
      : status === "running"
        ? "pending"
        : "not_committed";
  d.equal(field("projection_state"), projectionState, path + ".projection_state");
  const planId = d.string(field("plan_id"), path + ".plan_id", status !== "committed");
  const plan = field("plan");
  if (status === "committed") {
    const snapshot = decodePlan(plan, {
      expectedPlanId: planId,
      expectedDocumentId: identity.documentId,
      path: path + ".plan",
    });
    d.equal(snapshot.personaId, identity.personaId, path + ".plan.persona_id");
  } else if (plan !== null || planId !== "") {
    fail(path + ".plan", "unexpected_uncommitted_projection");
  }
  return { status, planId };
}

export class PlanStreamTerminalError extends Error {
  readonly cancelled: boolean;
  readonly notCommitted: boolean;

  constructor(message: string, cancelled: boolean, commitStatus: string | undefined) {
    super(message);
    this.cancelled = cancelled;
    this.notCommitted = commitStatus === "not_committed";
  }
}

export function classifyPlanStreamFailure(error: unknown) {
  if (error instanceof PlanStreamTerminalError && error.notCommitted) {
    return error.cancelled ? "cancelled" : "not_committed";
  }
  if (isApiHttpError(error) && error.status === 422) return "not_committed";
  if (
    isApiHttpError(error) &&
    error.status === 404 &&
    typeof error.payload === "object" &&
    error.payload !== null &&
    "detail" in error.payload &&
    ["document_not_found", "document_debug_not_found", "persona_not_found"].includes(
      String(error.payload.detail),
    )
  )
    return "not_committed";
  return "unconfirmed";
}
