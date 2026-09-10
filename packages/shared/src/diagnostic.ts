import type { HarnessWorkflow, HarnessStage, HarnessAttemptPhase, HarnessAttemptStatus, HarnessStatus, HarnessCommitStatus, HarnessResourceType } from "./harness";

export type DiagnosticPagePath = "/" | "/plan" | "/study" | "/persona-spectrum" | "/scene-setup" | "/tavern" | "/settings" | "/sensory-tools" | "/model-usage";

/** Diagnostic hints only; HTTP completion never establishes domain commit. */
export interface DiagnosticEventV1 {
  schema_version: "diagnostic-event-v1";
  event_id: string;
  source: "server" | "browser" | "desktop";
  name: "decode_failed" | "page_entered" | "page_left" | "request_started" | "response_headers" | "request_finished" | "request_failed" | "request_cancelled" | "lifecycle_started" | "lifecycle_stopped" | "harness_reference" | "resource_reference" | "provider_started" | "provider_finished" | "provider_failed" | "provider_attempt_started" | "provider_attempt_finished" | "provider_attempt_failed" | "tool_started" | "tool_finished" | "tool_failed" | "tool_unknown" | "action_started" | "action_finished" | "action_failed" | "action_cancelled" | "desktop_started" | "sidecar_spawned" | "sidecar_ready" | "sidecar_startup_failed" | "sidecar_exited" | "desktop_shutdown_requested" | "sidecar_stopped" | "sidecar_shutdown_unknown" | "desktop_stopped";
  page_path?: DiagnosticPagePath | null;
  desktop_metric?: DiagnosticDesktopMetricV1 | null;
  action_name?: "json_import_read_persona" | "json_import_read_scene" | "json_export_handoff" | "settings_save" | "vault_create" | "vault_unlock" | "vault_lock" | "vault_load_secrets" | "vault_save_secrets" | "vault_clear_secrets" | null;
  span_id?: string | null;
  parent_span_id?: string | null;
  tool_metric?: DiagnosticToolMetricV1 | null;
  provider_metric?: DiagnosticProviderMetricV1 | null;
  resource?: { resource_type: "persona" | "scene"; resource_id: string; revision: number | null } | null;
  harness?: { operation_id: string; workflow: HarnessWorkflow; stage: HarnessStage; trace_id: string | null; attempt_id?: string | null; attempt_index?: number | null; phase?: HarnessAttemptPhase | null; attempt_status?: HarnessAttemptStatus | null } | null;
  category: "transport" | "lifecycle" | "harness" | "resource" | "provider" | "tool" | "action" | "desktop" | "page" | "decode";
  severity: "info" | "warning" | "error";
  outcome: "started" | "headers_received" | "completed" | "failed" | "cancelled" | "observed" | "unknown";
  error_code: "transport_failure" | "http_error" | "cancelled" | "provider_failure" | "tool_failure" | "action_failure" | "desktop_failure" | "decode_failure" | null;
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
  decode_failed: ["decode", "error", "failed", "decode_failure"],
  page_entered: ["page", "info", "started", null],
  page_left: ["page", "info", "completed", null],
  request_started: ["transport", "info", "started", null],
  response_headers: ["transport", "info", "headers_received", null],
  request_finished: ["transport", "info", "completed", null],
  request_failed: ["transport", "error", "failed", "transport_failure"],
  request_cancelled: ["transport", "warning", "cancelled", "cancelled"],
  lifecycle_started: ["lifecycle", "info", "started", null],
  lifecycle_stopped: ["lifecycle", "info", "completed", null],
  harness_reference: ["harness", "info", "observed", null],
  resource_reference: ["resource", "info", "observed", null],
  provider_started: ["provider", "info", "started", null],
  provider_finished: ["provider", "info", "completed", null],
  provider_failed: ["provider", "error", "failed", "provider_failure"],
  provider_attempt_started: ["provider", "info", "started", null],
  provider_attempt_finished: ["provider", "info", "completed", null],
  provider_attempt_failed: ["provider", "error", "failed", "provider_failure"],
  tool_started: ["tool", "info", "started", null],
  tool_finished: ["tool", "info", "completed", null],
  tool_failed: ["tool", "error", "failed", "tool_failure"],
  tool_unknown: ["tool", "warning", "unknown", null],
  action_started: ["action", "info", "started", null],
  action_finished: ["action", "info", "completed", null],
  action_failed: ["action", "error", "failed", "action_failure"],
  action_cancelled: ["action", "warning", "cancelled", "cancelled"],
  desktop_started: ["desktop", "info", "started", null],
  sidecar_spawned: ["desktop", "info", "started", null],
  sidecar_ready: ["desktop", "info", "completed", null],
  sidecar_startup_failed: ["desktop", "error", "failed", "desktop_failure"],
  sidecar_exited: ["desktop", "error", "failed", "desktop_failure"],
  desktop_shutdown_requested: ["desktop", "info", "started", null],
  sidecar_stopped: ["desktop", "info", "completed", null],
  sidecar_shutdown_unknown: ["desktop", "warning", "unknown", null],
  desktop_stopped: ["desktop", "info", "completed", null],
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
export interface DiagnosticCanonicalResourcesV1 {
  context_subjects: { resource_type: HarnessResourceType; resource_id: string; revision: number | null }[];
  attempted_outputs: { resource_type: HarnessResourceType; resource_id: string; revision: number | null }[];
  committed_outputs: { resource_type: HarnessResourceType; resource_id: string; expected_revision: number | null; committed_revision: number | null; first_sequence: number | null; last_sequence: number | null }[];
  scope: "historical_canonical_projection_requires_read_back";
}

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
  resources: DiagnosticCanonicalResourcesV1 | null;
  resources_gap: "not_backfilled" | "source_removed" | "source_invalid_or_unavailable" | null;
  components: { name: string; version: string }[];
  attempts: { attempt_id: string; attempt_index: number; phase: HarnessAttemptPhase; status: HarnessAttemptStatus; duration_ms: number }[];
  provider: null; model: null; tokens: null; cost: null;
  usage_gap: "not_recorded_in_canonical_trace";
  correlation_gap: "resolve_request_links_separately";
}


export interface DiagnosticProviderMetricV1 {
  adapter: "litellm";
  adapter_contract: "diagnostic-provider-transport-v1";
  request_kind: "plan" | "chat" | "setting" | "embedding" | "other";
  model: string | null;
  model_gap: "model_label_unreviewed" | null;
  timeout_seconds: number;
  max_attempts: 3;
  attempt_index: number | null;
  attempts_used: number;
  recovered: boolean;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  usage_source: "provider_reported" | "unavailable";
  usage_gap: "not_returned" | "partial_or_invalid" | "aggregate_not_additive" | null;
  cost: null;
  cost_gap: "provider_cost_evidence_unavailable";
  configuration_gap: "endpoint_configuration_not_recorded";
}


export interface DiagnosticToolMetricV1 {
  workflow: HarnessWorkflow;
  offered_in_stage: HarnessStage;
  execution_stage: HarnessStage | null;
  manifest_key: string | null;
  canonical_name: string | null;
  input_contract_version: string | null;
  result_contract_version: string | null;
  provider_tool_call_id: string | null;
  max_calls_per_operation: number | null;
  max_calls_per_round: number | null;
  timeout_ms: number | null;
  manifest_gap: "unregistered_tool" | null;
  effect_commit_claim: "none";
}


export interface DiagnosticDesktopMetricV1 {
  instance_id: string;
  exit_code: number | null;
  dropped_before: number;
  write_failures_before: number;
}

/** Query filters are diagnostic hints. Dates require an explicit timezone. */
export interface DiagnosticEventFilters {
  request_id?: string;
  action_id?: string;
  flow_id?: string;
  page_view_id?: string;
  page_path?: DiagnosticPagePath;
  source?: DiagnosticEventV1["source"];
  severity?: DiagnosticEventV1["severity"];
  operation_id?: string;
  workflow?: HarnessWorkflow;
  stage?: HarnessStage;
  resource_id?: string;
  resource_type?: HarnessResourceType;
  since?: string;
  until?: string;
}

export interface DiagnosticEventRetentionV1 {
  schema_version: "diagnostic-event-retention-v1";
  retained_events: number;
  retained_payload_bytes: number;
  removed_events: number;
  removed_through_sequence: number;
  legacy_timestamp_rows: number;
  cursor_gap: boolean;
  max_age_seconds: number;
  max_rows: number;
  max_payload_bytes: number;
  storage_scope: "event_payloads";
  disk_size_limit_certified: false;
}

export interface DiagnosticEventPageV1 {
  retention: DiagnosticEventRetentionV1;
  items: { sequence: number; event: DiagnosticEventV1 }[];
  next_cursor: number;
  has_more: boolean;
  health: { dropped: number; write_failures: number; read_failures: number; queued: number; writer_alive: boolean };
  desktop_spool: { rejected: number; failures: number } | null;
}


export interface DiagnosticOperationLinkV1 {
  operation_id: string;
  request_id: string;
  client_instance_id?: string | null;
  page_view_id?: string | null;
  flow_id?: string | null;
  action_id?: string | null;
  workflow?: HarnessWorkflow | null;
  stage?: HarnessStage | null;
}

export interface DiagnosticWriterEpochV1 {
  sequence: number;
  epoch_id: string;
  started_at: number;
  observed_at: number;
  closed_at: number | null;
  observed_dropped: number;
  observed_write_failures: number;
  observed_read_failures: number;
}
export interface DiagnosticWriterCoverageV1 {
  schema_version: "diagnostic-writer-coverage-v1";
  items: DiagnosticWriterEpochV1[];
  next_cursor: number;
  has_more: boolean;
  totals: { retired_epochs: number; retired_unclosed: number; retained_epochs: number; unclosed_epochs: number; observed_dropped: number; observed_write_failures: number; observed_read_failures: number };
  counts_are_lower_bounds: true;
  unpersisted_queue_gap: true;
  startup_before_epoch_gap: true;
  unclosed_meaning: "active_or_interrupted";
  complete_collection_claim: false;
}


export interface DiagnosticIndexFilters extends Pick<DiagnosticEventFilters, "operation_id" | "workflow" | "stage" | "resource_id" | "resource_type"> {
  resource_role?: "context_subjects" | "attempted_outputs" | "committed_outputs";
}
