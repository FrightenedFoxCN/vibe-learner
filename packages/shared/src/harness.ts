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
  | "ocr_page"
  | "study_unit_cleanup"
  | "plan_generation"
  | "persona_generation"
  | "scene_generation"
  | "study_chat_reply"
  | "actor_reply"
  | "response_decode";

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
