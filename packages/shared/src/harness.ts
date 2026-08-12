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

export const HARNESS_COMPONENT_REGISTRATIONS = {
  document_parser: { ownerModule: "app.services.document_parser", contract: null },
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
  ocr_engine: { ownerModule: "app.services.ocr_engine", contract: null },
  study_unit_cleaner: { ownerModule: "app.services.study_arrangement", contract: null },
  planning_prompt: { ownerModule: "app.services.plan_prompt", contract: null },
  planning_toolset: {
    ownerModule: "app.services.plan_tool_runtime",
    contract: { name: "planning_toolset", version: "planning-toolset-v1" },
  },
  planning_tool_runtime: {
    ownerModule: "app.services.plan_tool_runtime",
    contract: { name: "planning_tool_runtime", version: "planning-tool-runtime-v1" },
  },
  persona_compiler: { ownerModule: "app.services.persona_cards", contract: null },
  scene_compiler: { ownerModule: "app.services.scene_setup", contract: null },
  study_chat_prompt: { ownerModule: "app.services.study_session_prompt", contract: null },
  study_chat_toolset: {
    ownerModule: "app.services.study_session_chat_runtime",
    contract: null,
  },
  tavern_persona_compiler: {
    ownerModule: "app.services.tavern_harness",
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
  frontend_decoder: { ownerModule: "apps.web.lib.api", contract: null },
} as const satisfies Record<HarnessComponentName, HarnessComponentRegistration>;

export const HARNESS_OPERATION_STAGE_REGISTRATIONS = {
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
} as const satisfies Record<HarnessOperationStageKey, HarnessOperationStageRegistration>;

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
  | "unsupported";
export type HarnessCommitEvidencePolicy =
  | "revision"
  | "sequence"
  | "unsupported";
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
    commitEvidence: "unsupported",
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
    commitEvidence: "unsupported",
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
    semantics: "unversioned_mutable",
    contextEvidence: "unsupported",
    commitEvidence: "unsupported",
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
    contextEvidence: "unsupported",
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
