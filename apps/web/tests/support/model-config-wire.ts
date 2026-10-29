// UI fixtures may choose synthetic tools; the public wire shape stays complete.
interface ToolInput {
  name: string;
  label: string;
  description?: string;
  category?: string;
  category_label?: string;
  enabled: boolean;
  available: boolean;
  unavailable_reason?: string;
}
interface StageInput {
  name: string;
  label: string;
  description?: string;
  stage_enabled: boolean;
  tools: ToolInput[];
}
export function wireModelTools(stages: StageInput[]) {
  return {
    contract_version: "model-tool-config-response-v1",
    updated_at: "2026-10-29T00:00:00Z",
    stages: stages.map((stage) => ({
      ...stage,
      description: stage.description ?? "",
      audit_basis: [],
      stage_disabled_reason: "",
      tools: stage.tools.map((tool) => ({
        ...tool,
        description: tool.description ?? "",
        category: tool.category ?? "sensory",
        category_label: tool.category_label ?? "Sensory",
        audit_basis: [],
        unavailable_reason: tool.unavailable_reason ?? "",
        effective_enabled:
          tool.enabled && tool.available && stage.stage_enabled,
      })),
    })),
  };
}
