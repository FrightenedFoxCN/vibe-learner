export type HarnessStatus = "passed" | "repaired" | "failed" | "skipped";
export type HarnessCheckStatus = "passed" | "failed" | "warning" | "skipped";

export interface HarnessCheckV1 {
  name: string;
  status: HarnessCheckStatus;
  code: string;
  message: string;
}

export interface HarnessTraceV1 {
  version: string;
  workflow: string;
  stage: string;
  status: HarnessStatus;
  schemaName: string;
  inputDigest: string;
  contextDigest: string;
  checks: HarnessCheckV1[];
  attempts: number;
  recoveryStrategy: string;
  durationMs: number;
}

export type HarnessWorkflow =
  | "document_parse"
  | "ocr"
  | "study_unit_cleanup"
  | "planning"
  | "persona"
  | "scene"
  | "study_chat"
  | "tavern"
  | "frontend_decode";
export type HarnessStage =
  | "document_parse"
  | "page_extraction"
  | "section_detection"
  | "chunk_building"
  | "ocr_page"
  | "study_unit_cleanup"
  | "plan_generation"
  | "planning_tool_execution"
  | "persona_generation"
  | "scene_generation"
  | "study_chat_reply"
  | "actor_reply"
  | "response_decode";

export type HarnessComponentName =
  | "document_parser"
  | "document_page_extractor"
  | "document_section_detector"
  | "document_chunk_builder"
  | "ocr_engine"
  | "study_unit_cleaner"
  | "planning_prompt"
  | "planning_toolset"
  | "planning_tool_runtime"
  | "persona_compiler"
  | "scene_compiler"
  | "study_chat_prompt"
  | "study_chat_toolset"
  | "tavern_persona_compiler"
  | "tavern_actor_prompt"
  | "tavern_scheduler"
  | "frontend_decoder";

export interface HarnessComponentRegistration {
  ownerModule: string;
  contract: HarnessContractRef | null;
}

export interface HarnessOperationStageRegistration {
  ownerModule: string;
  componentNames: HarnessComponentName[];
  evalRoute: string;
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

export type HarnessOperationStageKey =
  | "document_parse:document_parse"
  | "document_parse:page_extraction"
  | "document_parse:section_detection"
  | "document_parse:chunk_building"
  | "ocr:ocr_page"
  | "study_unit_cleanup:study_unit_cleanup"
  | "planning:plan_generation"
  | "planning:planning_tool_execution"
  | "persona:persona_generation"
  | "scene:scene_generation"
  | "study_chat:study_chat_reply"
  | "tavern:actor_reply"
  | "frontend_decode:response_decode";

export const HARNESS_STAGE_WORKFLOWS = deepFreeze({
  document_parse: "document_parse",
  page_extraction: "document_parse",
  section_detection: "document_parse",
  chunk_building: "document_parse",
  ocr_page: "ocr",
  study_unit_cleanup: "study_unit_cleanup",
  plan_generation: "planning",
  planning_tool_execution: "planning",
  persona_generation: "persona",
  scene_generation: "scene",
  study_chat_reply: "study_chat",
  actor_reply: "tavern",
  response_decode: "frontend_decode",
} as const satisfies Record<HarnessStage, HarnessWorkflow>);

export const HARNESS_COMPONENT_REGISTRATIONS = deepFreeze({
  document_parser: { ownerModule: "app.services.document_parser", contract: { name: "document_parser", version: "document-parser-v1" } },
  document_page_extractor: {
    ownerModule: "app.services.document_parser",
    contract: { name: "document_page_extractor", version: "document-page-extractor-v1" },
  },
  document_section_detector: {
    ownerModule: "app.services.document_parser",
    contract: { name: "document_section_detector", version: "document-section-detector-v1" },
  },
  document_chunk_builder: {
    ownerModule: "app.services.document_parser",
    contract: { name: "document_chunk_builder", version: "document-chunk-builder-v1" },
  },
  ocr_engine: { ownerModule: "app.services.ocr_engine", contract: { name: "ocr_engine", version: "ocr-engine-v1" } },
  study_unit_cleaner: { ownerModule: "app.services.study_arrangement", contract: { name: "study_unit_cleaner", version: "study-unit-cleaner-v1" } },
  planning_prompt: { ownerModule: "app.services.plan_prompt", contract: { name: "planning_prompt", version: "planning-prompt-v1" } },
  planning_toolset: {
    ownerModule: "app.services.plan_tool_runtime",
    contract: { name: "planning_toolset", version: "planning-toolset-v1" },
  },
  planning_tool_runtime: {
    ownerModule: "app.services.plan_tool_runtime",
    contract: { name: "planning_tool_runtime", version: "planning-tool-runtime-v1" },
  },
  persona_compiler: { ownerModule: "app.services.persona_cards", contract: { name: "persona_compiler", version: "persona-compiler-v1" } },
  scene_compiler: { ownerModule: "app.services.scene_setup", contract: { name: "scene_compiler", version: "scene-compiler-v1" } },
  study_chat_prompt: { ownerModule: "app.services.study_session_prompt", contract: { name: "study_chat_prompt", version: "study-chat-prompt-v1" } },
  study_chat_toolset: {
    ownerModule: "app.services.study_session_chat_runtime",
    contract: { name: "study_chat_toolset", version: "study-chat-toolset-v1" },
  },
  tavern_persona_compiler: {
    ownerModule: "app.services.persona_runtime",
    contract: { name: "tavern_persona_compiler", version: "tavern-persona-compiler-v1" },
  },
  tavern_actor_prompt: {
    ownerModule: "app.services.tavern_prompt",
    contract: { name: "tavern_actor_prompt", version: "tavern-actor-v1" },
  },
  tavern_scheduler: {
    ownerModule: "app.services.tavern",
    contract: { name: "tavern_scheduler", version: "tavern-schedule-v1" },
  },
  frontend_decoder: { ownerModule: "apps.web.lib.api", contract: { name: "frontend_decoder", version: "frontend-decoder-v1" } },
} as const satisfies Record<HarnessComponentName, HarnessComponentRegistration>);

export const HARNESS_OPERATION_STAGE_REGISTRATIONS = deepFreeze({
  "document_parse:document_parse": {
    ownerModule: "app.services.document_parser",
    componentNames: ["document_parser"],
    evalRoute: "document.parse",
  },
  "document_parse:page_extraction": {
    ownerModule: "app.services.document_parser",
    componentNames: ["document_page_extractor"],
    evalRoute: "document.page_extraction",
  },
  "document_parse:section_detection": {
    ownerModule: "app.services.document_parser",
    componentNames: ["document_section_detector"],
    evalRoute: "document.section_detection",
  },
  "document_parse:chunk_building": {
    ownerModule: "app.services.document_parser",
    componentNames: ["document_chunk_builder"],
    evalRoute: "document.chunk_building",
  },
  "ocr:ocr_page": {
    ownerModule: "app.services.ocr_engine",
    componentNames: ["ocr_engine"],
    evalRoute: "document.ocr_page",
  },
  "study_unit_cleanup:study_unit_cleanup": {
    ownerModule: "app.services.study_arrangement",
    componentNames: ["study_unit_cleaner"],
    evalRoute: "document.study_unit_cleanup",
  },
  "planning:plan_generation": {
    ownerModule: "app.services.model_provider",
    componentNames: ["planning_prompt", "planning_toolset"],
    evalRoute: "planning.plan_generation",
  },
  "planning:planning_tool_execution": {
    ownerModule: "app.services.plan_tool_runtime",
    componentNames: ["planning_tool_runtime", "planning_toolset"],
    evalRoute: "planning.tool_execution",
  },
  "persona:persona_generation": {
    ownerModule: "app.services.persona_cards",
    componentNames: ["persona_compiler"],
    evalRoute: "persona.generation",
  },
  "scene:scene_generation": {
    ownerModule: "app.services.scene_setup",
    componentNames: ["scene_compiler"],
    evalRoute: "scene.generation",
  },
  "study_chat:study_chat_reply": {
    ownerModule: "app.services.study_sessions",
    componentNames: ["study_chat_prompt", "study_chat_toolset"],
    evalRoute: "study_chat.reply",
  },
  "tavern:actor_reply": {
    ownerModule: "app.services.tavern",
    componentNames: ["tavern_actor_prompt", "tavern_persona_compiler", "tavern_scheduler"],
    evalRoute: "tavern.actor_reply",
  },
  "frontend_decode:response_decode": {
    ownerModule: "apps.web.lib.api",
    componentNames: ["frontend_decoder"],
    evalRoute: "frontend.response_decode",
  },
} as const satisfies Record<HarnessOperationStageKey, HarnessOperationStageRegistration>);

export interface HarnessOperationStageRegistrySnapshot {
  schema_name: "HarnessOperationStageRegistry";
  schema_version: "harness-operation-stage-registry-v1";
  components: Array<{
    component_name: HarnessComponentName;
    owner_module: string;
    contract: HarnessContractRef | null;
  }>;
  stages: Array<{
    workflow: HarnessWorkflow;
    stage: HarnessStage;
    owner_module: string;
    component_names: HarnessComponentName[];
    eval_route: string;
  }>;
}

export function harnessOperationStageRegistrySnapshot(): HarnessOperationStageRegistrySnapshot {
  return {
    schema_name: "HarnessOperationStageRegistry",
    schema_version: "harness-operation-stage-registry-v1",
    components: Object.entries(HARNESS_COMPONENT_REGISTRATIONS)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([componentName, registration]) => ({
        component_name: componentName as HarnessComponentName,
        owner_module: registration.ownerModule,
        contract: registration.contract,
      })),
    stages: Object.entries(HARNESS_OPERATION_STAGE_REGISTRATIONS)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, registration]) => {
        const [workflow, stage] = key.split(":") as [HarnessWorkflow, HarnessStage];
        return {
          workflow,
          stage,
          owner_module: registration.ownerModule,
          component_names: [...registration.componentNames],
          eval_route: registration.evalRoute,
        };
      }),
  };
}

export type HarnessAttemptPhase =
  | "generate"
  | "decode"
  | "validate"
  | "repair"
  | "commit"
  | "rollback";

export type HarnessAttemptStatus = "passed" | "failed" | "skipped";
export type HarnessCommitStatus =
  | "not_applicable"
  | "not_committed"
  | "committed"
  | "rolled_back";
export type HarnessDigestScope = "committed_projection" | "committed_batch";
export type HarnessArtifactType =
  | "document_upload"
  | "document_debug"
  | "ocr_page"
  | "study_unit_input"
  | "planning_context"
  | "persona_snapshot"
  | "scene_snapshot"
  | "study_session_snapshot"
  | "tavern_room_snapshot"
  | "tavern_transcript"
  | "frontend_response_fixture";
export type HarnessResourceType =
  | "document"
  | "document_page"
  | "document_debug"
  | "study_unit"
  | "learning_plan"
  | "planning_trace"
  | "persona"
  | "scene"
  | "study_session"
  | "tavern_room"
  | "tavern_run"
  | "tavern_message"
  | "frontend_request";
export type HarnessResourceSemantics =
  | "revisioned_control_aggregate"
  | "append_only"
  | "immutable"
  | "parent_bound"
  | "unversioned_mutable"
  | "operation_identity";
export type HarnessContextEvidencePolicy =
  | "authoritative_revision"
  | "protected_snapshot"
  | "operation_identity"
  | "unsupported";
export type HarnessCommitEvidencePolicy =
  | "revision"
  | "sequence"
  | "digest"
  | "unsupported";
export type HarnessOperationEvidenceScope = "primary_output_only" | "complete_transaction";
export type HarnessRollbackEvidencePolicy =
  | "read_back"
  | "compensation"
  | "unsupported";

export interface HarnessResourceEvidencePolicy {
  semantics: HarnessResourceSemantics;
  contextEvidence: HarnessContextEvidencePolicy;
  commitEvidence: HarnessCommitEvidencePolicy;
  rollbackEvidence: HarnessRollbackEvidencePolicy;
}

export const HARNESS_RESOURCE_EVIDENCE_POLICIES = {
  document: {
    semantics: "unversioned_mutable",
    contextEvidence: "unsupported",
    commitEvidence: "digest",
    rollbackEvidence: "unsupported",
  },
  document_page: {
    semantics: "parent_bound",
    contextEvidence: "unsupported",
    commitEvidence: "unsupported",
    rollbackEvidence: "unsupported",
  },
  document_debug: {
    semantics: "unversioned_mutable",
    contextEvidence: "unsupported",
    commitEvidence: "unsupported",
    rollbackEvidence: "unsupported",
  },
  study_unit: {
    semantics: "parent_bound",
    contextEvidence: "unsupported",
    commitEvidence: "unsupported",
    rollbackEvidence: "unsupported",
  },
  learning_plan: {
    semantics: "unversioned_mutable",
    contextEvidence: "unsupported",
    commitEvidence: "digest",
    rollbackEvidence: "unsupported",
  },
  planning_trace: {
    semantics: "unversioned_mutable",
    contextEvidence: "unsupported",
    commitEvidence: "unsupported",
    rollbackEvidence: "unsupported",
  },
  persona: {
    semantics: "unversioned_mutable",
    contextEvidence: "unsupported",
    commitEvidence: "unsupported",
    rollbackEvidence: "unsupported",
  },
  scene: {
    semantics: "unversioned_mutable",
    contextEvidence: "unsupported",
    commitEvidence: "unsupported",
    rollbackEvidence: "unsupported",
  },
  study_session: {
    semantics: "revisioned_control_aggregate",
    contextEvidence: "authoritative_revision",
    commitEvidence: "revision",
    rollbackEvidence: "unsupported",
  },
  tavern_room: {
    semantics: "revisioned_control_aggregate",
    contextEvidence: "authoritative_revision",
    commitEvidence: "revision",
    rollbackEvidence: "unsupported",
  },
  tavern_run: {
    semantics: "unversioned_mutable",
    contextEvidence: "unsupported",
    commitEvidence: "unsupported",
    rollbackEvidence: "unsupported",
  },
  tavern_message: {
    semantics: "append_only",
    contextEvidence: "unsupported",
    commitEvidence: "sequence",
    rollbackEvidence: "unsupported",
  },
  frontend_request: {
    semantics: "operation_identity",
    contextEvidence: "operation_identity",
    commitEvidence: "unsupported",
    rollbackEvidence: "unsupported",
  },
} as const satisfies Record<HarnessResourceType, HarnessResourceEvidencePolicy>;

export interface HarnessResourceEvidencePolicyRegistrySnapshot {
  schema_name: "HarnessResourceEvidencePolicyRegistry";
  schema_version: "harness-resource-evidence-policies-v1";
  resources: Array<{
    resource_type: HarnessResourceType;
    semantics: HarnessResourceSemantics;
    context_evidence: HarnessContextEvidencePolicy;
    commit_evidence: HarnessCommitEvidencePolicy;
    rollback_evidence: HarnessRollbackEvidencePolicy;
  }>;
}

export function harnessResourceEvidencePolicyRegistrySnapshot(): HarnessResourceEvidencePolicyRegistrySnapshot {
  return {
    schema_name: "HarnessResourceEvidencePolicyRegistry",
    schema_version: "harness-resource-evidence-policies-v1",
    resources: Object.entries(HARNESS_RESOURCE_EVIDENCE_POLICIES)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([resourceType, policy]) => ({
        resource_type: resourceType as HarnessResourceType,
        semantics: policy.semantics,
        context_evidence: policy.contextEvidence,
        commit_evidence: policy.commitEvidence,
        rollback_evidence: policy.rollbackEvidence,
      })),
  };
}

export interface HarnessOperationCommitPolicy {
  workflow: HarnessWorkflow;
  stage: HarnessStage;
  traceContract: HarnessContractRef;
  payloadContract: HarnessContractRef;
  projectionContract: HarnessContractRef;
  bindingContract: HarnessContractRef;
  digestScope: HarnessDigestScope;
  evidenceScope: HarnessOperationEvidenceScope;
  subjectResourceType: HarnessResourceType;
  subjectResourceCount: number;
  statusRules: Array<{
    traceStatus: HarnessStatus;
    commitStatus: HarnessCommitStatus;
  }>;
  resourceRules: Array<{
    resourceType: HarnessResourceType;
    committedAttemptedCount: number;
    committedResourceCount: number;
    notCommittedAttemptedMin: number;
    notCommittedAttemptedMax: number;
  }>;
}

export const HARNESS_OPERATION_COMMIT_POLICIES = deepFreeze({
  "document_parse:document_parse:DocumentProcessRuntimeOutput:document-process-runtime-output-v1:DocumentProcessCommittedProjection:document-process-committed-projection-v1": {
    workflow: "document_parse",
    stage: "document_parse",
    traceContract: { name: "DocumentProcessRuntimeOutput", version: "document-process-runtime-output-v1" },
    payloadContract: { name: "DocumentProcessCommittedProjection", version: "document-process-committed-projection-v1" },
    projectionContract: { name: "DocumentProcessCommittedProjection", version: "document-process-committed-projection-v1" },
    bindingContract: { name: "DocumentProcessOperationBinding", version: "document-process-operation-binding-v1" },
    digestScope: "committed_projection",
    evidenceScope: "complete_transaction",
    subjectResourceType: "frontend_request",
    subjectResourceCount: 1,
    statusRules: [
      { traceStatus: "failed", commitStatus: "not_committed" },
      { traceStatus: "passed", commitStatus: "committed" },
      { traceStatus: "repaired", commitStatus: "committed" },
    ],
    resourceRules: [{ resourceType: "document", committedAttemptedCount: 1, committedResourceCount: 1, notCommittedAttemptedMin: 1, notCommittedAttemptedMax: 1 }],
  },
  "planning:plan_generation:LearningPlanRuntimeOutput:learning-plan-runtime-output-v1:LearningPlanCommittedProjection:learning-plan-committed-projection-v1": {
    workflow: "planning",
    stage: "plan_generation",
    traceContract: { name: "LearningPlanRuntimeOutput", version: "learning-plan-runtime-output-v1" },
    payloadContract: { name: "LearningPlanCommittedProjection", version: "learning-plan-committed-projection-v1" },
    projectionContract: { name: "LearningPlanCommittedProjection", version: "learning-plan-committed-projection-v1" },
    bindingContract: { name: "LearningPlanOperationBinding", version: "learning-plan-operation-binding-v1" },
    digestScope: "committed_projection",
    evidenceScope: "complete_transaction",
    subjectResourceType: "frontend_request",
    subjectResourceCount: 1,
    statusRules: [
      { traceStatus: "failed", commitStatus: "not_committed" },
      { traceStatus: "passed", commitStatus: "committed" },
      { traceStatus: "repaired", commitStatus: "committed" },
    ],
    resourceRules: [{ resourceType: "learning_plan", committedAttemptedCount: 1, committedResourceCount: 1, notCommittedAttemptedMin: 1, notCommittedAttemptedMax: 1 }],
  },
  "tavern:actor_reply:TavernActorReply:tavern-actor-reply-v2:TavernPersonaMessageCommittedProjection:tavern-persona-message-committed-projection-v1": {
    workflow: "tavern",
    stage: "actor_reply",
    traceContract: {
      name: "TavernActorReply",
      version: "tavern-actor-reply-v2",
    },
    payloadContract: {
      name: "TavernPersonaMessageCommittedProjection",
      version: "tavern-persona-message-committed-projection-v1",
    },
    projectionContract: {
      name: "TavernPersonaMessageCommittedProjection",
      version: "tavern-persona-message-committed-projection-v1",
    },
    bindingContract: {
      name: "TavernPersonaMessageCommitBinding",
      version: "tavern-persona-message-commit-binding-v1",
    },
    digestScope: "committed_projection",
    evidenceScope: "primary_output_only",
    subjectResourceType: "tavern_room",
    subjectResourceCount: 1,
    statusRules: [
      { traceStatus: "failed", commitStatus: "not_committed" },
      { traceStatus: "passed", commitStatus: "committed" },
      { traceStatus: "repaired", commitStatus: "committed" },
    ],
    resourceRules: [
      {
        resourceType: "tavern_message",
        committedAttemptedCount: 1,
        committedResourceCount: 1,
        notCommittedAttemptedMin: 1,
        notCommittedAttemptedMax: 1,
      },
    ],
  },
  "study_chat:study_chat_reply:StudyChatReply:study-chat-reply-trace-v1:StudySessionTurnCommittedProjection:study-chat-turn-committed-projection-v1": {
    workflow: "study_chat",
    stage: "study_chat_reply",
    traceContract: { name: "StudyChatReply", version: "study-chat-reply-trace-v1" },
    payloadContract: { name: "StudySessionTurnCommittedProjection", version: "study-chat-turn-committed-projection-v1" },
    projectionContract: { name: "StudySessionTurnCommittedProjection", version: "study-chat-turn-committed-projection-v1" },
    bindingContract: { name: "StudyChatOperationBinding", version: "study-chat-operation-binding-v1" },
    digestScope: "committed_projection",
    evidenceScope: "primary_output_only",
    subjectResourceType: "study_session",
    subjectResourceCount: 1,
    statusRules: [
      { traceStatus: "failed", commitStatus: "not_committed" },
      { traceStatus: "passed", commitStatus: "committed" },
      { traceStatus: "repaired", commitStatus: "committed" },
    ],
    resourceRules: [{ resourceType: "study_session", committedAttemptedCount: 1, committedResourceCount: 1, notCommittedAttemptedMin: 1, notCommittedAttemptedMax: 1 }],
  },
} as const satisfies Record<string, HarnessOperationCommitPolicy>);

export interface HarnessOperationCommitPolicyRegistrySnapshot {
  schema_name: "HarnessOperationCommitPolicyRegistry";
  schema_version: "harness-operation-commit-policies-v1";
  policies: Array<{
    workflow: HarnessWorkflow;
    stage: HarnessStage;
    trace_contract: HarnessContractRef;
    payload_contract: HarnessContractRef;
    projection_contract: HarnessContractRef;
    binding_contract: HarnessContractRef;
    digest_scope: HarnessDigestScope;
    evidence_scope: HarnessOperationEvidenceScope;
    subject_resource_type: HarnessResourceType;
    subject_resource_count: number;
    status_rules: Array<{
      trace_status: HarnessStatus;
      commit_status: HarnessCommitStatus;
    }>;
    resource_rules: Array<{
      resource_type: HarnessResourceType;
      committed_attempted_count: number;
      committed_resource_count: number;
      not_committed_attempted_min: number;
      not_committed_attempted_max: number;
    }>;
  }>;
}

export function harnessOperationCommitPolicyRegistrySnapshot(): HarnessOperationCommitPolicyRegistrySnapshot {
  return {
    schema_name: "HarnessOperationCommitPolicyRegistry",
    schema_version: "harness-operation-commit-policies-v1",
    policies: [...Object.values(HARNESS_OPERATION_COMMIT_POLICIES)]
      .sort((left, right) => {
        const leftKey = `${left.workflow}:${left.stage}:${left.traceContract.name}:${left.traceContract.version}:${left.payloadContract.name}:${left.payloadContract.version}`;
        const rightKey = `${right.workflow}:${right.stage}:${right.traceContract.name}:${right.traceContract.version}:${right.payloadContract.name}:${right.payloadContract.version}`;
        return leftKey.localeCompare(rightKey);
      })
      .map((policy) => ({
      workflow: policy.workflow,
      stage: policy.stage,
      trace_contract: policy.traceContract,
      payload_contract: policy.payloadContract,
      projection_contract: policy.projectionContract,
      binding_contract: policy.bindingContract,
      digest_scope: policy.digestScope,
      evidence_scope: policy.evidenceScope,
      subject_resource_type: policy.subjectResourceType,
      subject_resource_count: policy.subjectResourceCount,
      status_rules: policy.statusRules.map((item) => ({
        trace_status: item.traceStatus,
        commit_status: item.commitStatus,
      })),
      resource_rules: policy.resourceRules.map((item) => ({
        resource_type: item.resourceType,
        committed_attempted_count: item.committedAttemptedCount,
        committed_resource_count: item.committedResourceCount,
        not_committed_attempted_min: item.notCommittedAttemptedMin,
        not_committed_attempted_max: item.notCommittedAttemptedMax,
      })),
      })),
  };
}

export interface TavernPersonaMessageCommitBindingV1 {
  schemaName: "TavernPersonaMessageCommitBinding";
  schemaVersion: "tavern-persona-message-commit-binding-v1";
  operationId: string;
  effectBatchId: string;
  roomId: string;
  messageId: string;
  sequence: number;
  runId: string;
  stepIndex: number;
  replyToMessageId: string;
  authorKind: "persona";
  personaId: string;
  personaName: string;
  clientRequestId: string;
  createdAt: string;
  projectionDigest: string;
}

export interface HarnessContractRef {
  name: string;
  version: string;
}

export interface HarnessResourceRef {
  resourceType: string;
  resourceId: string;
  revision: number | null;
}

export interface HarnessSnapshotRef {
  artifactType: string;
  artifactId: string;
  schemaVersion: string;
  digestAlgorithm: "sha256";
  payloadDigest: string;
}

export interface HarnessContextEnvelope {
  schemaName: string;
  schemaVersion: string;
  workflow: HarnessWorkflow;
  operationId: string;
  subjectRefs: HarnessResourceRef[];
  componentVersions: HarnessContractRef[];
  snapshotRefs: HarnessSnapshotRef[];
  digestAlgorithm: "sha256";
  inputDigest: string;
  contextDigest: string;
  policyVersion: string | null;
  promptVersion: string | null;
}

export interface HarnessResourceRefV3 {
  resourceType: HarnessResourceType;
  resourceId: string;
  revision: number | null;
}

export interface HarnessSnapshotRefV3 {
  artifactType: HarnessArtifactType;
  artifactId: string;
  contract: HarnessContractRef;
  digestAlgorithm: "sha256";
  payloadDigest: string;
}

export interface HarnessContextEnvelopeV3 {
  contextContract: {
    name: "HarnessContextEnvelopeV3";
    version: "harness-context-v3";
  };
  workflow: HarnessWorkflow;
  stage: HarnessStage;
  operationId: string;
  inputContract: HarnessContractRef;
  subjectRefs: HarnessResourceRefV3[];
  componentVersions: HarnessContractRef[];
  snapshotRefs: HarnessSnapshotRefV3[];
  digestAlgorithm: "sha256";
  digestContract: {
    name: "HarnessContextManifestDigest";
    version: "harness-context-manifest-digest-v1";
  };
  inputDigest: string;
  contextDigest: string;
  policyContract: HarnessContractRef | null;
  promptContract: HarnessContractRef | null;
}

export interface HarnessCheckV2 {
  name: string;
  status: HarnessCheckStatus;
  code: string;
  message: string;
}

export interface HarnessAttempt {
  attemptId: string;
  attemptIndex: number;
  phase: HarnessAttemptPhase;
  status: HarnessAttemptStatus;
  outputDigest: string | null;
  errorCode: string;
  durationMs: number;
}

export interface HarnessCommittedResourceRef {
  resourceType: string;
  resourceId: string;
  expectedRevision: number | null;
  committedRevision: number | null;
  firstSequence: number | null;
  lastSequence: number | null;
  payloadDigest: string;
}

export interface HarnessCommittedResourceRefV3
  extends Omit<HarnessCommittedResourceRef, "resourceType"> {
  resourceType: HarnessResourceType;
}

export interface HarnessCommitEvidence {
  status: HarnessCommitStatus;
  effectBatchId: string | null;
  payloadContract: HarnessContractRef | null;
  digestAlgorithm: "sha256" | null;
  digestScope: HarnessDigestScope | null;
  attemptedResourceRefs: HarnessResourceRef[];
  committedResources: HarnessCommittedResourceRef[];
  payloadDigest: string | null;
  committedAt: string | null;
  rollbackReasonCode: string;
  rolledBackAt: string | null;
}

export interface HarnessCommitEvidenceV3
  extends Omit<
    HarnessCommitEvidence,
    "attemptedResourceRefs" | "committedResources"
  > {
  attemptedResourceRefs: HarnessResourceRefV3[];
  committedResources: HarnessCommittedResourceRefV3[];
}

export interface HarnessTraceV2 {
  traceSchemaVersion: "harness-trace-v2";
  traceId: string;
  operationId: string;
  parentTraceId: string | null;
  workflow: HarnessWorkflow;
  stage: string;
  status: HarnessStatus;
  contract: HarnessContractRef;
  context: HarnessContextEnvelope;
  outputDigest: string | null;
  checks: HarnessCheckV2[];
  attemptRecords: HarnessAttempt[];
  recoveryStrategy: string;
  errorCode: string;
  durationMs: number;
  commitEvidence: HarnessCommitEvidence;
  startedAt: string;
  completedAt: string;
}

export interface HarnessTraceV3
  extends Omit<
    HarnessTraceV2,
    "traceSchemaVersion" | "stage" | "context" | "commitEvidence"
  > {
  traceSchemaVersion: "harness-trace-v3";
  stage: HarnessStage;
  context: HarnessContextEnvelopeV3;
  commitEvidence: HarnessCommitEvidenceV3;
}

export interface HarnessProposalEnvelope<Proposal> {
  operationId: string;
  contract: HarnessContractRef;
  contextDigest: string;
  payloadDigest: string;
  proposal: Proposal;
}

export type HarnessTraceWire = HarnessTraceV1 | HarnessTraceV2 | HarnessTraceV3;

/** Existing runtime consumers still receive v1 until an explicit decoder migration. */
export type HarnessTrace = HarnessTraceV1;

// Compatibility name for existing consumers that imported HarnessCheck.
export type HarnessCheck = HarnessCheckV1;
