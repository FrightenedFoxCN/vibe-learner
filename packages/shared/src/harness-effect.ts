import type { HarnessContractRef, HarnessResourceType } from "./harness";

export type HarnessEffectBoundaryKind =
  | "pure_read"
  | "database_write"
  | "file_write"
  | "external_call";

export type HarnessEffectTerminalOutcome =
  | "not_committed"
  | "committed"
  | "uncertain";

export type HarnessEffectPreparePolicy = "validate_and_assign_identity";
export type HarnessEffectCommitPolicy =
  | "database_transaction"
  | "staging_outbox"
  | "external_idempotency_or_read_back";
export type HarnessEffectCompensationPolicy =
  | "not_applicable"
  | "cleanup"
  | "domain_compensation";
export type HarnessEffectReadBackPolicy =
  | "exact_projection"
  | "provider_lookup"
  | "unsupported";

export interface HarnessEffectAdapterRefV1 {
  name: string;
  version: string;
  boundary_kind: HarnessEffectBoundaryKind;
  prepare_policy: HarnessEffectPreparePolicy;
  commit_policy: HarnessEffectCommitPolicy;
  compensation_policy: HarnessEffectCompensationPolicy;
  read_back_policy: HarnessEffectReadBackPolicy;
}

export interface HarnessEffectTargetRefV1 {
  resource_type: HarnessResourceType;
  resource_id: string;
}

export interface HarnessPreparedEffectV1<Proposal> {
  schema_name: "HarnessPreparedEffectV1";
  schema_version: "harness-prepared-effect-v1";
  operation_id: string;
  effect_batch_id: string;
  effect_id: string;
  slot: number;
  adapter: HarnessEffectAdapterRefV1;
  proposal_contract: HarnessContractRef;
  target_refs: HarnessEffectTargetRefV1[];
  proposal: Proposal;
}

export interface HarnessPreparedEffectBatchV1<Proposal> {
  schema_name: "HarnessPreparedEffectBatchV1";
  schema_version: "harness-prepared-effect-batch-v1";
  operation_id: string;
  effect_batch_id: string;
  effects: HarnessPreparedEffectV1<Proposal>[];
}

export type StudyPlanConfirmationEffectAction =
  | "update_plan"
  | "update_plan_progress";

export interface StudyPlanConfirmationEffectProposalV1 {
  schema_name: "StudyPlanConfirmationEffectProposalV1";
  schema_version: "study-plan-confirmation-effect-v1";
  action: StudyPlanConfirmationEffectAction;
  course_title: string;
  schedule_ids: string[];
  schedule_status: "" | "planned" | "in_progress" | "completed" | "blocked" | "skipped";
  note: string;
}

export interface StudyPlanConfirmationCommittedProjectionV1 {
  schema_name: "StudyPlanConfirmationCommittedProjectionV1";
  schema_version: "study-plan-confirmation-committed-projection-v1";
  operation_id: string;
  effect_batch_id: string;
  effect_id: string;
  slot: number;
  session_id: string;
  confirmation_id: string;
  action: StudyPlanConfirmationEffectAction;
  plan_id: string;
  status: "pending";
  created_at: string;
}

function deepFreeze<T>(value: T): Readonly<T> {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const child of Object.values(value as Record<string, unknown>)) {
      deepFreeze(child);
    }
    Object.freeze(value);
  }
  return value;
}

export const HARNESS_EFFECT_ADAPTER_POLICIES = deepFreeze({
  study_plan_confirmation_create: {
    name: "study_plan_confirmation_create",
    version: "study-plan-confirmation-create-v1",
    boundary_kind: "database_write",
    prepare_policy: "validate_and_assign_identity",
    commit_policy: "database_transaction",
    compensation_policy: "not_applicable",
    read_back_policy: "exact_projection",
  },
} as const satisfies Record<string, HarnessEffectAdapterRefV1>);

export interface HarnessEffectAdapterPolicyRegistrySnapshot {
  schema_name: "HarnessEffectAdapterPolicyRegistry";
  schema_version: "harness-effect-adapter-policy-registry-v1";
  adapters: HarnessEffectAdapterRefV1[];
}

export function harnessEffectAdapterPolicyRegistrySnapshot(): HarnessEffectAdapterPolicyRegistrySnapshot {
  return {
    schema_name: "HarnessEffectAdapterPolicyRegistry",
    schema_version: "harness-effect-adapter-policy-registry-v1",
    adapters: Object.entries(HARNESS_EFFECT_ADAPTER_POLICIES)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([, adapter]) => ({ ...adapter })),
  };
}
