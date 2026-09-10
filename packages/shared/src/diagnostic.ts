import type { HarnessWorkflow, HarnessStage, HarnessAttemptPhase, HarnessAttemptStatus, HarnessStatus, HarnessCommitStatus } from "./harness";

/** Diagnostic hints only; HTTP completion never establishes domain commit. */
export interface DiagnosticEventV1 {
  schema_version: "diagnostic-event-v1";
  event_id: string;
  source: "server" | "browser" | "desktop";
  name: "request_started" | "response_headers" | "request_finished" | "request_failed" | "request_cancelled" | "lifecycle_started" | "lifecycle_stopped" | "harness_reference" | "resource_reference";
  resource?: { resource_type: "persona"; resource_id: string; revision: number | null } | null;
  harness?: { operation_id: string; workflow: HarnessWorkflow; stage: HarnessStage; trace_id: string | null; attempt_id?: string | null; attempt_index?: number | null; phase?: HarnessAttemptPhase | null; attempt_status?: HarnessAttemptStatus | null } | null;
  category: "transport" | "lifecycle" | "harness" | "resource";
  severity: "info" | "warning" | "error";
  outcome: "started" | "headers_received" | "completed" | "failed" | "cancelled" | "observed";
  error_code: "transport_failure" | "http_error" | "cancelled" | null;
  timestamp: string;
  request_id: string | null;
  client_instance_id: string | null;
  page_view_id: string | null;
  flow_id: string | null;
  action_id: string | null;
  duration_ms: number | null;
  status_code: number | null;
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE" | "OPTIONS" | "HEAD" | null;
  route: string | null;
}

export const DIAGNOSTIC_EVENT_CATALOG = {
  request_started: ["transport", "info", "started", null],
  response_headers: ["transport", "info", "headers_received", null],
  request_finished: ["transport", "info", "completed", null],
  request_failed: ["transport", "error", "failed", "transport_failure"],
  request_cancelled: ["transport", "warning", "cancelled", "cancelled"],
  lifecycle_started: ["lifecycle", "info", "started", null],
  lifecycle_stopped: ["lifecycle", "info", "completed", null],
  harness_reference: ["harness", "info", "observed", null],
  resource_reference: ["resource", "info", "observed", null],
} as const;

export function classifyDiagnostic(name: DiagnosticEventV1["name"], statusCode: number | null = null):
  Pick<DiagnosticEventV1, "category" | "severity" | "outcome" | "error_code"> {
  const [category, severity, outcome, error_code] = DIAGNOSTIC_EVENT_CATALOG[name];
  const result: Pick<DiagnosticEventV1, "category" | "severity" | "outcome" | "error_code"> = { category, severity, outcome, error_code };
  if ((name === "response_headers" || name === "request_finished") && statusCode !== null && statusCode >= 400) {
    result.severity = statusCode >= 500 ? "error" : "warning";
    result.error_code = "http_error";
    if (name === "request_finished") result.outcome = "failed";
  }
  return result;
}


/** Eventually consistent diagnostic projection. Resolve canonical records for commit truth. */
export interface DiagnosticHarnessIndexV1 {
  schema_version: "diagnostic-harness-index-v1";
  trace_id: string;
  parent_trace_id: string | null;
  operation_id: string | null;
  workflow: HarnessWorkflow | null;
  stage: HarnessStage | null;
  state: "prepared" | "claimed" | "terminal" | null;
  status: HarnessStatus | null;
  commit_status: HarnessCommitStatus | null;
  duration_ms: number | null;
  started_at: string | null;
  completed_at: string | null;
  source_updated_at: string | null;
  gap: "source_removed" | "source_invalid_or_unavailable" | "terminal_trace_not_available" | null;
  components: { name: string; version: string }[];
  attempts: { attempt_id: string; attempt_index: number; phase: HarnessAttemptPhase; status: HarnessAttemptStatus; duration_ms: number }[];
  provider: null; model: null; tokens: null; cost: null;
  usage_gap: "not_recorded_in_canonical_trace";
  correlation_gap: "resolve_request_links_separately";
}
