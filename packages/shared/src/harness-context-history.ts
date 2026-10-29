import type { HarnessContractRef } from "./harness";

/** Read compatibility only; production context construction keeps the current manifest. */
const profiles = [
  {
    workflow: "document_parse",
    stage: "chunk_building",
    input_contract: "DocumentStageInputManifest@document-stage-input-manifest-v1",
    prompt_contract: null,
    policy_contract: "DocumentStageHarnessPolicy@document-stage-harness-v1",
    component_versions: ["document_chunk_builder@document-chunk-builder-v1"],
  },
  {
    workflow: "document_parse",
    stage: "document_parse",
    input_contract: "DocumentProcessInputManifest@document-process-input-manifest-v1",
    prompt_contract: null,
    policy_contract: "DocumentProcessHarnessPolicy@document-process-harness-v1",
    component_versions: ["document_parser@document-parser-v1"],
  },
  {
    workflow: "document_parse",
    stage: "document_parse",
    input_contract: "DocumentProcessInputManifest@document-process-input-manifest-v2",
    prompt_contract: null,
    policy_contract: "DocumentProcessHarnessPolicy@document-process-harness-v1",
    component_versions: ["document_parser@document-parser-v2"],
  },
  {
    workflow: "planning",
    stage: "plan_generation",
    input_contract: "LearningPlanInputManifest@learning-plan-input-manifest-v1",
    prompt_contract: "LearningPlanPrompt@planning-prompt-v6",
    policy_contract: "LearningPlanHarnessPolicy@learning-plan-harness-v1",
    component_versions: [
      "planning_prompt@planning-prompt-v6",
      "planning_toolset@planning-toolset-v2",
    ],
  },
  {
    workflow: "planning",
    stage: "plan_generation",
    input_contract: "LearningPlanInputManifest@learning-plan-input-manifest-v1",
    prompt_contract: "LearningPlanPrompt@planning-prompt-v7",
    policy_contract: "LearningPlanHarnessPolicy@learning-plan-harness-v1",
    component_versions: [
      "planning_prompt@planning-prompt-v7",
      "planning_toolset@planning-toolset-v2",
    ],
  },
  {
    workflow: "planning",
    stage: "planning_tool_execution",
    input_contract:
      "PlanningToolExecutionInputManifest@planning-tool-execution-input-manifest-v1",
    prompt_contract: null,
    policy_contract:
      "PlanningToolExecutionHarnessPolicy@planning-tool-execution-harness-v1",
    component_versions: [
      "planning_tool_runtime@planning-tool-runtime-v2",
      "planning_toolset@planning-toolset-v2",
    ],
  },
  {
    workflow: "study_chat",
    stage: "study_chat_reply",
    input_contract: "StudyChatInputManifest@study-chat-input-manifest-v1",
    prompt_contract: "StudyChatPrompt@study-chat-prompt-v2",
    policy_contract: "StudyChatHarnessPolicy@study-chat-harness-v1",
    component_versions: [
      "study_chat_prompt@study-chat-prompt-v2",
      "study_chat_toolset@study-chat-toolset-v2",
      "study_grounding@study-grounding-v1",
      "study_visual_grounding@study-visual-grounding-v1",
    ],
  },
] as const;

export const HISTORICAL_HARNESS_CONTEXT_PROFILES = Object.freeze(
  profiles.map((profile) =>
    Object.freeze({
      ...profile,
      component_versions: Object.freeze(profile.component_versions),
    }),
  ),
);

export function matchesHistoricalHarnessContext(value: {
  workflow: string;
  stage: string;
  inputContract: HarnessContractRef;
  promptContract: HarnessContractRef | null;
  policyContract: HarnessContractRef | null;
  componentVersions: HarnessContractRef[];
}): boolean {
  const token = (ref: HarnessContractRef | null) =>
    ref === null ? null : `${ref.name}@${ref.version}`;
  const components = value.componentVersions.map(token);
  return HISTORICAL_HARNESS_CONTEXT_PROFILES.some(
    (profile) =>
      profile.workflow === value.workflow &&
      profile.stage === value.stage &&
      profile.input_contract === token(value.inputContract) &&
      profile.prompt_contract === token(value.promptContract) &&
      profile.policy_contract === token(value.policyContract) &&
      profile.component_versions.length === components.length &&
      profile.component_versions.every((ref, index) => ref === components[index]),
  );
}
