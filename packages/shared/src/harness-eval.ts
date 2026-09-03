import { HARNESS_OPERATION_STAGE_REGISTRATIONS } from "./harness.ts";
import type {
  HarnessContractRef,
  HarnessOperationStageKey,
  HarnessStage,
  HarnessWorkflow,
} from "./harness";

export const HARNESS_EVAL_CASE_SCHEMA_VERSION = "harness-eval-case-v1" as const;
export const HARNESS_EVAL_RUN_SCHEMA_VERSION = "harness-eval-run-v1" as const;
export const HARNESS_EVAL_SAMPLE_SCHEMA_VERSION = "harness-eval-sample-v1" as const;
export const HARNESS_EVAL_REPORT_SCHEMA_VERSION = "harness-eval-report-v1" as const;
export const HARNESS_EVAL_METRIC_SCHEMA_VERSION = "harness-eval-metric-v1" as const;
export const HARNESS_EVAL_GRADER_RESULT_SCHEMA_VERSION =
  "harness-eval-grader-result-v1" as const;
export const HARNESS_EVAL_FAILURE_SCHEMA_VERSION = "harness-eval-failure-v1" as const;
export const HARNESS_EVAL_FAILURE_TAXONOMY_SCHEMA_VERSION =
  "harness-eval-failure-taxonomy-v1" as const;
export const HARNESS_EVAL_SYSTEM_CONFIG_SCHEMA_VERSION =
  "harness-eval-system-config-v1" as const;
export const HARNESS_EVAL_ENVIRONMENT_SCHEMA_VERSION =
  "harness-eval-environment-v1" as const;
export const HARNESS_EVAL_RAW_SAMPLES_SCHEMA_VERSION =
  "harness-eval-raw-samples-v1" as const;
export const HARNESS_EVAL_CONTRACT_GOLDEN_SCHEMA_VERSION =
  "harness-eval-contract-golden-v1" as const;
export const HARNESS_EVAL_BASELINE_SCHEMA_VERSION =
  "harness-eval-baseline-v1" as const;
export const HARNESS_EVAL_GATE_DECISION_SCHEMA_VERSION =
  "harness-eval-gate-decision-v1" as const;

export type HarnessEvalSensitivity = "public" | "internal" | "protected";
export type HarnessEvalSplit =
  | "development"
  | "validation"
  | "held_out"
  | "calibration"
  | "regression";
export type HarnessEvalSourceMode = "fixture" | "synthetic" | "protected_artifact";
export type HarnessEvalSampleStatus = "passed" | "failed" | "broken" | "skipped";
export type HarnessEvalCandidateOutcome =
  | "passed"
  | "repaired"
  | "failed"
  | "skipped"
  | "unavailable";
export type HarnessEvalFailureOwner = "case" | "runner" | "candidate" | "grader" | "metric";
export type HarnessEvalFailureCategory =
  | "contract"
  | "resolution"
  | "configuration"
  | "execution"
  | "decode"
  | "validation"
  | "recovery"
  | "commit"
  | "effect"
  | "grading"
  | "measurement"
  | "sensitivity";
export type HarnessEvalFailureReleaseClass =
  | "candidate_failure"
  | "infrastructure_failure"
  | "data_failure"
  | "incomparable";

export interface HarnessEvalFixtureSourceV1 {
  source_mode: "fixture";
  fixture_id: string;
  payload_contract: HarnessContractRef;
  payload_digest: string;
}

export interface HarnessEvalSyntheticSourceV1 {
  source_mode: "synthetic";
  generator_contract: HarnessContractRef;
  seed: number;
  manifest_digest: string;
}

export interface HarnessEvalProtectedArtifactSourceV1 {
  source_mode: "protected_artifact";
  artifact_type: string;
  artifact_id: string;
  artifact_contract: HarnessContractRef;
  payload_digest: string;
}

export type HarnessEvalSourceV1 =
  | HarnessEvalFixtureSourceV1
  | HarnessEvalSyntheticSourceV1
  | HarnessEvalProtectedArtifactSourceV1;

export interface HarnessEvalProvenanceV1 {
  source_kind:
    | "developer_authored"
    | "independently_reviewed"
    | "synthetic"
    | "production_derived"
    | "imported";
  review_status: "unreviewed" | "developer_reviewed" | "independently_reviewed";
  review_contract: HarnessContractRef | null;
  attestation_digest: string | null;
}

export interface HarnessEvalExpectedInvariantV1 {
  invariant: HarnessContractRef;
  expected_outcome: "passed" | "failed" | "not_applicable";
}

export interface HarnessEvalCaseRefV1 {
  suite: HarnessContractRef;
  case_id: string;
  case_version: string;
  case_digest: string;
}

export interface HarnessEvalCaseV1 {
  schema_name: "HarnessEvalCase";
  schema_version: typeof HARNESS_EVAL_CASE_SCHEMA_VERSION;
  case_id: string;
  case_version: string;
  case_digest: string;
  suite: HarnessContractRef;
  workflow: HarnessWorkflow;
  stage: HarnessStage;
  eval_route: string;
  source: HarnessEvalSourceV1;
  provenance: HarnessEvalProvenanceV1;
  sensitivity: HarnessEvalSensitivity;
  split: HarnessEvalSplit;
  tags: string[];
  expected_invariants: HarnessEvalExpectedInvariantV1[];
  grader_refs: HarnessContractRef[];
}

export interface HarnessEvalSystemConfigV1 {
  schema_name: "HarnessEvalSystemConfig";
  schema_version: typeof HARNESS_EVAL_SYSTEM_CONFIG_SCHEMA_VERSION;
  workflow_manifest_contract: HarnessContractRef;
  harness_contract: HarnessContractRef;
  provider_adapter_contract: HarnessContractRef;
  provider_model_contract: HarnessContractRef;
  input_contract: HarnessContractRef;
  output_contract: HarnessContractRef;
  prompt_contract: HarnessContractRef | null;
  policy_contract: HarnessContractRef | null;
  toolset_contract: HarnessContractRef | null;
  component_contracts: HarnessContractRef[];
  reasoning: {
    mode:
      | "not_supported"
      | "disabled"
      | "minimal"
      | "low"
      | "medium"
      | "high"
      | "xhigh"
      | "max"
      | "ultra";
    budget_tokens: number | null;
  };
  sampling: {
    temperature: number | null;
    top_p: number | null;
    seed_strategy: "provider_unsupported" | "per_sample" | "fixed";
    fixed_seed: number | null;
  };
  budgets: {
    max_attempts: number;
    max_repairs: number;
    max_tool_calls: number;
    max_provider_calls: number;
    max_input_tokens: number;
    max_output_tokens: number;
    max_wall_time_ms: number;
    per_call_timeout_ms: number;
    max_cost_micro_usd: number;
  };
  source_revision: string;
  worktree_state: "clean" | "dirty";
  source_tree_digest: string | null;
}

export interface HarnessEvalEnvironmentV1 {
  schema_name: "HarnessEvalEnvironment";
  schema_version: typeof HARNESS_EVAL_ENVIRONMENT_SCHEMA_VERSION;
  environment_contract: HarnessContractRef;
  platform: string;
  architecture: string;
  python_version: string;
  node_version: string | null;
  database_kind: "none" | "sqlite" | "postgresql";
  provider_mode: "mock" | "local" | "live";
}

export interface HarnessEvalRunV1 {
  schema_name: "HarnessEvalRun";
  schema_version: typeof HARNESS_EVAL_RUN_SCHEMA_VERSION;
  run_id: string;
  suite: HarnessContractRef;
  suite_manifest_digest: string;
  case_set_digest: string;
  execution_mode: "fixture" | "synthetic" | "protected_replay";
  splits: HarnessEvalSplit[];
  repetition_count: number;
  seeds: number[];
  runner_contract: HarnessContractRef;
  failure_taxonomy_contract: HarnessContractRef;
  grader_registry_contract: HarnessContractRef;
  tested_system: HarnessEvalSystemConfigV1;
  tested_system_config_digest: string;
  environment: HarnessEvalEnvironmentV1;
  environment_digest: string;
  admitted_at: string;
  run_digest: string;
}

export interface HarnessEvalBooleanMetricV1 {
  schema_name: "HarnessEvalMetric";
  schema_version: typeof HARNESS_EVAL_METRIC_SCHEMA_VERSION;
  metric: HarnessContractRef;
  value_type: "boolean";
  unit: "boolean";
  value: boolean;
  evidence_digest: string;
}

export interface HarnessEvalIntegerMetricV1 {
  schema_name: "HarnessEvalMetric";
  schema_version: typeof HARNESS_EVAL_METRIC_SCHEMA_VERSION;
  metric: HarnessContractRef;
  value_type: "integer";
  unit:
    | "count"
    | "milliseconds"
    | "bytes"
    | "tokens"
    | "tool_calls"
    | "provider_calls"
    | "micro_usd";
  value: number;
  evidence_digest: string;
}

export interface HarnessEvalNumberMetricV1 {
  schema_name: "HarnessEvalMetric";
  schema_version: typeof HARNESS_EVAL_METRIC_SCHEMA_VERSION;
  metric: HarnessContractRef;
  value_type: "number";
  unit: "ratio" | "score";
  value: number;
  evidence_digest: string;
}

export type HarnessEvalMetricObservationV1 =
  | HarnessEvalBooleanMetricV1
  | HarnessEvalIntegerMetricV1
  | HarnessEvalNumberMetricV1;

export interface HarnessEvalMetricAggregateV1 {
  schema_name: "HarnessEvalMetricAggregate";
  schema_version: typeof HARNESS_EVAL_METRIC_SCHEMA_VERSION;
  metric: HarnessContractRef;
  aggregation: "count" | "sum" | "mean" | "min" | "max" | "rate" | "p50" | "p95";
  unit:
    | "boolean"
    | "ratio"
    | "score"
    | "count"
    | "milliseconds"
    | "bytes"
    | "tokens"
    | "tool_calls"
    | "provider_calls"
    | "micro_usd";
  value: number;
  population_count: number;
  excluded_count: number;
  numerator: number | null;
  denominator: number | null;
  percentile_method: "nearest_rank" | null;
}

export interface HarnessEvalGraderResultV1 {
  schema_name: "HarnessEvalGraderResult";
  schema_version: typeof HARNESS_EVAL_GRADER_RESULT_SCHEMA_VERSION;
  grader_result_id: string;
  grader: HarnessContractRef;
  grader_kind: "deterministic" | "model" | "human";
  grader_config_digest: string;
  execution_status: "completed" | "error" | "skipped";
  verdict: "passed" | "failed" | "not_applicable" | null;
  score: number | null;
  metrics: HarnessEvalMetricObservationV1[];
  failure_codes: string[];
  evidence_digest: string | null;
  duration_ms: number;
}

export interface HarnessEvalFailureTaxonomyEntryV1 {
  code: string;
  owner: HarnessEvalFailureOwner;
  category: HarnessEvalFailureCategory;
  release_class: HarnessEvalFailureReleaseClass;
  retryable: boolean;
  counts_as_candidate_failure: boolean;
  allowed_sample_statuses: HarnessEvalSampleStatus[];
}

export interface HarnessEvalFailureTaxonomyRegistryV1 {
  schema_name: "HarnessEvalFailureTaxonomy";
  schema_version: typeof HARNESS_EVAL_FAILURE_TAXONOMY_SCHEMA_VERSION;
  entries: HarnessEvalFailureTaxonomyEntryV1[];
}

export interface HarnessEvalFailureV1 {
  schema_name: "HarnessEvalFailure";
  schema_version: typeof HARNESS_EVAL_FAILURE_SCHEMA_VERSION;
  failure_code: string;
  owner: HarnessEvalFailureOwner;
  reason_code: string;
  evidence_digest: string | null;
}

export interface HarnessEvalSampleV1 {
  schema_name: "HarnessEvalSample";
  schema_version: typeof HARNESS_EVAL_SAMPLE_SCHEMA_VERSION;
  sample_id: string;
  run_id: string;
  harness_operation_id: string;
  sample_index: number;
  case_ref: HarnessEvalCaseRefV1;
  repetition_index: number;
  seed: number;
  status: HarnessEvalSampleStatus;
  candidate_outcome: HarnessEvalCandidateOutcome;
  raw_schema_valid: boolean | null;
  final_schema_valid: boolean | null;
  trace_contract: HarnessContractRef | null;
  trace_digest: string | null;
  metrics: HarnessEvalMetricObservationV1[];
  grader_results: HarnessEvalGraderResultV1[];
  failures: HarnessEvalFailureV1[];
  evidence_digest: string;
  started_at: string;
  completed_at: string;
  duration_ms: number;
  sample_digest: string;
}

export interface HarnessEvalSampleRefV1 {
  sample_id: string;
  sample_index: number;
  case_ref: HarnessEvalCaseRefV1;
  sample_digest: string;
}

export interface HarnessEvalReportV1 {
  schema_name: "HarnessEvalReport";
  schema_version: typeof HARNESS_EVAL_REPORT_SCHEMA_VERSION;
  report_id: string;
  run_id: string;
  run_digest: string;
  tested_system_config_digest: string;
  status: "passed" | "failed" | "broken";
  expected_sample_count: number;
  sample_count: number;
  passed_count: number;
  failed_count: number;
  broken_count: number;
  skipped_count: number;
  sample_refs: HarnessEvalSampleRefV1[];
  raw_samples_artifact: {
    artifact_id: string;
    artifact_contract: HarnessContractRef;
    payload_digest: string;
    sample_count: number;
  } | null;
  aggregate_metrics: HarnessEvalMetricAggregateV1[];
  failure_counts: Array<{ failure_code: string; count: number }>;
  started_at: string;
  completed_at: string;
  report_digest: string;
}

export interface HarnessEvalMetricThresholdV1 {
  metric: HarnessContractRef;
  direction: "minimum" | "maximum";
  absolute_value: number;
  max_regression_ratio: number | null;
}

export interface HarnessEvalBaselineV1 {
  schema_name: "HarnessEvalBaseline";
  schema_version: typeof HARNESS_EVAL_BASELINE_SCHEMA_VERSION;
  baseline_id: string;
  baseline_version: string;
  suite: HarnessContractRef;
  suite_manifest_digest: string;
  case_set_digest: string;
  tested_system_config_digest: string;
  environment_digest: string;
  execution_mode: "fixture" | "synthetic" | "protected_replay";
  splits: HarnessEvalSplit[];
  repetition_count: number;
  seeds: number[];
  minimum_sample_count: number;
  report_contract: HarnessContractRef;
  report_id: string;
  report_digest: string;
  raw_samples_artifact: NonNullable<HarnessEvalReportV1["raw_samples_artifact"]>;
  metrics: HarnessEvalMetricAggregateV1[];
  thresholds: HarnessEvalMetricThresholdV1[];
  review_contract: HarnessContractRef;
  review_attestation_digest: string;
  baseline_digest: string;
}

export interface HarnessEvalGateMetricResultV1 {
  metric: HarnessContractRef;
  baseline_value: number;
  candidate_value: number;
  passed: boolean;
  failure_code: string | null;
}

export interface HarnessEvalGateDecisionV1 {
  schema_name: "HarnessEvalGateDecision";
  schema_version: typeof HARNESS_EVAL_GATE_DECISION_SCHEMA_VERSION;
  baseline_id: string;
  candidate_report_id: string;
  status: "passed" | "failed" | "blocked";
  comparable: boolean;
  failure_codes: string[];
  metric_results: HarnessEvalGateMetricResultV1[];
  decision_digest: string;
}

export interface HarnessEvalContractGoldenV1 {
  schema_name: "HarnessEvalContractGolden";
  schema_version: typeof HARNESS_EVAL_CONTRACT_GOLDEN_SCHEMA_VERSION;
  case: HarnessEvalCaseV1;
  run: HarnessEvalRunV1;
  sample: HarnessEvalSampleV1;
  report: HarnessEvalReportV1;
}

export class HarnessEvalDecodeError extends Error {
  readonly code = "harness_eval_decode_error";
  readonly path: string;
  readonly reason: string;

  constructor(path: string, reason: string) {
    super(`${reason} at ${path}`);
    this.name = "HarnessEvalDecodeError";
    this.path = path;
    this.reason = reason;
  }
}

const TOKEN = /^[A-Za-z0-9][A-Za-z0-9:._-]{0,159}$/;
const DIGEST = /^[0-9a-f]{64}$/;
const RUN_ID = /^harness-eval-run-[0-9a-f]{32}$/;
const SAMPLE_ID = /^harness-eval-sample-[0-9a-f]{32}$/;
const REPORT_ID = /^harness-eval-report-[0-9a-f]{32}$/;
const UTC_TIMESTAMP = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z$/;

function deepFreeze<T>(value: T): Readonly<T> {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const child of Object.values(value as Record<string, unknown>)) deepFreeze(child);
    Object.freeze(value);
  }
  return value;
}

function record(raw: unknown, path: string, keys: readonly string[]): Record<string, unknown> {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) fail(path, "expected_object");
  const value = raw as Record<string, unknown>;
  const actual = Object.keys(value).sort();
  const expected = [...keys].sort();
  if (actual.length !== expected.length || actual.some((key, index) => key !== expected[index])) {
    fail(path, "unexpected_or_missing_fields");
  }
  return value;
}

function fail(path: string, reason: string): never {
  throw new HarnessEvalDecodeError(path, reason);
}

function field(value: Record<string, unknown>, key: string): unknown {
  return value[key];
}

function string(raw: unknown, path: string, pattern?: RegExp): string {
  if (typeof raw !== "string" || raw.length === 0 || (pattern && !pattern.test(raw))) {
    fail(path, "expected_bounded_string");
  }
  return raw;
}

function literal<T extends string>(raw: unknown, expected: T, path: string): T {
  if (raw !== expected) fail(path, `expected_${expected}`);
  return expected;
}

function enumeration<T extends string>(raw: unknown, values: readonly T[], path: string): T {
  if (typeof raw !== "string" || !values.includes(raw as T)) fail(path, "unexpected_enum");
  return raw as T;
}

function integer(raw: unknown, path: string, minimum = 0, maximum = Number.MAX_SAFE_INTEGER): number {
  if (!Number.isSafeInteger(raw) || (raw as number) < minimum || (raw as number) > maximum) {
    fail(path, "expected_safe_integer");
  }
  return raw as number;
}

function number(raw: unknown, path: string, minimum = 0, maximum = Number.MAX_VALUE): number {
  if (typeof raw !== "number" || !Number.isFinite(raw) || raw < minimum || raw > maximum) {
    fail(path, "expected_finite_number");
  }
  return raw;
}

function boolean(raw: unknown, path: string): boolean {
  if (typeof raw !== "boolean") fail(path, "expected_boolean");
  return raw;
}

function nullable<T>(raw: unknown, path: string, decode: (value: unknown, path: string) => T): T | null {
  return raw === null ? null : decode(raw, path);
}

function array<T>(
  raw: unknown,
  path: string,
  decode: (value: unknown, path: string) => T,
  minimum = 0,
  maximum = Number.MAX_SAFE_INTEGER,
): T[] {
  if (!Array.isArray(raw) || raw.length < minimum || raw.length > maximum) fail(path, "expected_bounded_array");
  return raw.map((item, index) => decode(item, `${path}[${index}]`));
}

function assertSortedUnique(values: string[], path: string): void {
  if (new Set(values).size !== values.length || values.some((item, index) => index > 0 && item < values[index - 1]!)) {
    fail(path, "expected_sorted_unique_values");
  }
}

function digest(raw: unknown, path: string): string {
  return string(raw, path, DIGEST);
}

function timestamp(raw: unknown, path: string): string {
  const value = string(raw, path, UTC_TIMESTAMP);
  const parsed = new Date(value);
  const parts = /^([0-9]{4})-([0-9]{2})-([0-9]{2})T([0-9]{2}):([0-9]{2}):([0-9]{2})/.exec(value);
  if (!parts || !Number.isFinite(parsed.getTime())
    || parsed.getUTCFullYear() !== Number(parts[1])
    || parsed.getUTCMonth() + 1 !== Number(parts[2])
    || parsed.getUTCDate() !== Number(parts[3])
    || parsed.getUTCHours() !== Number(parts[4])
    || parsed.getUTCMinutes() !== Number(parts[5])
    || parsed.getUTCSeconds() !== Number(parts[6])) {
    fail(path, "invalid_utc_timestamp");
  }
  return value;
}

function contract(raw: unknown, path: string): HarnessContractRef {
  const value = record(raw, path, ["name", "version"]);
  const result = {
    name: string(field(value, "name"), `${path}.name`, TOKEN),
    version: string(field(value, "version"), `${path}.version`, TOKEN),
  };
  if (["latest", "unknown", "none"].includes(result.version.toLowerCase()) || result.version.toLowerCase().startsWith("pending-")) {
    fail(`${path}.version`, "placeholder_version_forbidden");
  }
  return result;
}

function nullableContract(raw: unknown, path: string): HarnessContractRef | null {
  return nullable(raw, path, contract);
}

function contractIdentity(value: HarnessContractRef): string {
  return `${value.name}\u0000${value.version}`;
}

function decodeCaseRef(raw: unknown, path: string): HarnessEvalCaseRefV1 {
  const value = record(raw, path, ["suite", "case_id", "case_version", "case_digest"]);
  return {
    suite: contract(field(value, "suite"), `${path}.suite`),
    case_id: string(field(value, "case_id"), `${path}.case_id`, TOKEN),
    case_version: string(field(value, "case_version"), `${path}.case_version`, TOKEN),
    case_digest: digest(field(value, "case_digest"), `${path}.case_digest`),
  };
}

function decodeSource(raw: unknown, path: string): HarnessEvalSourceV1 {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) fail(path, "expected_object");
  const mode = (raw as Record<string, unknown>).source_mode;
  if (mode === "fixture") {
    const value = record(raw, path, ["source_mode", "fixture_id", "payload_contract", "payload_digest"]);
    return {
      source_mode: "fixture",
      fixture_id: string(field(value, "fixture_id"), `${path}.fixture_id`, TOKEN),
      payload_contract: contract(field(value, "payload_contract"), `${path}.payload_contract`),
      payload_digest: digest(field(value, "payload_digest"), `${path}.payload_digest`),
    };
  }
  if (mode === "synthetic") {
    const value = record(raw, path, ["source_mode", "generator_contract", "seed", "manifest_digest"]);
    return {
      source_mode: "synthetic",
      generator_contract: contract(field(value, "generator_contract"), `${path}.generator_contract`),
      seed: integer(field(value, "seed"), `${path}.seed`),
      manifest_digest: digest(field(value, "manifest_digest"), `${path}.manifest_digest`),
    };
  }
  if (mode === "protected_artifact") {
    const value = record(raw, path, ["source_mode", "artifact_type", "artifact_id", "artifact_contract", "payload_digest"]);
    return {
      source_mode: "protected_artifact",
      artifact_type: string(field(value, "artifact_type"), `${path}.artifact_type`, TOKEN),
      artifact_id: string(field(value, "artifact_id"), `${path}.artifact_id`, TOKEN),
      artifact_contract: contract(field(value, "artifact_contract"), `${path}.artifact_contract`),
      payload_digest: digest(field(value, "payload_digest"), `${path}.payload_digest`),
    };
  }
  return fail(`${path}.source_mode`, "unknown_source_mode");
}

function decodeProvenance(raw: unknown, path: string): HarnessEvalProvenanceV1 {
  const value = record(raw, path, ["source_kind", "review_status", "review_contract", "attestation_digest"]);
  const result: HarnessEvalProvenanceV1 = {
    source_kind: enumeration(field(value, "source_kind"), ["developer_authored", "independently_reviewed", "synthetic", "production_derived", "imported"] as const, `${path}.source_kind`),
    review_status: enumeration(field(value, "review_status"), ["unreviewed", "developer_reviewed", "independently_reviewed"] as const, `${path}.review_status`),
    review_contract: nullableContract(field(value, "review_contract"), `${path}.review_contract`),
    attestation_digest: nullable(field(value, "attestation_digest"), `${path}.attestation_digest`, digest),
  };
  const hasEvidence = result.review_contract !== null && result.attestation_digest !== null;
  if ((result.review_status === "independently_reviewed") !== hasEvidence) fail(path, "independent_review_evidence_mismatch");
  if (result.review_status !== "independently_reviewed" && (result.review_contract !== null || result.attestation_digest !== null)) fail(path, "review_evidence_forbidden");
  return result;
}

export function decodeHarnessEvalCase(raw: unknown, path = "eval_case"): HarnessEvalCaseV1 {
  const value = record(raw, path, ["schema_name", "schema_version", "case_id", "case_version", "case_digest", "suite", "workflow", "stage", "eval_route", "source", "provenance", "sensitivity", "split", "tags", "expected_invariants", "grader_refs"]);
  literal(field(value, "schema_name"), "HarnessEvalCase", `${path}.schema_name`);
  literal(field(value, "schema_version"), HARNESS_EVAL_CASE_SCHEMA_VERSION, `${path}.schema_version`);
  const workflow = enumeration(field(value, "workflow"), ["document_parse", "ocr", "study_unit_cleanup", "planning", "persona", "scene", "study_chat", "tavern", "frontend_decode"] as const, `${path}.workflow`);
  const stage = enumeration(field(value, "stage"), ["document_parse", "page_extraction", "section_detection", "chunk_building", "ocr_page", "study_unit_cleanup", "plan_generation", "planning_tool_execution", "persona_generation", "scene_generation", "study_chat_reply", "actor_reply", "response_decode"] as const, `${path}.stage`);
  const evalRoute = string(field(value, "eval_route"), `${path}.eval_route`);
  const registration = HARNESS_OPERATION_STAGE_REGISTRATIONS[`${workflow}:${stage}` as HarnessOperationStageKey];
  if (!registration || registration.evalRoute !== evalRoute) fail(`${path}.eval_route`, "route_mismatch");
  const source = decodeSource(field(value, "source"), `${path}.source`);
  const provenance = decodeProvenance(field(value, "provenance"), `${path}.provenance`);
  const sensitivity = enumeration(field(value, "sensitivity"), ["public", "internal", "protected"] as const, `${path}.sensitivity`);
  if ((sensitivity === "protected") !== (source.source_mode === "protected_artifact")) fail(path, "sensitivity_source_mismatch");
  if (source.source_mode === "synthetic" && provenance.source_kind !== "synthetic") fail(path, "synthetic_provenance_required");
  const split = enumeration(field(value, "split"), ["development", "validation", "held_out", "calibration", "regression"] as const, `${path}.split`);
  if (["held_out", "calibration"].includes(split) && provenance.review_status !== "independently_reviewed") fail(path, "independent_review_required");
  const tags = array(field(value, "tags"), `${path}.tags`, (item, itemPath) => string(item, itemPath, TOKEN), 0, 64);
  assertSortedUnique(tags, `${path}.tags`);
  const expectedInvariants = array(field(value, "expected_invariants"), `${path}.expected_invariants`, (item, itemPath) => {
    const entry = record(item, itemPath, ["invariant", "expected_outcome"]);
    return {
      invariant: contract(field(entry, "invariant"), `${itemPath}.invariant`),
      expected_outcome: enumeration(field(entry, "expected_outcome"), ["passed", "failed", "not_applicable"] as const, `${itemPath}.expected_outcome`),
    };
  }, 0, 64);
  const invariantIds = expectedInvariants.map((item) => contractIdentity(item.invariant));
  assertSortedUnique(invariantIds, `${path}.expected_invariants`);
  const graderRefs = array(field(value, "grader_refs"), `${path}.grader_refs`, contract, 0, 32);
  assertSortedUnique(graderRefs.map(contractIdentity), `${path}.grader_refs`);
  if (!expectedInvariants.length && !graderRefs.length) fail(path, "expectation_missing");
  return {
    schema_name: "HarnessEvalCase",
    schema_version: HARNESS_EVAL_CASE_SCHEMA_VERSION,
    case_id: string(field(value, "case_id"), `${path}.case_id`, TOKEN),
    case_version: string(field(value, "case_version"), `${path}.case_version`, TOKEN),
    case_digest: digest(field(value, "case_digest"), `${path}.case_digest`),
    suite: contract(field(value, "suite"), `${path}.suite`),
    workflow,
    stage,
    eval_route: evalRoute,
    source,
    provenance,
    sensitivity,
    split,
    tags,
    expected_invariants: expectedInvariants,
    grader_refs: graderRefs,
  };
}

function decodeReasoning(raw: unknown, path: string): HarnessEvalSystemConfigV1["reasoning"] {
  const value = record(raw, path, ["mode", "budget_tokens"]);
  const result = {
    mode: enumeration(field(value, "mode"), ["not_supported", "disabled", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"] as const, `${path}.mode`),
    budget_tokens: nullable(field(value, "budget_tokens"), `${path}.budget_tokens`, (item, itemPath) => integer(item, itemPath, 1, 10_000_000)),
  };
  if (["not_supported", "disabled"].includes(result.mode) && result.budget_tokens !== null) fail(path, "reasoning_budget_forbidden");
  return result;
}

function decodeSampling(raw: unknown, path: string): HarnessEvalSystemConfigV1["sampling"] {
  const value = record(raw, path, ["temperature", "top_p", "seed_strategy", "fixed_seed"]);
  const result = {
    temperature: nullable(field(value, "temperature"), `${path}.temperature`, (item, itemPath) => number(item, itemPath, 0, 2)),
    top_p: nullable(field(value, "top_p"), `${path}.top_p`, (item, itemPath) => number(item, itemPath, Number.MIN_VALUE, 1)),
    seed_strategy: enumeration(field(value, "seed_strategy"), ["provider_unsupported", "per_sample", "fixed"] as const, `${path}.seed_strategy`),
    fixed_seed: nullable(field(value, "fixed_seed"), `${path}.fixed_seed`, integer),
  };
  if ((result.seed_strategy === "fixed") !== (result.fixed_seed !== null)) fail(path, "fixed_seed_mismatch");
  return result;
}

function decodeBudgets(raw: unknown, path: string): HarnessEvalSystemConfigV1["budgets"] {
  const keys = ["max_attempts", "max_repairs", "max_tool_calls", "max_provider_calls", "max_input_tokens", "max_output_tokens", "max_wall_time_ms", "per_call_timeout_ms", "max_cost_micro_usd"] as const;
  const value = record(raw, path, keys);
  const result = {
    max_attempts: integer(field(value, "max_attempts"), `${path}.max_attempts`, 1, 128),
    max_repairs: integer(field(value, "max_repairs"), `${path}.max_repairs`, 0, 32),
    max_tool_calls: integer(field(value, "max_tool_calls"), `${path}.max_tool_calls`, 0, 10_000),
    max_provider_calls: integer(field(value, "max_provider_calls"), `${path}.max_provider_calls`, 0, 10_000),
    max_input_tokens: integer(field(value, "max_input_tokens"), `${path}.max_input_tokens`, 0, 100_000_000),
    max_output_tokens: integer(field(value, "max_output_tokens"), `${path}.max_output_tokens`, 0, 100_000_000),
    max_wall_time_ms: integer(field(value, "max_wall_time_ms"), `${path}.max_wall_time_ms`, 1, 86_400_000),
    per_call_timeout_ms: integer(field(value, "per_call_timeout_ms"), `${path}.per_call_timeout_ms`, 1, 86_400_000),
    max_cost_micro_usd: integer(field(value, "max_cost_micro_usd"), `${path}.max_cost_micro_usd`, 0, 10_000_000_000),
  };
  if (result.max_repairs >= result.max_attempts) fail(path, "repair_budget_exceeds_attempts");
  if (result.per_call_timeout_ms > result.max_wall_time_ms) fail(path, "call_timeout_exceeds_wall_time");
  return result;
}

function decodeSystemConfig(raw: unknown, path: string): HarnessEvalSystemConfigV1 {
  const keys = ["schema_name", "schema_version", "workflow_manifest_contract", "harness_contract", "provider_adapter_contract", "provider_model_contract", "input_contract", "output_contract", "prompt_contract", "policy_contract", "toolset_contract", "component_contracts", "reasoning", "sampling", "budgets", "source_revision", "worktree_state", "source_tree_digest"] as const;
  const value = record(raw, path, keys);
  literal(field(value, "schema_name"), "HarnessEvalSystemConfig", `${path}.schema_name`);
  literal(field(value, "schema_version"), HARNESS_EVAL_SYSTEM_CONFIG_SCHEMA_VERSION, `${path}.schema_version`);
  const componentContracts = array(field(value, "component_contracts"), `${path}.component_contracts`, contract, 1, 64);
  assertSortedUnique(componentContracts.map(contractIdentity), `${path}.component_contracts`);
  const worktreeState = enumeration(field(value, "worktree_state"), ["clean", "dirty"] as const, `${path}.worktree_state`);
  const sourceTreeDigest = nullable(field(value, "source_tree_digest"), `${path}.source_tree_digest`, digest);
  if ((worktreeState === "dirty") !== (sourceTreeDigest !== null)) fail(path, "source_tree_digest_mismatch");
  return {
    schema_name: "HarnessEvalSystemConfig",
    schema_version: HARNESS_EVAL_SYSTEM_CONFIG_SCHEMA_VERSION,
    workflow_manifest_contract: contract(field(value, "workflow_manifest_contract"), `${path}.workflow_manifest_contract`),
    harness_contract: contract(field(value, "harness_contract"), `${path}.harness_contract`),
    provider_adapter_contract: contract(field(value, "provider_adapter_contract"), `${path}.provider_adapter_contract`),
    provider_model_contract: contract(field(value, "provider_model_contract"), `${path}.provider_model_contract`),
    input_contract: contract(field(value, "input_contract"), `${path}.input_contract`),
    output_contract: contract(field(value, "output_contract"), `${path}.output_contract`),
    prompt_contract: nullableContract(field(value, "prompt_contract"), `${path}.prompt_contract`),
    policy_contract: nullableContract(field(value, "policy_contract"), `${path}.policy_contract`),
    toolset_contract: nullableContract(field(value, "toolset_contract"), `${path}.toolset_contract`),
    component_contracts: componentContracts,
    reasoning: decodeReasoning(field(value, "reasoning"), `${path}.reasoning`),
    sampling: decodeSampling(field(value, "sampling"), `${path}.sampling`),
    budgets: decodeBudgets(field(value, "budgets"), `${path}.budgets`),
    source_revision: string(field(value, "source_revision"), `${path}.source_revision`, TOKEN),
    worktree_state: worktreeState,
    source_tree_digest: sourceTreeDigest,
  };
}

function decodeEnvironment(raw: unknown, path: string): HarnessEvalEnvironmentV1 {
  const value = record(raw, path, ["schema_name", "schema_version", "environment_contract", "platform", "architecture", "python_version", "node_version", "database_kind", "provider_mode"]);
  literal(field(value, "schema_name"), "HarnessEvalEnvironment", `${path}.schema_name`);
  literal(field(value, "schema_version"), HARNESS_EVAL_ENVIRONMENT_SCHEMA_VERSION, `${path}.schema_version`);
  return {
    schema_name: "HarnessEvalEnvironment",
    schema_version: HARNESS_EVAL_ENVIRONMENT_SCHEMA_VERSION,
    environment_contract: contract(field(value, "environment_contract"), `${path}.environment_contract`),
    platform: string(field(value, "platform"), `${path}.platform`, TOKEN),
    architecture: string(field(value, "architecture"), `${path}.architecture`, TOKEN),
    python_version: string(field(value, "python_version"), `${path}.python_version`, TOKEN),
    node_version: nullable(field(value, "node_version"), `${path}.node_version`, (item, itemPath) => string(item, itemPath, TOKEN)),
    database_kind: enumeration(field(value, "database_kind"), ["none", "sqlite", "postgresql"] as const, `${path}.database_kind`),
    provider_mode: enumeration(field(value, "provider_mode"), ["mock", "local", "live"] as const, `${path}.provider_mode`),
  };
}

export function decodeHarnessEvalRun(raw: unknown, path = "eval_run"): HarnessEvalRunV1 {
  const keys = ["schema_name", "schema_version", "run_id", "suite", "suite_manifest_digest", "case_set_digest", "execution_mode", "splits", "repetition_count", "seeds", "runner_contract", "failure_taxonomy_contract", "grader_registry_contract", "tested_system", "tested_system_config_digest", "environment", "environment_digest", "admitted_at", "run_digest"] as const;
  const value = record(raw, path, keys);
  literal(field(value, "schema_name"), "HarnessEvalRun", `${path}.schema_name`);
  literal(field(value, "schema_version"), HARNESS_EVAL_RUN_SCHEMA_VERSION, `${path}.schema_version`);
  const splits = array(field(value, "splits"), `${path}.splits`, (item, itemPath) => enumeration(item, ["development", "validation", "held_out", "calibration", "regression"] as const, itemPath), 1, 8);
  assertSortedUnique(splits, `${path}.splits`);
  const repetitionCount = integer(field(value, "repetition_count"), `${path}.repetition_count`, 1, 1_000);
  const seeds = array(field(value, "seeds"), `${path}.seeds`, integer, 1, 1_000);
  if (seeds.length !== repetitionCount || new Set(seeds).size !== seeds.length) fail(`${path}.seeds`, "seed_count_or_identity_mismatch");
  const taxonomy = contract(field(value, "failure_taxonomy_contract"), `${path}.failure_taxonomy_contract`);
  if (taxonomy.name !== "HarnessEvalFailureTaxonomy" || taxonomy.version !== HARNESS_EVAL_FAILURE_TAXONOMY_SCHEMA_VERSION) fail(`${path}.failure_taxonomy_contract`, "taxonomy_contract_mismatch");
  const environment = decodeEnvironment(field(value, "environment"), `${path}.environment`);
  const executionMode = enumeration(field(value, "execution_mode"), ["fixture", "synthetic", "protected_replay"] as const, `${path}.execution_mode`);
  if (executionMode === "protected_replay" && environment.provider_mode === "mock") fail(path, "protected_replay_mock_provider_forbidden");
  return {
    schema_name: "HarnessEvalRun",
    schema_version: HARNESS_EVAL_RUN_SCHEMA_VERSION,
    run_id: string(field(value, "run_id"), `${path}.run_id`, RUN_ID),
    suite: contract(field(value, "suite"), `${path}.suite`),
    suite_manifest_digest: digest(field(value, "suite_manifest_digest"), `${path}.suite_manifest_digest`),
    case_set_digest: digest(field(value, "case_set_digest"), `${path}.case_set_digest`),
    execution_mode: executionMode,
    splits,
    repetition_count: repetitionCount,
    seeds,
    runner_contract: contract(field(value, "runner_contract"), `${path}.runner_contract`),
    failure_taxonomy_contract: taxonomy,
    grader_registry_contract: contract(field(value, "grader_registry_contract"), `${path}.grader_registry_contract`),
    tested_system: decodeSystemConfig(field(value, "tested_system"), `${path}.tested_system`),
    tested_system_config_digest: digest(field(value, "tested_system_config_digest"), `${path}.tested_system_config_digest`),
    environment,
    environment_digest: digest(field(value, "environment_digest"), `${path}.environment_digest`),
    admitted_at: timestamp(field(value, "admitted_at"), `${path}.admitted_at`),
    run_digest: digest(field(value, "run_digest"), `${path}.run_digest`),
  };
}

function decodeMetric(raw: unknown, path: string): HarnessEvalMetricObservationV1 {
  if (!raw || typeof raw !== "object" || Array.isArray(raw)) fail(path, "expected_object");
  const valueType = (raw as Record<string, unknown>).value_type;
  const value = record(raw, path, ["schema_name", "schema_version", "metric", "value_type", "unit", "value", "evidence_digest"]);
  literal(field(value, "schema_name"), "HarnessEvalMetric", `${path}.schema_name`);
  literal(field(value, "schema_version"), HARNESS_EVAL_METRIC_SCHEMA_VERSION, `${path}.schema_version`);
  const common = {
    schema_name: "HarnessEvalMetric" as const,
    schema_version: HARNESS_EVAL_METRIC_SCHEMA_VERSION,
    metric: contract(field(value, "metric"), `${path}.metric`),
    evidence_digest: digest(field(value, "evidence_digest"), `${path}.evidence_digest`),
  };
  if (valueType === "boolean") return { ...common, value_type: "boolean", unit: literal(field(value, "unit"), "boolean", `${path}.unit`), value: boolean(field(value, "value"), `${path}.value`) };
  if (valueType === "integer") return { ...common, value_type: "integer", unit: enumeration(field(value, "unit"), ["count", "milliseconds", "bytes", "tokens", "tool_calls", "provider_calls", "micro_usd"] as const, `${path}.unit`), value: integer(field(value, "value"), `${path}.value`) };
  if (valueType === "number") return { ...common, value_type: "number", unit: enumeration(field(value, "unit"), ["ratio", "score"] as const, `${path}.unit`), value: number(field(value, "value"), `${path}.value`, 0, 1) };
  return fail(`${path}.value_type`, "unknown_metric_value_type");
}

function decodeMetricAggregate(raw: unknown, path: string): HarnessEvalMetricAggregateV1 {
  const value = record(raw, path, ["schema_name", "schema_version", "metric", "aggregation", "unit", "value", "population_count", "excluded_count", "numerator", "denominator", "percentile_method"]);
  literal(field(value, "schema_name"), "HarnessEvalMetricAggregate", `${path}.schema_name`);
  literal(field(value, "schema_version"), HARNESS_EVAL_METRIC_SCHEMA_VERSION, `${path}.schema_version`);
  const aggregation = enumeration(field(value, "aggregation"), ["count", "sum", "mean", "min", "max", "rate", "p50", "p95"] as const, `${path}.aggregation`);
  const unit = enumeration(field(value, "unit"), ["boolean", "ratio", "score", "count", "milliseconds", "bytes", "tokens", "tool_calls", "provider_calls", "micro_usd"] as const, `${path}.unit`);
  const result: HarnessEvalMetricAggregateV1 = {
    schema_name: "HarnessEvalMetricAggregate",
    schema_version: HARNESS_EVAL_METRIC_SCHEMA_VERSION,
    metric: contract(field(value, "metric"), `${path}.metric`),
    aggregation,
    unit,
    value: number(field(value, "value"), `${path}.value`, 0),
    population_count: integer(field(value, "population_count"), `${path}.population_count`, 1, 10_000_000),
    excluded_count: integer(field(value, "excluded_count"), `${path}.excluded_count`, 0, 10_000_000),
    numerator: nullable(field(value, "numerator"), `${path}.numerator`, integer),
    denominator: nullable(field(value, "denominator"), `${path}.denominator`, (item, itemPath) => integer(item, itemPath, 1)),
    percentile_method: nullable(field(value, "percentile_method"), `${path}.percentile_method`, (item, itemPath) => literal(item, "nearest_rank", itemPath)),
  };
  const isRate = aggregation === "rate";
  if (isRate !== (result.numerator !== null && result.denominator !== null)) fail(path, "rate_evidence_mismatch");
  if (isRate && (unit !== "ratio" || result.numerator! > result.denominator! || Math.abs(result.value - result.numerator! / result.denominator!) > 1e-12)) fail(path, "rate_value_invalid");
  const isPercentile = aggregation === "p50" || aggregation === "p95";
  if (isPercentile !== (result.percentile_method !== null)) fail(path, "percentile_method_mismatch");
  if (unit === "boolean") fail(path, "boolean_aggregate_forbidden");
  return result;
}

function decodeGraderResult(raw: unknown, path: string): HarnessEvalGraderResultV1 {
  const value = record(raw, path, ["schema_name", "schema_version", "grader_result_id", "grader", "grader_kind", "grader_config_digest", "execution_status", "verdict", "score", "metrics", "failure_codes", "evidence_digest", "duration_ms"]);
  literal(field(value, "schema_name"), "HarnessEvalGraderResult", `${path}.schema_name`);
  literal(field(value, "schema_version"), HARNESS_EVAL_GRADER_RESULT_SCHEMA_VERSION, `${path}.schema_version`);
  const executionStatus = enumeration(field(value, "execution_status"), ["completed", "error", "skipped"] as const, `${path}.execution_status`);
  const verdict = nullable(field(value, "verdict"), `${path}.verdict`, (item, itemPath) => enumeration(item, ["passed", "failed", "not_applicable"] as const, itemPath));
  const score = nullable(field(value, "score"), `${path}.score`, (item, itemPath) => number(item, itemPath, 0, 1));
  const metrics = array(field(value, "metrics"), `${path}.metrics`, decodeMetric, 0, 128);
  assertSortedUnique(metrics.map((item) => contractIdentity(item.metric)), `${path}.metrics`);
  const failureCodes = array(field(value, "failure_codes"), `${path}.failure_codes`, (item, itemPath) => string(item, itemPath, TOKEN), 0, 32);
  assertSortedUnique(failureCodes, `${path}.failure_codes`);
  const evidenceDigest = nullable(field(value, "evidence_digest"), `${path}.evidence_digest`, digest);
  if (executionStatus === "completed" && (verdict === null || failureCodes.length > 0 || evidenceDigest === null)) fail(path, "completed_grader_invalid");
  if (executionStatus === "error" && (verdict !== null || score !== null || failureCodes.length === 0)) fail(path, "failed_grader_invalid");
  if (executionStatus === "skipped" && (verdict !== null || score !== null || metrics.length > 0)) fail(path, "skipped_grader_invalid");
  return {
    schema_name: "HarnessEvalGraderResult",
    schema_version: HARNESS_EVAL_GRADER_RESULT_SCHEMA_VERSION,
    grader_result_id: string(field(value, "grader_result_id"), `${path}.grader_result_id`, TOKEN),
    grader: contract(field(value, "grader"), `${path}.grader`),
    grader_kind: enumeration(field(value, "grader_kind"), ["deterministic", "model", "human"] as const, `${path}.grader_kind`),
    grader_config_digest: digest(field(value, "grader_config_digest"), `${path}.grader_config_digest`),
    execution_status: executionStatus,
    verdict,
    score,
    metrics,
    failure_codes: failureCodes,
    evidence_digest: evidenceDigest,
    duration_ms: integer(field(value, "duration_ms"), `${path}.duration_ms`, 0, 86_400_000),
  };
}

const FAILURE_ENTRIES = [
  ["candidate_commit_failed", "candidate", "commit", "candidate_failure", false, true, ["failed"]],
  ["candidate_decode_failed", "candidate", "decode", "candidate_failure", false, true, ["failed", "passed"]],
  ["candidate_effect_uncertain", "candidate", "effect", "candidate_failure", false, true, ["failed"]],
  ["candidate_execution_failed", "candidate", "execution", "candidate_failure", false, true, ["failed", "passed"]],
  ["candidate_recovery_exhausted", "candidate", "recovery", "candidate_failure", false, true, ["failed"]],
  ["candidate_validation_failed", "candidate", "validation", "candidate_failure", false, true, ["failed", "passed"]],
  ["case_contract_invalid", "case", "contract", "data_failure", false, false, ["broken"]],
  ["case_source_unresolved", "case", "resolution", "data_failure", true, false, ["broken"]],
  ["eval_route_unregistered", "runner", "configuration", "infrastructure_failure", false, false, ["broken"]],
  ["grader_execution_failed", "grader", "grading", "infrastructure_failure", true, false, ["broken"]],
  ["grader_output_invalid", "grader", "grading", "infrastructure_failure", false, false, ["broken"]],
  ["metric_computation_failed", "metric", "measurement", "infrastructure_failure", false, false, ["broken"]],
  ["protected_artifact_forbidden", "case", "resolution", "data_failure", false, false, ["broken"]],
  ["runner_configuration_invalid", "runner", "configuration", "incomparable", false, false, ["broken"]],
  ["runner_execution_failed", "runner", "execution", "infrastructure_failure", true, false, ["broken"]],
  ["sensitive_material_detected", "runner", "sensitivity", "infrastructure_failure", false, false, ["broken"]],
] as const;

export const HARNESS_EVAL_FAILURE_TAXONOMY = deepFreeze(Object.fromEntries(
  FAILURE_ENTRIES.map(([code, owner, category, releaseClass, retryable, candidate, statuses]) => [code, {
    code,
    owner,
    category,
    release_class: releaseClass,
    retryable,
    counts_as_candidate_failure: candidate,
    allowed_sample_statuses: [...statuses],
  }]),
) as Record<string, HarnessEvalFailureTaxonomyEntryV1>);

export function harnessEvalFailureTaxonomyRegistrySnapshot(): HarnessEvalFailureTaxonomyRegistryV1 {
  return {
    schema_name: "HarnessEvalFailureTaxonomy",
    schema_version: HARNESS_EVAL_FAILURE_TAXONOMY_SCHEMA_VERSION,
    entries: Object.keys(HARNESS_EVAL_FAILURE_TAXONOMY).sort().map((code) => ({
      ...HARNESS_EVAL_FAILURE_TAXONOMY[code]!,
      allowed_sample_statuses: [...HARNESS_EVAL_FAILURE_TAXONOMY[code]!.allowed_sample_statuses],
    })),
  };
}

export function decodeHarnessEvalFailureTaxonomy(raw: unknown, path = "eval_failure_taxonomy"): HarnessEvalFailureTaxonomyRegistryV1 {
  const value = record(raw, path, ["schema_name", "schema_version", "entries"]);
  literal(field(value, "schema_name"), "HarnessEvalFailureTaxonomy", `${path}.schema_name`);
  literal(field(value, "schema_version"), HARNESS_EVAL_FAILURE_TAXONOMY_SCHEMA_VERSION, `${path}.schema_version`);
  const entries = array(field(value, "entries"), `${path}.entries`, (item, itemPath) => {
    const entry = record(item, itemPath, ["code", "owner", "category", "release_class", "retryable", "counts_as_candidate_failure", "allowed_sample_statuses"]);
    const result: HarnessEvalFailureTaxonomyEntryV1 = {
      code: string(field(entry, "code"), `${itemPath}.code`, TOKEN),
      owner: enumeration(field(entry, "owner"), ["case", "runner", "candidate", "grader", "metric"] as const, `${itemPath}.owner`),
      category: enumeration(field(entry, "category"), ["contract", "resolution", "configuration", "execution", "decode", "validation", "recovery", "commit", "effect", "grading", "measurement", "sensitivity"] as const, `${itemPath}.category`),
      release_class: enumeration(field(entry, "release_class"), ["candidate_failure", "infrastructure_failure", "data_failure", "incomparable"] as const, `${itemPath}.release_class`),
      retryable: boolean(field(entry, "retryable"), `${itemPath}.retryable`),
      counts_as_candidate_failure: boolean(field(entry, "counts_as_candidate_failure"), `${itemPath}.counts_as_candidate_failure`),
      allowed_sample_statuses: array(field(entry, "allowed_sample_statuses"), `${itemPath}.allowed_sample_statuses`, (status, statusPath) => enumeration(status, ["passed", "failed", "broken", "skipped"] as const, statusPath), 1, 4),
    };
    assertSortedUnique(result.allowed_sample_statuses, `${itemPath}.allowed_sample_statuses`);
    if (result.counts_as_candidate_failure !== (result.owner === "candidate")) fail(itemPath, "candidate_blame_mismatch");
    if ((result.owner === "candidate") !== (result.release_class === "candidate_failure")) fail(itemPath, "candidate_release_class_mismatch");
    return result;
  }, 1, 256);
  assertSortedUnique(entries.map((entry) => entry.code), `${path}.entries`);
  return { schema_name: "HarnessEvalFailureTaxonomy", schema_version: HARNESS_EVAL_FAILURE_TAXONOMY_SCHEMA_VERSION, entries };
}

function decodeFailure(raw: unknown, path: string): HarnessEvalFailureV1 {
  const value = record(raw, path, ["schema_name", "schema_version", "failure_code", "owner", "reason_code", "evidence_digest"]);
  literal(field(value, "schema_name"), "HarnessEvalFailure", `${path}.schema_name`);
  literal(field(value, "schema_version"), HARNESS_EVAL_FAILURE_SCHEMA_VERSION, `${path}.schema_version`);
  const failureCode = string(field(value, "failure_code"), `${path}.failure_code`, TOKEN);
  const owner = enumeration(field(value, "owner"), ["case", "runner", "candidate", "grader", "metric"] as const, `${path}.owner`);
  const taxonomy = HARNESS_EVAL_FAILURE_TAXONOMY[failureCode];
  if (!taxonomy) fail(`${path}.failure_code`, "unregistered_failure_code");
  if (taxonomy.owner !== owner) fail(`${path}.owner`, "failure_owner_mismatch");
  return {
    schema_name: "HarnessEvalFailure",
    schema_version: HARNESS_EVAL_FAILURE_SCHEMA_VERSION,
    failure_code: failureCode,
    owner,
    reason_code: string(field(value, "reason_code"), `${path}.reason_code`, TOKEN),
    evidence_digest: nullable(field(value, "evidence_digest"), `${path}.evidence_digest`, digest),
  };
}

export function decodeHarnessEvalSample(raw: unknown, path = "eval_sample"): HarnessEvalSampleV1 {
  const keys = ["schema_name", "schema_version", "sample_id", "run_id", "harness_operation_id", "sample_index", "case_ref", "repetition_index", "seed", "status", "candidate_outcome", "raw_schema_valid", "final_schema_valid", "trace_contract", "trace_digest", "metrics", "grader_results", "failures", "evidence_digest", "started_at", "completed_at", "duration_ms", "sample_digest"] as const;
  const value = record(raw, path, keys);
  literal(field(value, "schema_name"), "HarnessEvalSample", `${path}.schema_name`);
  literal(field(value, "schema_version"), HARNESS_EVAL_SAMPLE_SCHEMA_VERSION, `${path}.schema_version`);
  const status = enumeration(field(value, "status"), ["passed", "failed", "broken", "skipped"] as const, `${path}.status`);
  const candidateOutcome = enumeration(field(value, "candidate_outcome"), ["passed", "repaired", "failed", "skipped", "unavailable"] as const, `${path}.candidate_outcome`);
  const rawSchemaValid = nullable(field(value, "raw_schema_valid"), `${path}.raw_schema_valid`, boolean);
  const finalSchemaValid = nullable(field(value, "final_schema_valid"), `${path}.final_schema_valid`, boolean);
  const traceContract = nullableContract(field(value, "trace_contract"), `${path}.trace_contract`);
  const traceDigest = nullable(field(value, "trace_digest"), `${path}.trace_digest`, digest);
  if ((traceContract === null) !== (traceDigest === null)) fail(path, "trace_evidence_incomplete");
  const metrics = array(field(value, "metrics"), `${path}.metrics`, decodeMetric, 0, 256);
  assertSortedUnique(metrics.map((item) => contractIdentity(item.metric)), `${path}.metrics`);
  const graderResults = array(field(value, "grader_results"), `${path}.grader_results`, decodeGraderResult, 0, 64);
  assertSortedUnique(graderResults.map((item) => contractIdentity(item.grader)), `${path}.grader_results`);
  const failures = array(field(value, "failures"), `${path}.failures`, decodeFailure, 0, 64);
  assertSortedUnique(failures.map((item) => item.failure_code), `${path}.failures`);
  for (const failure of failures) {
    if (!HARNESS_EVAL_FAILURE_TAXONOMY[failure.failure_code]!.allowed_sample_statuses.includes(status)) fail(path, "failure_status_mismatch");
  }
  const graderError = graderResults.some((item) => item.execution_status === "error");
  const infrastructureFailure = failures.some((item) => item.owner !== "candidate");
  if ((graderError || infrastructureFailure) && status !== "broken") fail(path, "infrastructure_failure_not_broken");
  if (status === "passed" || status === "failed") {
    if (!graderResults.length || graderResults.some((item) => item.execution_status !== "completed")) fail(path, "evaluable_sample_grader_missing");
    if ((status === "failed") !== graderResults.some((item) => item.verdict === "failed")) fail(path, "sample_verdict_mismatch");
  } else if (status === "broken") {
    if (!failures.length && !graderError) fail(path, "broken_sample_failure_missing");
  } else if (candidateOutcome !== "skipped" || metrics.length || graderResults.length) {
    fail(path, "skipped_sample_contains_execution");
  }
  if (candidateOutcome === "unavailable" || candidateOutcome === "skipped") {
    if (rawSchemaValid !== null || finalSchemaValid !== null) fail(path, "unavailable_schema_evidence_forbidden");
  } else if (rawSchemaValid === null || finalSchemaValid === null) fail(path, "candidate_schema_evidence_required");
  if (rawSchemaValid === true && finalSchemaValid !== true) fail(path, "final_schema_regressed");
  const startedAt = timestamp(field(value, "started_at"), `${path}.started_at`);
  const completedAt = timestamp(field(value, "completed_at"), `${path}.completed_at`);
  if (Date.parse(startedAt) > Date.parse(completedAt)) fail(path, "time_range_invalid");
  return {
    schema_name: "HarnessEvalSample",
    schema_version: HARNESS_EVAL_SAMPLE_SCHEMA_VERSION,
    sample_id: string(field(value, "sample_id"), `${path}.sample_id`, SAMPLE_ID),
    run_id: string(field(value, "run_id"), `${path}.run_id`, RUN_ID),
    harness_operation_id: string(
      field(value, "harness_operation_id"),
      `${path}.harness_operation_id`,
      /^harness-operation-[0-9a-f]{32}$/,
    ),
    sample_index: integer(field(value, "sample_index"), `${path}.sample_index`, 1, 10_000_000),
    case_ref: decodeCaseRef(field(value, "case_ref"), `${path}.case_ref`),
    repetition_index: integer(field(value, "repetition_index"), `${path}.repetition_index`, 1, 1_000),
    seed: integer(field(value, "seed"), `${path}.seed`),
    status,
    candidate_outcome: candidateOutcome,
    raw_schema_valid: rawSchemaValid,
    final_schema_valid: finalSchemaValid,
    trace_contract: traceContract,
    trace_digest: traceDigest,
    metrics,
    grader_results: graderResults,
    failures,
    evidence_digest: digest(field(value, "evidence_digest"), `${path}.evidence_digest`),
    started_at: startedAt,
    completed_at: completedAt,
    duration_ms: integer(field(value, "duration_ms"), `${path}.duration_ms`, 0, 86_400_000),
    sample_digest: digest(field(value, "sample_digest"), `${path}.sample_digest`),
  };
}

function decodeSampleRef(raw: unknown, path: string): HarnessEvalSampleRefV1 {
  const value = record(raw, path, ["sample_id", "sample_index", "case_ref", "sample_digest"]);
  return {
    sample_id: string(field(value, "sample_id"), `${path}.sample_id`, SAMPLE_ID),
    sample_index: integer(field(value, "sample_index"), `${path}.sample_index`, 1, 10_000_000),
    case_ref: decodeCaseRef(field(value, "case_ref"), `${path}.case_ref`),
    sample_digest: digest(field(value, "sample_digest"), `${path}.sample_digest`),
  };
}

function decodeBaseline(raw: unknown, path: string): HarnessEvalBaselineV1 {
  const value = record(raw, path, ["schema_name", "schema_version", "baseline_id", "baseline_version", "suite", "suite_manifest_digest", "case_set_digest", "tested_system_config_digest", "environment_digest", "execution_mode", "splits", "repetition_count", "seeds", "minimum_sample_count", "report_contract", "report_id", "report_digest", "raw_samples_artifact", "metrics", "thresholds", "review_contract", "review_attestation_digest", "baseline_digest"]);
  literal(field(value, "schema_name"), "HarnessEvalBaseline", `${path}.schema_name`);
  literal(field(value, "schema_version"), HARNESS_EVAL_BASELINE_SCHEMA_VERSION, `${path}.schema_version`);
  const splits = array(field(value, "splits"), `${path}.splits`, (v, p) => enumeration(v, ["development", "validation", "held_out", "calibration", "regression"] as const, p), 1, 8);
  assertSortedUnique(splits, `${path}.splits`);
  const repetitionCount = integer(field(value, "repetition_count"), `${path}.repetition_count`, 1, 1000);
  const seeds = array(field(value, "seeds"), `${path}.seeds`, integer, 1, 1000);
  if (seeds.length !== repetitionCount || new Set(seeds).size !== seeds.length) fail(`${path}.seeds`, "seed_count_or_identity_mismatch");
  const artifactRaw = record(field(value, "raw_samples_artifact"), `${path}.raw_samples_artifact`, ["artifact_id", "artifact_contract", "payload_digest", "sample_count"]);
  const artifactContract = contract(field(artifactRaw, "artifact_contract"), `${path}.raw_samples_artifact.artifact_contract`);
  if (artifactContract.name !== "HarnessEvalRawSamples" || artifactContract.version !== HARNESS_EVAL_RAW_SAMPLES_SCHEMA_VERSION) fail(`${path}.raw_samples_artifact.artifact_contract`, "raw_samples_contract_mismatch");
  const reportContract = contract(field(value, "report_contract"), `${path}.report_contract`);
  if (reportContract.name !== "HarnessEvalReport" || reportContract.version !== HARNESS_EVAL_REPORT_SCHEMA_VERSION) fail(`${path}.report_contract`, "report_contract_mismatch");
  const thresholds = array(field(value, "thresholds"), `${path}.thresholds`, (v, p) => {
    const item = record(v, p, ["metric", "direction", "absolute_value", "max_regression_ratio"]);
    return { metric: contract(field(item, "metric"), `${p}.metric`), direction: enumeration(field(item, "direction"), ["minimum", "maximum"] as const, `${p}.direction`), absolute_value: number(field(item, "absolute_value"), `${p}.absolute_value`), max_regression_ratio: nullable(field(item, "max_regression_ratio"), `${p}.max_regression_ratio`, (x, q) => number(x, q, 0, 1)) };
  }, 1, 256);
  assertSortedUnique(thresholds.map(x => contractIdentity(x.metric)), `${path}.thresholds`);
  const metrics = array(field(value, "metrics"), `${path}.metrics`, decodeMetricAggregate, 1, 256);
  assertSortedUnique(metrics.map(x => contractIdentity(x.metric)), `${path}.metrics`);
  if (!thresholds.every(t => metrics.some(m => contractIdentity(m.metric) === contractIdentity(t.metric)))) fail(path, "threshold_metric_missing");
  const sampleCount = integer(field(artifactRaw, "sample_count"), `${path}.raw_samples_artifact.sample_count`, 1, 10000000);
  const minimumSampleCount = integer(field(value, "minimum_sample_count"), `${path}.minimum_sample_count`, 1, 10000000);
  if (sampleCount < minimumSampleCount) fail(path, "sample_count_insufficient");
  return { schema_name: "HarnessEvalBaseline", schema_version: HARNESS_EVAL_BASELINE_SCHEMA_VERSION, baseline_id: string(field(value, "baseline_id"), `${path}.baseline_id`, /^harness-eval-baseline-[0-9a-f]{32}$/), baseline_version: string(field(value, "baseline_version"), `${path}.baseline_version`, TOKEN), suite: contract(field(value, "suite"), `${path}.suite`), suite_manifest_digest: digest(field(value, "suite_manifest_digest"), `${path}.suite_manifest_digest`), case_set_digest: digest(field(value, "case_set_digest"), `${path}.case_set_digest`), tested_system_config_digest: digest(field(value, "tested_system_config_digest"), `${path}.tested_system_config_digest`), environment_digest: digest(field(value, "environment_digest"), `${path}.environment_digest`), execution_mode: enumeration(field(value, "execution_mode"), ["fixture", "synthetic", "protected_replay"] as const, `${path}.execution_mode`), splits, repetition_count: repetitionCount, seeds, minimum_sample_count: minimumSampleCount, report_contract: reportContract, report_id: string(field(value, "report_id"), `${path}.report_id`, REPORT_ID), report_digest: digest(field(value, "report_digest"), `${path}.report_digest`), raw_samples_artifact: { artifact_id: string(field(artifactRaw, "artifact_id"), `${path}.raw_samples_artifact.artifact_id`, TOKEN), artifact_contract: artifactContract, payload_digest: digest(field(artifactRaw, "payload_digest"), `${path}.raw_samples_artifact.payload_digest`), sample_count: sampleCount }, metrics, thresholds, review_contract: contract(field(value, "review_contract"), `${path}.review_contract`), review_attestation_digest: digest(field(value, "review_attestation_digest"), `${path}.review_attestation_digest`), baseline_digest: digest(field(value, "baseline_digest"), `${path}.baseline_digest`) };
}

export function decodeHarnessEvalBaseline(raw: unknown, path = "eval_baseline"): HarnessEvalBaselineV1 { return decodeBaseline(raw, path); }

export function decodeHarnessEvalGateDecision(raw: unknown, path = "eval_gate_decision"): HarnessEvalGateDecisionV1 {
  const value = record(raw, path, ["schema_name", "schema_version", "baseline_id", "candidate_report_id", "status", "comparable", "failure_codes", "metric_results", "decision_digest"]);
  literal(field(value, "schema_name"), "HarnessEvalGateDecision", `${path}.schema_name`); literal(field(value, "schema_version"), HARNESS_EVAL_GATE_DECISION_SCHEMA_VERSION, `${path}.schema_version`);
  const comparable = boolean(field(value, "comparable"), `${path}.comparable`); const failures = array(field(value, "failure_codes"), `${path}.failure_codes`, (v,p) => string(v,p,TOKEN), 0, 64); assertSortedUnique(failures, `${path}.failure_codes`);
  const results = array(field(value, "metric_results"), `${path}.metric_results`, (v,p) => { const item = record(v,p,["metric","baseline_value","candidate_value","passed","failure_code"]); const passed=boolean(field(item,"passed"),`${p}.passed`); const code=nullable(field(item,"failure_code"),`${p}.failure_code`,(x,q)=>string(x,q,TOKEN)); if (passed === (code !== null)) fail(p,"metric_failure_shape_invalid"); return {metric:contract(field(item,"metric"),`${p}.metric`),baseline_value:number(field(item,"baseline_value"),`${p}.baseline_value`),candidate_value:number(field(item,"candidate_value"),`${p}.candidate_value`),passed,failure_code:code}; },0,256);
  assertSortedUnique(results.map(x=>contractIdentity(x.metric)), `${path}.metric_results`);
  const status=enumeration(field(value,"status"),["passed","failed","blocked"] as const,`${path}.status`); if (status !== (comparable ? (failures.length ? "failed" : "passed") : "blocked")) fail(path,"status_mismatch");
  return {schema_name:"HarnessEvalGateDecision",schema_version:HARNESS_EVAL_GATE_DECISION_SCHEMA_VERSION,baseline_id:string(field(value,"baseline_id"),`${path}.baseline_id`,/^harness-eval-baseline-[0-9a-f]{32}$/),candidate_report_id:string(field(value,"candidate_report_id"),`${path}.candidate_report_id`,REPORT_ID),status,comparable,failure_codes:failures,metric_results:results,decision_digest:digest(field(value,"decision_digest"),`${path}.decision_digest`)};
}

export function decodeHarnessEvalReport(raw: unknown, path = "eval_report"): HarnessEvalReportV1 {
  const keys = ["schema_name", "schema_version", "report_id", "run_id", "run_digest", "tested_system_config_digest", "status", "expected_sample_count", "sample_count", "passed_count", "failed_count", "broken_count", "skipped_count", "sample_refs", "raw_samples_artifact", "aggregate_metrics", "failure_counts", "started_at", "completed_at", "report_digest"] as const;
  const value = record(raw, path, keys);
  literal(field(value, "schema_name"), "HarnessEvalReport", `${path}.schema_name`);
  literal(field(value, "schema_version"), HARNESS_EVAL_REPORT_SCHEMA_VERSION, `${path}.schema_version`);
  const status = enumeration(field(value, "status"), ["passed", "failed", "broken"] as const, `${path}.status`);
  const expectedSampleCount = integer(field(value, "expected_sample_count"), `${path}.expected_sample_count`, 1, 10_000_000);
  const sampleCount = integer(field(value, "sample_count"), `${path}.sample_count`, 0, 10_000_000);
  const passedCount = integer(field(value, "passed_count"), `${path}.passed_count`, 0, 10_000_000);
  const failedCount = integer(field(value, "failed_count"), `${path}.failed_count`, 0, 10_000_000);
  const brokenCount = integer(field(value, "broken_count"), `${path}.broken_count`, 0, 10_000_000);
  const skippedCount = integer(field(value, "skipped_count"), `${path}.skipped_count`, 0, 10_000_000);
  const sampleRefs = array(field(value, "sample_refs"), `${path}.sample_refs`, decodeSampleRef, 0, 10_000);
  if (sampleCount !== sampleRefs.length) fail(path, "sample_count_mismatch");
  if (sampleCount !== passedCount + failedCount + brokenCount + skippedCount) fail(path, "terminal_counts_mismatch");
  if (sampleRefs.some((item, index) => item.sample_index !== index + 1) || new Set(sampleRefs.map((item) => item.sample_id)).size !== sampleRefs.length) fail(path, "sample_manifest_not_canonical");
  const rawSamplesArtifact = nullable(field(value, "raw_samples_artifact"), `${path}.raw_samples_artifact`, (item, itemPath) => {
    const artifact = record(item, itemPath, ["artifact_id", "artifact_contract", "payload_digest", "sample_count"]);
    const artifactContract = contract(field(artifact, "artifact_contract"), `${itemPath}.artifact_contract`);
    if (artifactContract.name !== "HarnessEvalRawSamples" || artifactContract.version !== HARNESS_EVAL_RAW_SAMPLES_SCHEMA_VERSION) fail(`${itemPath}.artifact_contract`, "raw_samples_contract_mismatch");
    return {
      artifact_id: string(field(artifact, "artifact_id"), `${itemPath}.artifact_id`, TOKEN),
      artifact_contract: artifactContract,
      payload_digest: digest(field(artifact, "payload_digest"), `${itemPath}.payload_digest`),
      sample_count: integer(field(artifact, "sample_count"), `${itemPath}.sample_count`, 0, 10_000_000),
    };
  });
  if (sampleCount > 0 && (!rawSamplesArtifact || rawSamplesArtifact.sample_count !== sampleCount)) fail(path, "raw_samples_mismatch");
  if (sampleCount === 0 && rawSamplesArtifact) fail(path, "empty_raw_samples_forbidden");
  const aggregateMetrics = array(field(value, "aggregate_metrics"), `${path}.aggregate_metrics`, decodeMetricAggregate, 0, 256);
  assertSortedUnique(aggregateMetrics.map((item) => contractIdentity(item.metric)), `${path}.aggregate_metrics`);
  const failureCounts = array(field(value, "failure_counts"), `${path}.failure_counts`, (item, itemPath) => {
    const entry = record(item, itemPath, ["failure_code", "count"]);
    const failureCode = string(field(entry, "failure_code"), `${itemPath}.failure_code`, TOKEN);
    if (!HARNESS_EVAL_FAILURE_TAXONOMY[failureCode]) fail(`${itemPath}.failure_code`, "unregistered_failure_code");
    return { failure_code: failureCode, count: integer(field(entry, "count"), `${itemPath}.count`, 1, 10_000_000) };
  }, 0, 256);
  assertSortedUnique(failureCounts.map((item) => item.failure_code), `${path}.failure_counts`);
  const expectedStatus = brokenCount > 0 || sampleCount !== expectedSampleCount ? "broken" : failedCount > 0 ? "failed" : "passed";
  if (status !== expectedStatus) fail(path, "report_status_mismatch");
  const startedAt = timestamp(field(value, "started_at"), `${path}.started_at`);
  const completedAt = timestamp(field(value, "completed_at"), `${path}.completed_at`);
  if (Date.parse(startedAt) > Date.parse(completedAt)) fail(path, "time_range_invalid");
  return {
    schema_name: "HarnessEvalReport",
    schema_version: HARNESS_EVAL_REPORT_SCHEMA_VERSION,
    report_id: string(field(value, "report_id"), `${path}.report_id`, REPORT_ID),
    run_id: string(field(value, "run_id"), `${path}.run_id`, RUN_ID),
    run_digest: digest(field(value, "run_digest"), `${path}.run_digest`),
    tested_system_config_digest: digest(field(value, "tested_system_config_digest"), `${path}.tested_system_config_digest`),
    status,
    expected_sample_count: expectedSampleCount,
    sample_count: sampleCount,
    passed_count: passedCount,
    failed_count: failedCount,
    broken_count: brokenCount,
    skipped_count: skippedCount,
    sample_refs: sampleRefs,
    raw_samples_artifact: rawSamplesArtifact,
    aggregate_metrics: aggregateMetrics,
    failure_counts: failureCounts,
    started_at: startedAt,
    completed_at: completedAt,
    report_digest: digest(field(value, "report_digest"), `${path}.report_digest`),
  };
}

function equalContract(left: HarnessContractRef, right: HarnessContractRef): boolean {
  return left.name === right.name && left.version === right.version;
}

function equalCaseRef(left: HarnessEvalCaseRefV1, right: HarnessEvalCaseRefV1): boolean {
  return equalContract(left.suite, right.suite) && left.case_id === right.case_id && left.case_version === right.case_version && left.case_digest === right.case_digest;
}

export function decodeHarnessEvalContractGolden(raw: unknown, path = "eval_golden"): HarnessEvalContractGoldenV1 {
  const value = record(raw, path, ["schema_name", "schema_version", "case", "run", "sample", "report"]);
  literal(field(value, "schema_name"), "HarnessEvalContractGolden", `${path}.schema_name`);
  literal(field(value, "schema_version"), HARNESS_EVAL_CONTRACT_GOLDEN_SCHEMA_VERSION, `${path}.schema_version`);
  const evalCase = decodeHarnessEvalCase(field(value, "case"), `${path}.case`);
  const run = decodeHarnessEvalRun(field(value, "run"), `${path}.run`);
  const sample = decodeHarnessEvalSample(field(value, "sample"), `${path}.sample`);
  const report = decodeHarnessEvalReport(field(value, "report"), `${path}.report`);
  const caseRef: HarnessEvalCaseRefV1 = { suite: evalCase.suite, case_id: evalCase.case_id, case_version: evalCase.case_version, case_digest: evalCase.case_digest };
  if (!equalContract(run.suite, evalCase.suite) || !equalCaseRef(sample.case_ref, caseRef)) fail(path, "case_identity_mismatch");
  if (sample.run_id !== run.run_id || report.run_id !== run.run_id || report.run_digest !== run.run_digest || report.tested_system_config_digest !== run.tested_system_config_digest) fail(path, "run_identity_mismatch");
  if (report.sample_refs.length !== 1 || report.sample_refs[0]!.sample_id !== sample.sample_id || report.sample_refs[0]!.sample_digest !== sample.sample_digest || !equalCaseRef(report.sample_refs[0]!.case_ref, sample.case_ref)) fail(path, "sample_ref_mismatch");
  return { schema_name: "HarnessEvalContractGolden", schema_version: HARNESS_EVAL_CONTRACT_GOLDEN_SCHEMA_VERSION, case: evalCase, run, sample, report };
}
