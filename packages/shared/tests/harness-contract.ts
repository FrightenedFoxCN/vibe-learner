import type {
  HarnessProposalEnvelope,
  HarnessTraceV1,
  HarnessTraceV2,
  HarnessTraceWire,
} from "../src/harness";

const legacyV1 = {
  version: "tavern-harness-v1/tavern-actor-prompt-v1",
  workflow: "tavern",
  stage: "actor_reply",
  status: "passed",
  schemaName: "TavernActorReply",
  inputDigest: "legacy-input-digest",
  contextDigest: "legacy-context-digest",
  checks: [
    {
      name: "speaker_identity",
      status: "passed",
      code: "",
      message: "说话者归属有效。",
    },
  ],
  attempts: 1,
  recoveryStrategy: "none",
  durationMs: 12,
} satisfies HarnessTraceV1;

const repairedCommittedV2 = {
  traceSchemaVersion: "harness-trace-v2",
  traceId: "trace-tavern-actor-2",
  operationId: "operation-tavern-turn-1",
  parentTraceId: "trace-tavern-run-1",
  workflow: "tavern",
  stage: "actor_reply",
  status: "repaired",
  contract: {
    name: "TavernActorReply",
    version: "tavern-actor-reply-v1",
  },
  context: {
    schemaName: "TavernActorContext",
    schemaVersion: "tavern-actor-context-v1",
    workflow: "tavern",
    operationId: "operation-tavern-turn-1",
    subjectRefs: [
      { resourceType: "tavern_room", resourceId: "room-1", revision: 4 },
    ],
    componentVersions: [
      { name: "persona_compiler", version: "tavern-persona-compiler-v1" },
      { name: "speaker_scheduler", version: "tavern-schedule-v1" },
    ],
    snapshotRefs: [
      {
        artifactType: "tavern_context_snapshot",
        artifactId: "room-1-revision-4",
        schemaVersion: "tavern-context-snapshot-v1",
        digestAlgorithm: "sha256",
        payloadDigest: "2".repeat(64),
      },
    ],
    digestAlgorithm: "sha256",
    inputDigest: "1".repeat(64),
    contextDigest: "2".repeat(64),
    policyVersion: "tavern-harness-v1",
    promptVersion: "tavern-actor-prompt-v1",
  },
  outputDigest: "3".repeat(64),
  checks: [
    {
      name: "addressed_participants",
      status: "warning",
      code: "scheduled_reply_target_restored",
      message: "已恢复服务端安排的上一位说话者目标。",
    },
  ],
  attemptRecords: [
    {
      attemptId: "attempt-generate-1",
      attemptIndex: 1,
      phase: "generate",
      status: "passed",
      outputDigest: "4".repeat(64),
      errorCode: "",
      durationMs: 40,
    },
    {
      attemptId: "attempt-validate-1",
      attemptIndex: 2,
      phase: "validate",
      status: "failed",
      outputDigest: "4".repeat(64),
      errorCode: "scheduled_reply_target_missing",
      durationMs: 2,
    },
    {
      attemptId: "attempt-repair-1",
      attemptIndex: 3,
      phase: "repair",
      status: "passed",
      outputDigest: "3".repeat(64),
      errorCode: "",
      durationMs: 1,
    },
    {
      attemptId: "attempt-validate-2",
      attemptIndex: 4,
      phase: "validate",
      status: "passed",
      outputDigest: "3".repeat(64),
      errorCode: "",
      durationMs: 1,
    },
    {
      attemptId: "attempt-commit-1",
      attemptIndex: 5,
      phase: "commit",
      status: "passed",
      outputDigest: "f0c384a84c2fc09428614ddb0bddd8963201eb90ff659802470b28781933b04f",
      errorCode: "",
      durationMs: 5,
    },
  ],
  recoveryStrategy: "restore_scheduled_reply_target",
  errorCode: "",
  durationMs: 49,
  commitEvidence: {
    status: "committed",
    effectBatchId: "tavern-step-commit-run-1-step-2",
    payloadContract: {
      name: "TavernActorCommitBatch",
      version: "tavern-actor-commit-v1",
    },
    digestAlgorithm: "sha256",
    digestScope: "committed_batch",
    attemptedResourceRefs: [
      { resourceType: "tavern_message", resourceId: "message-10", revision: null },
      { resourceType: "tavern_room", resourceId: "room-1", revision: 4 },
    ],
    committedResources: [
      {
        resourceType: "tavern_message",
        resourceId: "message-10",
        expectedRevision: null,
        committedRevision: null,
        firstSequence: 10,
        lastSequence: 10,
        payloadDigest: "5".repeat(64),
      },
      {
        resourceType: "tavern_room",
        resourceId: "room-1",
        expectedRevision: 4,
        committedRevision: 5,
        firstSequence: null,
        lastSequence: null,
        payloadDigest: "6".repeat(64),
      },
    ],
    payloadDigest: "f0c384a84c2fc09428614ddb0bddd8963201eb90ff659802470b28781933b04f",
    committedAt: "2026-08-12T08:00:00Z",
    rollbackReasonCode: "",
    rolledBackAt: null,
  },
  startedAt: "2026-08-12T07:59:59Z",
  completedAt: "2026-08-12T08:00:00Z",
} satisfies HarnessTraceV2;

const proposalEnvelope = {
  operationId: "operation-example-1",
  contract: { name: "ExampleProposal", version: "example-proposal-v1" },
  contextDigest: "c".repeat(64),
  payloadDigest: "d".repeat(64),
  proposal: { text: "validated content" },
} satisfies HarnessProposalEnvelope<{ text: string }>;

const wireFixtures: HarnessTraceWire[] = [legacyV1, repairedCommittedV2];

void proposalEnvelope;
void wireFixtures;
