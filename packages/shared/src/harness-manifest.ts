import type {
  HarnessArtifactType,
  HarnessComponentName,
  HarnessContractRef,
  HarnessStage,
  HarnessWorkflow,
} from "./harness";

export const HARNESS_WORKFLOW_MANIFEST_SCHEMA_VERSION =
  "harness-workflow-manifest-v1" as const;
export const HARNESS_WORKFLOW_MANIFEST_EVAL_CASE_VERSION =
  "harness-eval-case-v1" as const;
export const HARNESS_WORKFLOW_MANIFEST_TOOL_MANIFEST_VERSION =
  "tool-manifest-v1" as const;
export const TAVERN_IDENTITY_EVAL_SUITE = {
  name: "tavern_identity_eval",
  version: "tavern-identity-eval-v1",
} as const satisfies HarnessContractRef;
export const PLANNING_TOOL_EVAL_SUITE = {
  name: "planning_tool_eval",
  version: "planning-tool-eval-v1",
} as const satisfies HarnessContractRef;

export type HarnessManifestSlotStatus =
  | "registered"
  | "not_applicable"
  | "unregistered";

export type HarnessManifestNotApplicableReason =
  | "no_model_proposal"
  | "no_prompt"
  | "no_policy"
  | "no_tools"
  | "no_artifacts"
  | "no_effects"
  | "no_commit"
  | "no_decoder";

export type HarnessManifestUnregisteredReason =
  | "workflow_not_audited"
  | "contract_not_registered"
  | "adapter_not_registered"
  | "component_contract_not_registered"
  | "policy_not_registered"
  | "artifact_allowlist_not_registered"
  | "effect_adapter_not_registered"
  | "commit_policy_not_registered"
  | "decoder_not_registered"
  | "eval_suite_not_registered";

export interface HarnessManifestRegisteredContractSlotV1 {
  status: "registered";
  contract: HarnessContractRef;
}

export interface HarnessManifestRegisteredStringSlotV1 {
  status: "registered";
  value: string;
}

export interface HarnessManifestRegisteredArtifactSlotV1 {
  status: "registered";
  artifact_types: HarnessArtifactType[];
}

export interface HarnessManifestRegisteredContractListSlotV1 {
  status: "registered";
  contracts: HarnessContractRef[];
}

export interface HarnessManifestNotApplicableSlotV1 {
  status: "not_applicable";
  reason: HarnessManifestNotApplicableReason;
}

export interface HarnessManifestUnregisteredSlotV1 {
  status: "unregistered";
  reason: HarnessManifestUnregisteredReason;
}

export type HarnessManifestContractSlotV1 =
  | HarnessManifestRegisteredContractSlotV1
  | HarnessManifestNotApplicableSlotV1
  | HarnessManifestUnregisteredSlotV1;
export type HarnessManifestStringSlotV1 =
  | HarnessManifestRegisteredStringSlotV1
  | HarnessManifestNotApplicableSlotV1
  | HarnessManifestUnregisteredSlotV1;
export type HarnessManifestArtifactSlotV1 =
  | HarnessManifestRegisteredArtifactSlotV1
  | HarnessManifestNotApplicableSlotV1
  | HarnessManifestUnregisteredSlotV1;
export type HarnessManifestContractListSlotV1 =
  | HarnessManifestRegisteredContractListSlotV1
  | HarnessManifestNotApplicableSlotV1
  | HarnessManifestUnregisteredSlotV1;

export interface HarnessManifestCommitPolicyKeyV1 {
  workflow: HarnessWorkflow;
  stage: HarnessStage;
  trace_contract: HarnessContractRef;
  payload_contract: HarnessContractRef;
}

export interface HarnessManifestRegisteredCommitPolicySlotV1 {
  status: "registered";
  key: HarnessManifestCommitPolicyKeyV1;
}

export type HarnessManifestCommitPolicySlotV1 =
  | HarnessManifestRegisteredCommitPolicySlotV1
  | HarnessManifestNotApplicableSlotV1
  | HarnessManifestUnregisteredSlotV1;

export interface HarnessManifestComponentContractV1 {
  component_name: HarnessComponentName;
  contract: HarnessManifestContractSlotV1;
}

export interface HarnessManifestAttemptCeilingV1 {
  max_attempts: number;
  max_repair_attempts: number;
}

export interface HarnessManifestExecutionBudgetV1 {
  max_provider_calls: number;
  max_tool_calls: number;
  max_input_tokens: number;
  max_output_tokens: number;
  max_wall_time_ms: number;
  per_call_timeout_ms: number;
}

export interface HarnessWorkflowManifestEntryV1 {
  key: string;
  workflow: HarnessWorkflow;
  stage: HarnessStage;
  registration: HarnessManifestContractSlotV1;
  owner_module: string;
  owner_adapter: HarnessManifestContractSlotV1;
  input_contract: HarnessManifestContractSlotV1;
  proposal_contract: HarnessManifestContractSlotV1;
  output_contract: HarnessManifestContractSlotV1;
  component_contracts: HarnessManifestComponentContractV1[];
  prompt_contract: HarnessManifestContractSlotV1;
  policy_contract: HarnessManifestContractSlotV1;
  toolset_contract: HarnessManifestContractSlotV1;
  attempt_ceiling: HarnessManifestAttemptCeilingV1;
  execution_budget: HarnessManifestExecutionBudgetV1;
  allowed_artifact_types: HarnessManifestArtifactSlotV1;
  allowed_effect_adapters: HarnessManifestContractListSlotV1;
  commit_policy: HarnessManifestCommitPolicySlotV1;
  decoder_route: HarnessManifestStringSlotV1;
  eval_route: HarnessManifestStringSlotV1;
  eval_suites: HarnessManifestContractListSlotV1;
}

export interface HarnessWorkflowManifestV1 {
  schema_name: "HarnessWorkflowManifest";
  schema_version: typeof HARNESS_WORKFLOW_MANIFEST_SCHEMA_VERSION;
  stages: HarnessWorkflowManifestEntryV1[];
}

type StageVocabulary = {
  workflow: HarnessWorkflow;
  stage: HarnessStage;
  ownerModule: string;
  components: Array<{
    name: HarnessComponentName;
    contract: HarnessContractRef | null;
  }>;
  evalRoute: string;
};

const STAGE_VOCABULARY: StageVocabulary[] = [
  { workflow: "planning", stage: "plan_revision", ownerModule: "app.services.plan_revision", components: [{ name: "plan_revision_patch", contract: { name: "plan_revision_patch", version: "plan-revision-patch-v1" } }], evalRoute: "planning.plan_revision" },
  {
    workflow: "document_parse",
    stage: "document_parse",
    ownerModule: "app.services.document_parser",
    components: [{ name: "document_parser", contract: { name: "document_parser", version: "document-parser-v1" } }],
    evalRoute: "document.parse",
  },
  {
    workflow: "document_parse",
    stage: "page_extraction",
    ownerModule: "app.services.document_parser",
    components: [
      {
        name: "document_page_extractor",
        contract: {
          name: "document_page_extractor",
          version: "document-page-extractor-v1",
        },
      },
    ],
    evalRoute: "document.page_extraction",
  },
  {
    workflow: "document_parse",
    stage: "section_detection",
    ownerModule: "app.services.document_parser",
    components: [
      {
        name: "document_section_detector",
        contract: {
          name: "document_section_detector",
          version: "document-section-detector-v1",
        },
      },
    ],
    evalRoute: "document.section_detection",
  },
  {
    workflow: "document_parse",
    stage: "chunk_building",
    ownerModule: "app.services.document_parser",
    components: [
      {
        name: "document_chunk_builder",
        contract: {
          name: "document_chunk_builder",
          version: "document-chunk-builder-v1",
        },
      },
    ],
    evalRoute: "document.chunk_building",
  },
  {
    workflow: "ocr",
    stage: "ocr_page",
    ownerModule: "app.services.ocr_engine",
    components: [{ name: "ocr_engine", contract: { name: "ocr_engine", version: "ocr-engine-v1" } }],
    evalRoute: "document.ocr_page",
  },
  {
    workflow: "study_unit_cleanup",
    stage: "study_unit_cleanup",
    ownerModule: "app.services.study_arrangement",
    components: [{ name: "study_unit_cleaner", contract: { name: "study_unit_cleaner", version: "study-unit-cleaner-v1" } }],
    evalRoute: "document.study_unit_cleanup",
  },
  {
    workflow: "planning",
    stage: "plan_generation",
    ownerModule: "app.services.model_provider",
    components: [
      { name: "planning_prompt", contract: { name: "planning_prompt", version: "planning-prompt-v1" } },
      {
        name: "planning_toolset",
        contract: { name: "planning_toolset", version: "planning-toolset-v1" },
      },
    ],
    evalRoute: "planning.plan_generation",
  },
  {
    workflow: "planning",
    stage: "planning_tool_execution",
    ownerModule: "app.services.plan_tool_runtime",
    components: [
      {
        name: "planning_tool_runtime",
        contract: {
          name: "planning_tool_runtime",
          version: "planning-tool-runtime-v1",
        },
      },
      {
        name: "planning_toolset",
        contract: { name: "planning_toolset", version: "planning-toolset-v1" },
      },
    ],
    evalRoute: "planning.tool_execution",
  },
  {
    workflow: "persona",
    stage: "persona_generation",
    ownerModule: "app.services.persona_cards",
    components: [{ name: "persona_compiler", contract: { name: "persona_compiler", version: "persona-compiler-v1" } }],
    evalRoute: "persona.generation",
  },
  {
    workflow: "scene",
    stage: "scene_generation",
    ownerModule: "app.services.scene_setup",
    components: [{ name: "scene_compiler", contract: { name: "scene_compiler", version: "scene-compiler-v1" } }],
    evalRoute: "scene.generation",
  },
  {
    workflow: "study_chat",
    stage: "study_chat_reply",
    ownerModule: "app.services.study_sessions",
    components: [
      { name: "study_chat_prompt", contract: { name: "study_chat_prompt", version: "study-chat-prompt-v1" } },
      { name: "study_chat_toolset", contract: { name: "study_chat_toolset", version: "study-chat-toolset-v1" } },
    ],
    evalRoute: "study_chat.reply",
  },
  {
    workflow: "tavern",
    stage: "actor_reply",
    ownerModule: "app.services.tavern",
    components: [
      {
        name: "tavern_actor_prompt",
        contract: { name: "tavern_actor_prompt", version: "tavern-actor-v1" },
      },
      {
        name: "tavern_persona_compiler",
        contract: {
          name: "tavern_persona_compiler",
          version: "tavern-persona-compiler-v1",
        },
      },
      {
        name: "tavern_scheduler",
        contract: { name: "tavern_scheduler", version: "tavern-schedule-v1" },
      },
    ],
    evalRoute: "tavern.actor_reply",
  },
  {
    workflow: "frontend_decode",
    stage: "response_decode",
    ownerModule: "apps.web.lib.api",
    components: [{ name: "frontend_decoder", contract: { name: "frontend_decoder", version: "frontend-decoder-v1" } }],
    evalRoute: "frontend.response_decode",
  },
];

const contract = (name: string, version: string): HarnessContractRef => ({
  name,
  version,
});
const registeredContract = (
  name: string,
  version: string,
): HarnessManifestRegisteredContractSlotV1 => ({
  status: "registered",
  contract: contract(name, version),
});
const registeredString = (
  value: string,
): HarnessManifestRegisteredStringSlotV1 => ({ status: "registered", value });
const notApplicable = (
  reason: HarnessManifestNotApplicableReason,
): HarnessManifestNotApplicableSlotV1 => ({ status: "not_applicable", reason });
const unregistered = (
  reason: HarnessManifestUnregisteredReason,
): HarnessManifestUnregisteredSlotV1 => ({ status: "unregistered", reason });
const artifactAllowlist = (
  ...artifactTypes: HarnessArtifactType[]
): HarnessManifestRegisteredArtifactSlotV1 => ({
  status: "registered",
  artifact_types: [...artifactTypes].sort(),
});
const registeredContracts = (
  ...contracts: HarnessContractRef[]
): HarnessManifestRegisteredContractListSlotV1 => ({
  status: "registered",
  contracts: [...contracts].sort((left, right) =>
    `${left.name}@${left.version}`.localeCompare(`${right.name}@${right.version}`),
  ),
});

const DEFAULT_ATTEMPTS: HarnessManifestAttemptCeilingV1 = {
  max_attempts: 3,
  max_repair_attempts: 2,
};
const DEFAULT_BUDGET: HarnessManifestExecutionBudgetV1 = {
  max_provider_calls: 3,
  max_tool_calls: 16,
  max_input_tokens: 64_000,
  max_output_tokens: 8_000,
  max_wall_time_ms: 180_000,
  per_call_timeout_ms: 120_000,
};
const TOOL_MANIFEST_SLOT = registeredContract(
  "ToolManifestRegistry",
  HARNESS_WORKFLOW_MANIFEST_TOOL_MANIFEST_VERSION,
);

const vocabularyFor = (
  workflow: HarnessWorkflow,
  stage: HarnessStage,
): StageVocabulary => {
  const entry = STAGE_VOCABULARY.find(
    (candidate) => candidate.workflow === workflow && candidate.stage === stage,
  );
  if (!entry) {
    throw new Error("harness_workflow_manifest_stage_unknown");
  }
  return entry;
};

const componentContracts = (
  workflow: HarnessWorkflow,
  stage: HarnessStage,
): HarnessManifestComponentContractV1[] =>
  vocabularyFor(workflow, stage).components
    .map((component) => ({
      component_name: component.name,
      contract: component.contract
        ? registeredContract(component.contract.name, component.contract.version)
        : unregistered("component_contract_not_registered"),
    }))
    .sort((left, right) => left.component_name.localeCompare(right.component_name));

const unregisteredEntry = (
  workflow: HarnessWorkflow,
  stage: HarnessStage,
  options: {
    artifactTypes: HarnessArtifactType[];
    prompt?: HarnessManifestContractSlotV1;
    toolset?: HarnessManifestContractSlotV1;
    noEffects?: boolean;
    noCommit?: boolean;
    evalSuites?: HarnessContractRef[];
  },
): HarnessWorkflowManifestEntryV1 => {
  const vocabulary = vocabularyFor(workflow, stage);
  return {
    key: `${workflow}:${stage}`,
    workflow,
    stage,
    registration: unregistered("workflow_not_audited"),
    owner_module: vocabulary.ownerModule,
    owner_adapter: unregistered("adapter_not_registered"),
    input_contract: unregistered("contract_not_registered"),
    proposal_contract: unregistered("contract_not_registered"),
    output_contract: unregistered("contract_not_registered"),
    component_contracts: componentContracts(workflow, stage),
    prompt_contract: options.prompt ?? notApplicable("no_prompt"),
    policy_contract: unregistered("policy_not_registered"),
    toolset_contract: options.toolset ?? notApplicable("no_tools"),
    attempt_ceiling: { ...DEFAULT_ATTEMPTS },
    execution_budget: { ...DEFAULT_BUDGET },
    allowed_artifact_types: artifactAllowlist(...options.artifactTypes),
    allowed_effect_adapters: options.noEffects
      ? notApplicable("no_effects")
      : unregistered("effect_adapter_not_registered"),
    commit_policy: options.noCommit
      ? notApplicable("no_commit")
      : unregistered("commit_policy_not_registered"),
    decoder_route: unregistered("decoder_not_registered"),
    eval_route: registeredString(vocabulary.evalRoute),
    eval_suites: options.evalSuites?.length
      ? registeredContracts(...options.evalSuites)
      : unregistered("eval_suite_not_registered"),
  };
};

const TAVERN_ENTRY: HarnessWorkflowManifestEntryV1 = {
  key: "tavern:actor_reply",
  workflow: "tavern",
  stage: "actor_reply",
  registration: registeredContract(
    "TavernActorReplyWorkflowManifestEntry",
    "tavern-actor-reply-workflow-manifest-v1",
  ),
  owner_module: "app.services.tavern",
  owner_adapter: registeredContract(
    "TavernActorWorkflowAdapter",
    "tavern-actor-workflow-adapter-v1",
  ),
  input_contract: registeredContract(
    "TavernActorInputManifest",
    "tavern-actor-input-manifest-v1",
  ),
  proposal_contract: registeredContract(
    "TavernActorReply",
    "tavern-actor-reply-v1",
  ),
  output_contract: registeredContract(
    "TavernPersonaMessageCommittedProjection",
    "tavern-persona-message-committed-projection-v1",
  ),
  component_contracts: componentContracts("tavern", "actor_reply"),
  prompt_contract: registeredContract("TavernActorPrompt", "tavern-actor-v1"),
  policy_contract: registeredContract("TavernHarnessPolicy", "tavern-harness-v1"),
  toolset_contract: notApplicable("no_tools"),
  attempt_ceiling: { max_attempts: 3, max_repair_attempts: 2 },
  execution_budget: {
    max_provider_calls: 3,
    max_tool_calls: 0,
    max_input_tokens: 24_000,
    max_output_tokens: 4_000,
    max_wall_time_ms: 180_000,
    per_call_timeout_ms: 120_000,
  },
  allowed_artifact_types: artifactAllowlist(
    "persona_snapshot",
    "scene_snapshot",
    "tavern_room_snapshot",
    "tavern_transcript",
  ),
  allowed_effect_adapters: notApplicable("no_effects"),
  commit_policy: {
    status: "registered",
    key: {
      workflow: "tavern",
      stage: "actor_reply",
      trace_contract: contract("TavernActorReply", "tavern-actor-reply-v2"),
      payload_contract: contract(
        "TavernPersonaMessageCommittedProjection",
        "tavern-persona-message-committed-projection-v1",
      ),
    },
  },
  decoder_route: registeredString(
    "app.services.tavern_harness.TavernActorHarness",
  ),
  eval_route: registeredString("tavern.actor_reply"),
  eval_suites: registeredContracts(TAVERN_IDENTITY_EVAL_SUITE),
};

const STUDY_ENTRY: HarnessWorkflowManifestEntryV1 = {
  key: "study_chat:study_chat_reply", workflow: "study_chat", stage: "study_chat_reply",
  registration: registeredContract("StudyChatReplyWorkflowManifestEntry", "study-chat-reply-workflow-manifest-v1"),
  owner_module: "app.services.study_sessions",
  owner_adapter: registeredContract("StudyChatWorkflowAdapter", "study-chat-workflow-adapter-v1"),
  input_contract: registeredContract("StudyChatInputManifest", "study-chat-input-manifest-v1"),
  proposal_contract: registeredContract("StudyChatReplyProposal", "study-chat-reply-proposal-v1"),
  output_contract: registeredContract("StudySessionTurnCommittedProjection", "study-chat-turn-committed-projection-v1"),
  component_contracts: componentContracts("study_chat", "study_chat_reply"),
  prompt_contract: registeredContract("StudyChatPrompt", "study-chat-prompt-v1"),
  policy_contract: registeredContract("StudyChatHarnessPolicy", "study-chat-harness-v1"),
  toolset_contract: registeredContract("ToolManifestRegistry", HARNESS_WORKFLOW_MANIFEST_TOOL_MANIFEST_VERSION),
  attempt_ceiling: { max_attempts: 3, max_repair_attempts: 2 },
  execution_budget: { ...DEFAULT_BUDGET },
  allowed_artifact_types: artifactAllowlist("document_upload", "planning_context", "scene_snapshot", "study_session_snapshot"),
  allowed_effect_adapters: registeredContracts(contract("StudyChatEffectBatch", "study-chat-effect-batch-v1")),
  commit_policy: { status: "registered", key: { workflow: "study_chat", stage: "study_chat_reply", trace_contract: contract("StudyChatReply", "study-chat-reply-trace-v1"), payload_contract: contract("StudySessionTurnCommittedProjection", "study-chat-turn-committed-projection-v1") } },
  decoder_route: registeredString("app.services.study_v3.StudyV3ReplyAdapter"),
  eval_route: registeredString("study_chat.reply"),
  eval_suites: registeredContracts(contract("study_chat_eval", "study-chat-eval-v1")),
};

// Independently typed projection: the golden test must compare two sources,
// not compare a fixture to an unchecked cast of that same fixture.
export const STAGE_EVAL_SUITES: Record<string, HarnessContractRef> = {
  "document_parse:document_parse": contract("document_process_regression", "document-process-regression-v1"),
  "document_parse:page_extraction": contract("page_extraction_regression", "page-extraction-regression-v1"),
  "document_parse:section_detection": contract("section_detection_regression", "section-detection-regression-v1"),
  "document_parse:chunk_building": contract("chunk_building_regression", "chunk-building-regression-v1"),
  "ocr:ocr_page": contract("ocr_page_regression", "ocr-page-regression-v1"),
  "study_unit_cleanup:study_unit_cleanup": contract("study_unit_cleanup_regression", "study-unit-cleanup-regression-v1"),
  "planning:plan_generation": contract("plan_generation_regression", "plan-generation-regression-v1"),
  "persona:persona_generation": contract("persona_generation_regression", "persona-generation-regression-v1"),
  "scene:scene_generation": contract("scene_generation_regression", "scene-generation-regression-v1"),
  "frontend_decode:response_decode": contract("frontend_decode_regression", "frontend-decode-regression-v1"),
};

const executableEntry = (
  workflow: HarnessWorkflow,
  stage: HarnessStage,
  options: {
    registration: HarnessContractRef;
    adapter: HarnessContractRef;
    input: HarnessContractRef;
    proposal: HarnessContractRef;
    output: HarnessContractRef;
    artifacts: HarnessArtifactType[];
    decoder: string;
    prompt?: HarnessContractRef;
    policy: HarnessContractRef;
    toolset?: HarnessManifestContractSlotV1;
    commit?: HarnessManifestCommitPolicySlotV1;
    evalSuites?: HarnessContractRef[];
  },
): HarnessWorkflowManifestEntryV1 => ({
  ...unregisteredEntry(workflow, stage, { artifactTypes: options.artifacts, noEffects: true, noCommit: true }),
  registration: registeredContract(options.registration.name, options.registration.version),
  owner_adapter: registeredContract(options.adapter.name, options.adapter.version),
  input_contract: registeredContract(options.input.name, options.input.version),
  proposal_contract: registeredContract(options.proposal.name, options.proposal.version),
  output_contract: registeredContract(options.output.name, options.output.version),
  prompt_contract: options.prompt ? registeredContract(options.prompt.name, options.prompt.version) : notApplicable("no_prompt"),
  policy_contract: registeredContract(options.policy.name, options.policy.version),
  toolset_contract: options.toolset ?? notApplicable("no_tools"),
  commit_policy: options.commit ?? notApplicable("no_commit"),
  decoder_route: registeredString(options.decoder),
  eval_suites: options.evalSuites?.length
    ? registeredContracts(...options.evalSuites)
    : STAGE_EVAL_SUITES[`${workflow}:${stage}`]
      ? registeredContracts(STAGE_EVAL_SUITES[`${workflow}:${stage}`])
      : unregistered("eval_suite_not_registered"),
});

const entries: HarnessWorkflowManifestEntryV1[] = [
  executableEntry("planning", "plan_revision", {
    registration: contract("PlanRevisionManifest", "plan-revision-manifest-v1"),
    adapter: contract("PlanRevisionAdapter", "plan-revision-adapter-v1"),
    input: contract("PlanRevisionInputManifest", "plan-revision-input-v1"),
    proposal: contract("PlanRevisionProposal", "plan-revision-proposal-v1"),
    output: contract("PlanRevisionCommittedProjection", "plan-revision-committed-projection-v1"),
    artifacts: ["planning_context"], decoder: "app.services.plan_revision.PlanRevisionService",
    prompt: contract("PlanRevisionPrompt", "plan-revision-prompt-v1"),
    policy: contract("PlanRevisionPolicy", "plan-revision-policy-v1"),
    evalSuites: [contract("plan_revision_regression", "plan-revision-regression-v1")],
    commit: { status: "registered", key: { workflow: "planning", stage: "plan_revision", trace_contract: contract("PlanRevisionProposal", "plan-revision-proposal-v1"), payload_contract: contract("PlanRevisionCommittedProjection", "plan-revision-committed-projection-v1") } },
  }),
  executableEntry("document_parse", "document_parse", {
    registration: contract("DocumentProcessWorkflowManifestEntry", "document-process-workflow-manifest-v1"),
    adapter: contract("DocumentProcessWorkflowAdapter", "document-process-workflow-adapter-v1"),
    input: contract("DocumentProcessInputManifest", "document-process-input-manifest-v1"),
    proposal: contract("DocumentProcessRuntimeOutput", "document-process-runtime-output-v1"),
    output: contract("DocumentProcessCommittedProjection", "document-process-committed-projection-v1"),
    artifacts: ["document_upload"],
    decoder: "app.services.harness_broad_adoption.DocumentProcessWorkflowAdapter",
    policy: contract("DocumentProcessHarnessPolicy", "document-process-harness-v1"),
    commit: { status: "registered", key: { workflow: "document_parse", stage: "document_parse", trace_contract: contract("DocumentProcessRuntimeOutput", "document-process-runtime-output-v1"), payload_contract: contract("DocumentProcessCommittedProjection", "document-process-committed-projection-v1") } },
  }),
  executableEntry("document_parse", "page_extraction", {
    registration: contract("DocumentPageExtractionWorkflowManifestEntry", "document-page-extraction-workflow-manifest-v1"),
    adapter: contract("DocumentStageWorkflowAdapter", "document-stage-workflow-adapter-v1"),
    input: contract("DocumentStageInputManifest", "document-stage-input-manifest-v1"),
    proposal: contract("DocumentStageEvidence", "document-stage-evidence-v1"),
    output: contract("DocumentStageEvidence", "document-stage-evidence-v1"),
    artifacts: ["document_upload"],
    decoder: "app.services.harness_broad_adoption.HarnessProposalRuntimeService.emit_document_stage_evidence",
    policy: contract("DocumentStageHarnessPolicy", "document-stage-harness-v1"),
  }),
  executableEntry("document_parse", "section_detection", {
    registration: contract("DocumentSectionDetectionWorkflowManifestEntry", "document-section-detection-workflow-manifest-v1"),
    adapter: contract("DocumentStageWorkflowAdapter", "document-stage-workflow-adapter-v1"),
    input: contract("DocumentStageInputManifest", "document-stage-input-manifest-v1"),
    proposal: contract("DocumentStageEvidence", "document-stage-evidence-v1"),
    output: contract("DocumentStageEvidence", "document-stage-evidence-v1"),
    artifacts: ["document_debug", "document_upload"],
    decoder: "app.services.harness_broad_adoption.HarnessProposalRuntimeService.emit_document_stage_evidence",
    policy: contract("DocumentStageHarnessPolicy", "document-stage-harness-v1"),
  }),
  executableEntry("document_parse", "chunk_building", {
    registration: contract("DocumentChunkBuildingWorkflowManifestEntry", "document-chunk-building-workflow-manifest-v1"),
    adapter: contract("DocumentStageWorkflowAdapter", "document-stage-workflow-adapter-v1"),
    input: contract("DocumentStageInputManifest", "document-stage-input-manifest-v1"),
    proposal: contract("DocumentStageEvidence", "document-stage-evidence-v1"),
    output: contract("DocumentStageEvidence", "document-stage-evidence-v1"),
    artifacts: ["document_debug", "document_upload"],
    decoder: "app.services.harness_broad_adoption.HarnessProposalRuntimeService.emit_document_stage_evidence",
    policy: contract("DocumentStageHarnessPolicy", "document-stage-harness-v1"),
  }),
  executableEntry("ocr", "ocr_page", {
    registration: contract("OcrPageWorkflowManifestEntry", "ocr-page-workflow-manifest-v1"),
    adapter: contract("DocumentStageWorkflowAdapter", "document-stage-workflow-adapter-v1"),
    input: contract("DocumentStageInputManifest", "document-stage-input-manifest-v1"),
    proposal: contract("DocumentStageEvidence", "document-stage-evidence-v1"),
    output: contract("DocumentStageEvidence", "document-stage-evidence-v1"),
    artifacts: ["document_upload", "ocr_page"],
    decoder: "app.services.harness_broad_adoption.HarnessProposalRuntimeService.emit_ocr_stage_evidence",
    policy: contract("DocumentStageHarnessPolicy", "document-stage-harness-v1"),
  }),
  executableEntry("study_unit_cleanup", "study_unit_cleanup", {
    registration: contract("StudyUnitCleanupWorkflowManifestEntry", "study-unit-cleanup-workflow-manifest-v1"),
    adapter: contract("DocumentStageWorkflowAdapter", "document-stage-workflow-adapter-v1"),
    input: contract("DocumentStageInputManifest", "document-stage-input-manifest-v1"),
    proposal: contract("DocumentStageEvidence", "document-stage-evidence-v1"),
    output: contract("DocumentStageEvidence", "document-stage-evidence-v1"),
    artifacts: ["document_debug", "study_unit_input"],
    decoder: "app.services.harness_broad_adoption.HarnessProposalRuntimeService.emit_study_unit_cleanup_evidence",
    policy: contract("DocumentStageHarnessPolicy", "document-stage-harness-v1"),
  }),
  executableEntry("planning", "plan_generation", {
    registration: contract("LearningPlanWorkflowManifestEntry", "learning-plan-workflow-manifest-v1"),
    adapter: contract("LearningPlanWorkflowAdapter", "learning-plan-workflow-adapter-v1"),
    input: contract("LearningPlanInputManifest", "learning-plan-input-manifest-v1"),
    proposal: contract("LearningPlanRuntimeOutput", "learning-plan-runtime-output-v1"),
    output: contract("LearningPlanCommittedProjection", "learning-plan-committed-projection-v1"),
    artifacts: ["document_debug", "persona_snapshot", "planning_context", "scene_snapshot", "study_unit_input"],
    decoder: "app.services.harness_broad_adoption.LearningPlanWorkflowAdapter",
    prompt: contract("LearningPlanPrompt", "planning-prompt-v1"),
    policy: contract("LearningPlanHarnessPolicy", "learning-plan-harness-v1"),
    toolset: TOOL_MANIFEST_SLOT,
    commit: { status: "registered", key: { workflow: "planning", stage: "plan_generation", trace_contract: contract("LearningPlanRuntimeOutput", "learning-plan-runtime-output-v1"), payload_contract: contract("LearningPlanCommittedProjection", "learning-plan-committed-projection-v1") } },
  }),
  executableEntry("planning", "planning_tool_execution", {
    registration: contract("PlanningToolExecutionWorkflowManifestEntry", "planning-tool-execution-workflow-manifest-v1"),
    adapter: contract("PlanningToolExecutionWorkflowAdapter", "planning-tool-execution-workflow-adapter-v1"),
    input: contract("PlanningToolExecutionInputManifest", "planning-tool-execution-input-manifest-v1"),
    proposal: contract("PlanningToolExecutionEvidence", "planning-tool-execution-evidence-v1"),
    output: contract("PlanningToolExecutionEvidence", "planning-tool-execution-evidence-v1"),
    artifacts: ["document_debug", "planning_context", "study_unit_input"],
    decoder: "app.services.harness_broad_adoption.HarnessProposalRuntimeService.emit_planning_tool_evidence",
    policy: contract("PlanningToolExecutionHarnessPolicy", "planning-tool-execution-harness-v1"),
    toolset: TOOL_MANIFEST_SLOT,
    evalSuites: [PLANNING_TOOL_EVAL_SUITE],
  }),
  executableEntry("persona", "persona_generation", {
    registration: contract("PersonaGenerationWorkflowManifestEntry", "persona-generation-workflow-manifest-v1"),
    adapter: contract("PersonaGenerationWorkflowAdapter", "persona-generation-workflow-adapter-v1"),
    input: contract("PersonaGenerationInputManifest", "persona-generation-input-manifest-v1"),
    proposal: contract("PersonaGenerationProposal", "persona-generation-proposal-v1"),
    output: contract("PersonaGenerationProposal", "persona-generation-proposal-v1"),
    artifacts: ["persona_snapshot"],
    decoder: "app.services.harness_broad_adoption.PersonaGenerationWorkflowAdapter",
    prompt: contract("PersonaGenerationPrompt", "persona-generation-prompt-v1"),
    policy: contract("PersonaGenerationHarnessPolicy", "persona-generation-harness-v2"),
  }),
  executableEntry("scene", "scene_generation", {
    registration: contract("SceneGenerationWorkflowManifestEntry", "scene-generation-workflow-manifest-v1"),
    adapter: contract("SceneGenerationWorkflowAdapter", "scene-generation-workflow-adapter-v1"),
    input: contract("SceneGenerationInputManifest", "scene-generation-input-manifest-v1"),
    proposal: contract("SceneTreeProposal", "scene-tree-proposal-v1"),
    output: contract("SceneTreeGeneratedProjection", "scene-tree-generated-projection-v1"),
    artifacts: ["persona_snapshot", "scene_snapshot"],
    decoder: "app.services.harness_broad_adoption.SceneGenerationWorkflowAdapter",
    prompt: contract("SceneGenerationPrompt", "scene-generation-prompt-v1"),
    policy: contract("SceneGenerationHarnessPolicy", "scene-generation-harness-v1"),
  }),
  STUDY_ENTRY,
  TAVERN_ENTRY,
  executableEntry("frontend_decode", "response_decode", {
    registration: contract("FrontendDecodeWorkflowManifestEntry", "frontend-decode-workflow-manifest-v1"),
    adapter: contract("FrontendDecodeWorkflowAdapter", "frontend-decode-workflow-adapter-v1"),
    input: contract("FrontendDecodeInputManifest", "frontend-decode-input-manifest-v1"),
    proposal: contract("FrontendDecodeResponse", "frontend-decode-response-v1"),
    output: contract("FrontendDecodeResponse", "frontend-decode-response-v1"),
    artifacts: ["frontend_response_fixture"],
    decoder: "apps.web.lib.harness-trace-decode.decodeHarnessTraceV3",
    policy: contract("FrontendDecodeHarnessPolicy", "frontend-decode-harness-v1"),
  }),
].sort((left, right) => left.key.localeCompare(right.key));

function deepFreeze<T>(value: T): Readonly<T> {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const child of Object.values(value as Record<string, unknown>)) {
      deepFreeze(child);
    }
    Object.freeze(value);
  }
  return value;
}

export const HARNESS_WORKFLOW_MANIFEST = deepFreeze({
  schema_name: "HarnessWorkflowManifest",
  schema_version: HARNESS_WORKFLOW_MANIFEST_SCHEMA_VERSION,
  stages: entries,
} as const satisfies HarnessWorkflowManifestV1);

export const HARNESS_WORKFLOW_MANIFEST_ENTRIES = deepFreeze(
  Object.fromEntries(
    HARNESS_WORKFLOW_MANIFEST.stages.map((entry) => [entry.key, entry]),
  ) as Record<string, HarnessWorkflowManifestEntryV1>,
);

const canonicalJson = (value: unknown): string => {
  if (Array.isArray(value)) {
    return `[${value.map((item) => canonicalJson(item)).join(",")}]`;
  }
  if (value !== null && typeof value === "object") {
    const record = value as Record<string, unknown>;
    return `{${Object.keys(record)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonicalJson(record[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
};

export function validateHarnessWorkflowManifest(value: unknown): asserts value is HarnessWorkflowManifestV1 {
  if (canonicalJson(value) !== canonicalJson(HARNESS_WORKFLOW_MANIFEST)) {
    throw new Error("harness_workflow_manifest_registry_drift");
  }
}

export function harnessWorkflowManifestSnapshot(): HarnessWorkflowManifestV1 {
  return JSON.parse(JSON.stringify(HARNESS_WORKFLOW_MANIFEST)) as HarnessWorkflowManifestV1;
}

export function requireExecutableWorkflowManifestEntry(
  workflow: HarnessWorkflow,
  stage: HarnessStage,
): HarnessWorkflowManifestEntryV1 {
  const entry = HARNESS_WORKFLOW_MANIFEST_ENTRIES[`${workflow}:${stage}`];
  if (!entry) {
    throw new Error("harness_workflow_manifest_stage_unknown");
  }
  if (entry.registration.status !== "registered") {
    throw new Error("harness_workflow_manifest_stage_unregistered");
  }
  const requiredContracts = [
    entry.owner_adapter,
    entry.input_contract,
    entry.proposal_contract,
    entry.output_contract,
  ];
  if (requiredContracts.some((slot) => slot.status !== "registered")) {
    throw new Error("harness_workflow_manifest_required_contract_unregistered");
  }
  if (entry.component_contracts.some((item) => item.contract.status !== "registered")) {
    throw new Error("harness_workflow_manifest_component_unregistered");
  }
  const optionalSlots = [
    entry.prompt_contract,
    entry.policy_contract,
    entry.toolset_contract,
    entry.allowed_artifact_types,
    entry.allowed_effect_adapters,
    entry.commit_policy,
    entry.decoder_route,
  ];
  if (optionalSlots.some((slot) => slot.status === "unregistered")) {
    throw new Error("harness_workflow_manifest_execution_slot_unregistered");
  }
  if (entry.eval_route.status !== "registered") {
    throw new Error("harness_workflow_manifest_eval_route_unregistered");
  }
  return entry;
}

validateHarnessWorkflowManifest(HARNESS_WORKFLOW_MANIFEST);
