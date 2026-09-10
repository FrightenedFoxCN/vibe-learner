import type { DiagnosticEventV1, DiagnosticEventFilters, DiagnosticEventRetentionV1, DiagnosticHarnessIndexV1, DiagnosticOperationLinkV1, DiagnosticWriterCoverageV1 } from "./diagnostic";
import type { HarnessWorkflow, HarnessStage, HarnessAttemptPhase } from "./harness";

export type DiagnosticMetricGap = "missing_start" | "missing_terminal" | "missing_span" | "conflicting_span_records" | "harness_reference_missing" | "component_context_unavailable" | "endpoint_configuration_not_recorded" | "provider_cost_evidence_unavailable" | "usage_not_returned" | "usage_partial_or_invalid" | "usage_not_additive" | "source_unavailable" | "duration_unavailable" | "model_label_unreviewed" | "metric_missing";
export interface DiagnosticAuditGroupKeyV1 {
  kind: "provider_call" | "provider_attempt" | "tool_call" | "harness_stage" | "harness_attempt";
  workflow: HarnessWorkflow | null;
  stage: HarnessStage | null;
  phase: HarnessAttemptPhase | null;
  provider: "litellm" | null;
  request_kind: "plan" | "chat" | "setting" | "embedding" | "other" | null;
  model: string | null;
  provider_contract: "diagnostic-provider-transport-v1" | null;
  timeout_ms: number | null;
  retry_limit: number | null;
  tool_name: string | null;
  input_contract: string | null;
  result_contract: string | null;
  tool_max_calls_operation: number | null;
  tool_max_calls_round: number | null;
  components: { name: string; version: string }[];
}
export interface DiagnosticAuditObservationV1 {
  sample_id: string;
  group: DiagnosticAuditGroupKeyV1;
  event_ids: string[];
  operation_id: string | null;
  trace_id: string | null;
  span_id: string | null;
  parent_span_id: string | null;
  outcome: "completed" | "failed" | "cancelled" | "unknown" | "skipped";
  duration_ms: number | null;
  recovered: boolean;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  gaps: DiagnosticMetricGap[];
}
export interface DiagnosticAuditGroupV1 {
  key: DiagnosticAuditGroupKeyV1;
  sample_count: number;
  completed_count: number;
  failed_count: number;
  cancelled_count: number;
  unknown_count: number;
  skipped_count: number;
  recovered_count: number;
  duration_sample_count: number;
  p50_ms: number | null;
  p95_ms: number | null;
  input_tokens: number | null;
  output_tokens: number | null;
  total_tokens: number | null;
  input_token_sample_count: number;
  output_token_sample_count: number;
  total_token_sample_count: number;
  gaps: { gap: DiagnosticMetricGap; count: number }[];
}
export interface DiagnosticAuditV1 {
  schema_version: "diagnostic-audit-v1";
  observations: DiagnosticAuditObservationV1[];
  groups: DiagnosticAuditGroupV1[];
  input_event_count: number;
  input_trace_count: number;
  duplicate_event_count: number;
  percentile_method: "nearest_rank";
  duration_aggregation: "per_kind_inclusive_never_additive";
  token_aggregation: "provider_attempts_only";
  commit_claim: "none";
  coverage_gap: "bounded_inputs_not_complete_installation";
}
export type DiagnosticExportFiltersV1 = { [K in keyof DiagnosticEventFilters]?: DiagnosticEventFilters[K] | null };
export interface DiagnosticExportV1 {
  schema_version: "diagnostic-export-v1";
  storage_observation: DiagnosticStorageV1;
  app_version: string;
  created_at: string;
  filters: DiagnosticExportFiltersV1;
  snapshot_consistency: "events_links_retention_writers_atomic_index_independent";
  complete_collection_claim: false;
  events: { sequence: number; event: DiagnosticEventV1 }[];
  operation_links: DiagnosticOperationLinkV1[];
  retention: DiagnosticEventRetentionV1;
  link_retention: DiagnosticRecordRetentionV1;
  index_retention: DiagnosticRecordRetentionV1 | null;
  writer_pages: DiagnosticWriterCoverageV1[];
  index: DiagnosticHarnessIndexV1[];
  index_coverage: {
    freshness: "eventual" | "unavailable";
    cursor: string | null;
    completed_sweeps: number | null;
    canonical_read_back_required: true;
    scope: "all_retained" | "workflow_stage" | "related_operations";
    missing_operation_count: number;
    time_and_event_filters_apply_to_traces: false;
  };
  audit: DiagnosticAuditV1;
}


export interface DiagnosticRecordRetentionV1 {
  schema_version: "diagnostic-record-retention-v1";
  table: "operation_links" | "projections";
  retained_rows: number;
  retained_payload_bytes: number;
  removed_rows: number;
  legacy_timestamp_rows: number;
  max_rows: number;
  max_payload_bytes: number;
  max_age_seconds: number;
  age_basis: "first_local_observation" | "canonical_update_or_first_local_observation";
  removed_count_scope: "deletions_not_unique_identities";
  source_age_exclusions_possible: boolean;
  complete_history_claim: false;
  disk_size_limit_certified: false;
}


export interface DiagnosticStorageDatabaseV1 {
  name: "events" | "index";
  max_bytes: number | null;
  files: { database: number; wal: number; shm: number; journal: number; lock: number; total_bytes: number } | null;
  counters: { quota_refusals: number; quota_unavailable: number; maintenance_busy: number; maintenance_failures: number; maintenance_completed: number; legacy_migrations: number } | null;
  recovery: { attempts: number; completed: number; deferred: number; failures: number; workspace_bytes: number; temporary_overage_possible: true } | null;
  status: "within_observed_limit" | "over_observed_limit" | "unavailable";
  gap: "not_configured" | "database_absent" | "filesystem_unavailable" | null;
}
export interface DiagnosticDirectoryStorageV1 {
  scope: "diagnostics_directory_regular_file_lengths";
  status: "observed" | "absent" | "incomplete" | "unavailable";
  gaps: ("not_configured" | "filesystem_unavailable" | "configured_database_outside_directory" | "scan_limit" | "depth_limit" | "time_limit" | "unsupported_entry")[];
  budget_state: "within_observed_limit" | "over_observed_limit" | "unknown";
  database_bytes: number; spool_bytes: number; other_bytes: number; total_bytes: number;
  database_files: number; spool_files: number; other_files: number;
  scanned_entries: number; visited_directories: number; skipped_entries: number;
  max_bytes: 209715200; scan_limit: 4096; max_depth: 4; scan_budget_ms: 100;
}
export interface DiagnosticStorageV1 {
  schema_version: "diagnostic-storage-v1";
  observed_at: string;
  databases: DiagnosticStorageDatabaseV1[];
  directory: DiagnosticDirectoryStorageV1;
  desktop_spool: {
    status: "observed" | "absent" | "incomplete" | "unavailable";
    gap: "not_configured" | "filesystem_unavailable" | "scan_limit" | "unsupported_entry" | null;
    event_files: number; event_bytes: number; metadata_bytes: number;
    other_files: number; other_bytes: number; skipped_entries: number; total_bytes: number;
    max_event_files: 256; max_event_bytes: 4194304; scan_limit: 1024;
  };
  observation_scope: "independent_live_file_lengths_and_process_counters";
  sizes_are_atomic: false;
  counters_are_process_local: true;
  admission_guarantee: false;
  installation_disk_limit_certified: false;
  unmeasured: ("filesystem_allocation_and_metadata" | "external_writers" | "vacuum_temporary_files")[];
}
