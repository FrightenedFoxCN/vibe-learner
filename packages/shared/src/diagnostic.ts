import type { HarnessWorkflow, HarnessStage } from "./harness";

/** Diagnostic hints only; HTTP completion never establishes domain commit. */
export interface DiagnosticEventV1 {
  schema_version: "diagnostic-event-v1";
  event_id: string;
  source: "server" | "browser" | "desktop";
  name: "request_started" | "response_headers" | "request_finished" | "request_failed" | "request_cancelled" | "lifecycle_started" | "lifecycle_stopped" | "harness_reference" | "resource_reference";
  resource?: { resource_type: "persona"; resource_id: string; revision: number | null } | null;
  harness?: { operation_id: string; workflow: HarnessWorkflow; stage: HarnessStage; trace_id: string | null } | null;
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
