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
  effect_kind: "plan_confirmation";
  action: StudyPlanConfirmationEffectAction;
  course_title: string;
  schedule_ids: string[];
  schedule_status: "" | "planned" | "in_progress" | "completed" | "blocked" | "skipped";
  note: string;
}

export interface StudyMemoryUpsertEffectProposalV1 {
  schema_name: "StudyMemoryUpsertEffectProposalV1";
  schema_version: "study-memory-upsert-effect-v1";
  effect_kind: "memory_upsert";
  key: string;
  content: string;
}

export interface StudyAffinityDeltaEffectProposalV1 {
  schema_name: "StudyAffinityDeltaEffectProposalV1";
  schema_version: "study-affinity-delta-effect-v1";
  effect_kind: "affinity_delta";
  delta: number;
  reason: string;
}

export type StudyFollowUpEffectAction =
  | "schedule"
  | "complete"
  | "cancel_pending";

export interface StudyFollowUpEffectProposalV1 {
  schema_name: "StudyFollowUpEffectProposalV1";
  schema_version: "study-follow-up-effect-v1";
  effect_kind: "follow_up";
  action: StudyFollowUpEffectAction;
  follow_up_id: string;
  delay_seconds: number;
  hidden_message: string;
  reason: string;
}

export type StudyProjectionEffectAction =
  | "set"
  | "focus"
  | "append_overlay"
  | "clear_overlays";

export interface StudyProjectionRectV1 {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface StudyProjectionEffectProposalV1 {
  schema_name: "StudyProjectionEffectProposalV1";
  schema_version: "study-projection-effect-v1";
  effect_kind: "projection";
  action: StudyProjectionEffectAction;
  source_kind: string;
  source_id: string;
  title: string;
  page_number: number;
  page_count: number;
  image_url: string;
  overlay_kind: string;
  rects: StudyProjectionRectV1[];
  label: string;
  quote_text: string;
  color: string;
}

export interface StudySceneObjectStateV1 {
  id: string;
  name: string;
  description: string;
  interaction: string;
  tags: string;
  reuse_id: string;
  reuse_hint: string;
}

export interface StudySceneLayerStateV1 {
  id: string;
  title: string;
  scope_label: string;
  summary: string;
  atmosphere: string;
  rules: string;
  entrance: string;
  tags: string;
  reuse_id: string;
  reuse_hint: string;
  objects: StudySceneObjectStateV1[];
  children: StudySceneLayerStateV1[];
}

export interface StudySceneProfileStateV1 {
  scene_name: string;
  scene_id: string;
  title: string;
  summary: string;
  tags: string[];
  selected_path: string[];
  focus_object_names: string[];
  scene_tree: StudySceneLayerStateV1[];
}

export interface StudySessionSceneStateV1 {
  config_id: string;
  updated_at: string;
  scene_name: string;
  scene_summary: string;
  scene_layers: StudySceneLayerStateV1[];
  selected_layer_id: string;
  collapsed_layer_ids: string[];
  scene_profile: StudySceneProfileStateV1 | null;
  scene_instance_id: string;
  session_id: string;
  document_id: string;
  persona_id: string;
  source_scene_id: string;
  source_scene_name: string;
  created_at: string;
}

export interface StudySceneReplaceEffectProposalV1 {
  schema_name: "StudySceneReplaceEffectProposalV1";
  schema_version: "study-scene-replace-effect-v1";
  effect_kind: "scene_replace";
  tool_name:
    | "add_scene"
    | "move_to_scene"
    | "add_object"
    | "update_object_description"
    | "delete_object";
  before_state_digest: string;
  proposed_record: StudySessionSceneStateV1;
}

export type StudyChatEffectProposalV1 =
  | StudyMemoryUpsertEffectProposalV1
  | StudyAffinityDeltaEffectProposalV1
  | StudyFollowUpEffectProposalV1
  | StudyProjectionEffectProposalV1
  | StudySceneReplaceEffectProposalV1
  | StudyPlanConfirmationEffectProposalV1;

export interface StudyPlanConfirmationCommittedProjectionV1 {
  schema_name: "StudyPlanConfirmationCommittedProjectionV1";
  schema_version: "study-plan-confirmation-committed-projection-v1";
  effect_kind: "plan_confirmation";
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

export interface StudyMemoryUpsertCommittedProjectionV1 {
  schema_name: "StudyMemoryUpsertCommittedProjectionV1";
  schema_version: "study-memory-upsert-committed-projection-v1";
  effect_kind: "memory_upsert";
  operation_id: string;
  effect_batch_id: string;
  effect_id: string;
  slot: number;
  session_id: string;
  memory_id: string;
  key: string;
  content: string;
  source: "tool_call";
  created_at: string;
  updated_at: string;
}

export interface StudyAffinityDeltaCommittedProjectionV1 {
  schema_name: "StudyAffinityDeltaCommittedProjectionV1";
  schema_version: "study-affinity-delta-committed-projection-v1";
  effect_kind: "affinity_delta";
  operation_id: string;
  effect_batch_id: string;
  effect_id: string;
  slot: number;
  session_id: string;
  event_id: string;
  delta: number;
  reason: string;
  source: "tool_call";
  score: number;
  level: string;
  summary: string;
  created_at: string;
  updated_at: string;
}

export interface StudyFollowUpCommittedProjectionV1 {
  schema_name: "StudyFollowUpCommittedProjectionV1";
  schema_version: "study-follow-up-committed-projection-v1";
  effect_kind: "follow_up";
  operation_id: string;
  effect_batch_id: string;
  effect_id: string;
  slot: number;
  session_id: string;
  action: StudyFollowUpEffectAction;
  follow_up_id: string;
  affected_follow_up_ids: string[];
  committed_at: string;
}

export interface StudyProjectionOverlayStateV1 {
  id: string;
  kind: string;
  page_number: number;
  rects: StudyProjectionRectV1[];
  label: string;
  quote_text: string;
  color: string;
  created_at: string;
}

export interface StudyProjectedStateV1 {
  source_kind: string;
  source_id: string;
  title: string;
  page_number: number;
  page_count: number;
  image_url: string;
  overlays: StudyProjectionOverlayStateV1[];
  updated_at: string;
}

export interface StudyProjectionCommittedProjectionV1 {
  schema_name: "StudyProjectionCommittedProjectionV1";
  schema_version: "study-projection-committed-projection-v1";
  effect_kind: "projection";
  operation_id: string;
  effect_batch_id: string;
  effect_id: string;
  slot: number;
  session_id: string;
  action: StudyProjectionEffectAction;
  projected_state: StudyProjectedStateV1;
}

export interface StudySceneReplaceCommittedProjectionV1 {
  schema_name: "StudySceneReplaceCommittedProjectionV1";
  schema_version: "study-scene-replace-committed-projection-v1";
  effect_kind: "scene_replace";
  operation_id: string;
  effect_batch_id: string;
  effect_id: string;
  slot: number;
  session_id: string;
  scene_instance_id: string;
  tool_name: StudySceneReplaceEffectProposalV1["tool_name"];
  scene_state_digest: string;
  updated_at: string;
  committed_record: StudySessionSceneStateV1;
}

export type StudyChatCommittedEffectProjectionV1 =
  | StudyMemoryUpsertCommittedProjectionV1
  | StudyAffinityDeltaCommittedProjectionV1
  | StudyFollowUpCommittedProjectionV1
  | StudyProjectionCommittedProjectionV1
  | StudySceneReplaceCommittedProjectionV1
  | StudyPlanConfirmationCommittedProjectionV1;

export interface StudyChatCommittedEffectBatchV1 {
  schema_name: "StudyChatCommittedEffectBatchV1";
  schema_version: "study-chat-committed-effect-batch-v1";
  operation_id: string;
  effect_batch_id: string;
  effects: StudyChatCommittedEffectProjectionV1[];
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
  study_affinity_delta: {
    name: "study_affinity_delta",
    version: "study-affinity-delta-v1",
    boundary_kind: "database_write",
    prepare_policy: "validate_and_assign_identity",
    commit_policy: "database_transaction",
    compensation_policy: "not_applicable",
    read_back_policy: "exact_projection",
  },
  study_memory_upsert: {
    name: "study_memory_upsert",
    version: "study-memory-upsert-v1",
    boundary_kind: "database_write",
    prepare_policy: "validate_and_assign_identity",
    commit_policy: "database_transaction",
    compensation_policy: "not_applicable",
    read_back_policy: "exact_projection",
  },
  study_follow_up_mutation: {
    name: "study_follow_up_mutation",
    version: "study-follow-up-mutation-v1",
    boundary_kind: "database_write",
    prepare_policy: "validate_and_assign_identity",
    commit_policy: "database_transaction",
    compensation_policy: "not_applicable",
    read_back_policy: "exact_projection",
  },
  study_projection_mutation: {
    name: "study_projection_mutation",
    version: "study-projection-mutation-v1",
    boundary_kind: "database_write",
    prepare_policy: "validate_and_assign_identity",
    commit_policy: "database_transaction",
    compensation_policy: "not_applicable",
    read_back_policy: "exact_projection",
  },
  study_scene_replace: {
    name: "study_scene_replace",
    version: "study-scene-replace-v1",
    boundary_kind: "database_write",
    prepare_policy: "validate_and_assign_identity",
    commit_policy: "database_transaction",
    compensation_policy: "not_applicable",
    read_back_policy: "exact_projection",
  },
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
