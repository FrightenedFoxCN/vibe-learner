import type {
  RuntimeCapabilitySignal,
  RuntimeModelCapability,
  RuntimeOpenAIProbeResult,
  RuntimeSettings,
  RuntimeSettingsPatch
} from "@vibe-learner/shared";

export const AUTO_SAVE_DELAY_MS = 900;

export type ProbeScope = "global" | "plan" | "setting" | "chat";

export type NumericSettingKey =
  | "openaiTimeoutSeconds"
  | "openaiSettingTemperature"
  | "openaiChatTemperature"
  | "openaiSettingMaxTokens"
  | "openaiChatMaxTokens"
  | "openaiChatHistoryMessages"
  | "openaiChatToolMaxRounds";

export interface NumericSettingConfig {
  min: number;
  max: number;
  fallback: number;
  integer: boolean;
}

export type NumericDraftState = Record<NumericSettingKey, string>;

export interface ScopeProbeState extends RuntimeOpenAIProbeResult {
  loading: boolean;
  lastCheckedAt: string;
}

export type SettingsSavePhase = "idle" | "pending" | "saving" | "saved" | "error";

export interface CapabilityAuditConfig {
  scope: Exclude<ProbeScope, "global">;
  title: string;
  description: string;
  modelKey: "openaiPlanModel" | "openaiSettingModel" | "openaiChatModel";
  manualKey:
    | "openaiPlanModelMultimodal"
    | "openaiSettingWebSearchEnabled"
    | "openaiChatModelMultimodal";
  manualLabel: string;
  capabilityKey: "multimodal" | "webSearch";
}

export const EMPTY_PROBE_STATE: ScopeProbeState = {
  loading: false,
  available: false,
  models: [],
  capabilities: {},
  error: "",
  lastCheckedAt: ""
};

export const NUMERIC_SETTING_CONFIGS: Record<NumericSettingKey, NumericSettingConfig> = {
  openaiTimeoutSeconds: { min: 5, max: 300, fallback: 30, integer: true },
  openaiSettingTemperature: { min: 0, max: 2, fallback: 0.4, integer: false },
  openaiChatTemperature: { min: 0, max: 2, fallback: 0.35, integer: false },
  openaiSettingMaxTokens: { min: 64, max: 16384, fallback: 900, integer: true },
  openaiChatMaxTokens: { min: 64, max: 16384, fallback: 800, integer: true },
  openaiChatHistoryMessages: { min: 1, max: 40, fallback: 8, integer: true },
  openaiChatToolMaxRounds: { min: 1, max: 12, fallback: 4, integer: true }
};

export const CAPABILITY_AUDIT_CONFIGS: CapabilityAuditConfig[] = [
  {
    scope: "plan",
    title: "计划生成模型",
    description: "对照图像输入能力与计划多模态开关。",
    modelKey: "openaiPlanModel",
    manualKey: "openaiPlanModelMultimodal",
    manualLabel: "计划支持图像输入",
    capabilityKey: "multimodal"
  },
  {
    scope: "setting",
    title: "人格设定辅助模型",
    description: "对照网络访问能力与人格设定的联网开关。",
    modelKey: "openaiSettingModel",
    manualKey: "openaiSettingWebSearchEnabled",
    manualLabel: "允许联网检索",
    capabilityKey: "webSearch"
  },
  {
    scope: "chat",
    title: "学习对话模型",
    description: "对照图像输入能力与学习对话多模态开关。",
    modelKey: "openaiChatModel",
    manualKey: "openaiChatModelMultimodal",
    manualLabel: "对话支持图像输入",
    capabilityKey: "multimodal"
  }
];

export function buildRuntimeSettingsPatch(settings: RuntimeSettings): RuntimeSettingsPatch {
  return {
    planProvider: settings.planProvider,
    openaiApiKey: settings.openaiApiKey,
    openaiBaseUrl: settings.openaiBaseUrl,
    openaiPlanApiKey: settings.openaiPlanApiKey,
    openaiPlanBaseUrl: settings.openaiPlanBaseUrl,
    openaiPlanModel: settings.openaiPlanModel,
    openaiSettingApiKey: settings.openaiSettingApiKey,
    openaiSettingBaseUrl: settings.openaiSettingBaseUrl,
    openaiSettingModel: settings.openaiSettingModel,
    openaiSettingWebSearchEnabled: settings.openaiSettingWebSearchEnabled,
    openaiChatApiKey: settings.openaiChatApiKey,
    openaiChatBaseUrl: settings.openaiChatBaseUrl,
    openaiChatModel: settings.openaiChatModel,
    openaiChatTemperature: settings.openaiChatTemperature,
    openaiSettingTemperature: settings.openaiSettingTemperature,
    openaiSettingMaxTokens: settings.openaiSettingMaxTokens,
    openaiChatMaxTokens: settings.openaiChatMaxTokens,
    openaiChatHistoryMessages: settings.openaiChatHistoryMessages,
    openaiChatToolMaxRounds: settings.openaiChatToolMaxRounds,
    openaiChatToolsEnabled: settings.openaiChatToolsEnabled,
    openaiChatMemoryToolEnabled: settings.openaiChatMemoryToolEnabled,
    openaiEmbeddingModel: settings.openaiEmbeddingModel,
    openaiChatModelMultimodal: settings.openaiChatModelMultimodal,
    openaiTimeoutSeconds: settings.openaiTimeoutSeconds,
    openaiPlanModelMultimodal: settings.openaiPlanModelMultimodal,
    openaiPlanToolsEnabled: settings.openaiPlanToolsEnabled,
    openaiPlanFallbackModel: settings.openaiPlanFallbackModel,
    openaiPlanFallbackDisableTools: settings.openaiPlanFallbackDisableTools,
    showDebugInfo: settings.showDebugInfo
  };
}

export function serializeSettings(settings: RuntimeSettings): string {
  return JSON.stringify(buildRuntimeSettingsPatch(settings));
}

export function resolveScopeEndpoint(
  settings: RuntimeSettings,
  scope: ProbeScope
): { apiKey: string; baseUrl: string } {
  if (scope === "global") {
    return {
      apiKey: settings.openaiApiKey.trim(),
      baseUrl: settings.openaiBaseUrl.trim()
    };
  }
  if (scope === "plan") {
    return {
      apiKey: (settings.openaiPlanApiKey || settings.openaiApiKey).trim(),
      baseUrl: (settings.openaiPlanBaseUrl || settings.openaiBaseUrl).trim()
    };
  }
  if (scope === "setting") {
    return {
      apiKey: (settings.openaiSettingApiKey || settings.openaiApiKey).trim(),
      baseUrl: (settings.openaiSettingBaseUrl || settings.openaiBaseUrl).trim()
    };
  }
  return {
    apiKey: (settings.openaiChatApiKey || settings.openaiApiKey).trim(),
    baseUrl: (settings.openaiChatBaseUrl || settings.openaiBaseUrl).trim()
  };
}

export function uniqueWithCurrent(models: string[], current: string): string[] {
  const set = new Set<string>();
  const list: string[] = [];
  for (const modelName of [current, ...models]) {
    const name = String(modelName || "").trim();
    if (!name || set.has(name)) {
      continue;
    }
    set.add(name);
    list.push(name);
  }
  return list;
}

export function buildNumericDrafts(settings: RuntimeSettings): NumericDraftState {
  return {
    openaiTimeoutSeconds: String(settings.openaiTimeoutSeconds),
    openaiSettingTemperature: String(settings.openaiSettingTemperature),
    openaiChatTemperature: String(settings.openaiChatTemperature),
    openaiSettingMaxTokens: String(settings.openaiSettingMaxTokens),
    openaiChatMaxTokens: String(settings.openaiChatMaxTokens),
    openaiChatHistoryMessages: String(settings.openaiChatHistoryMessages),
    openaiChatToolMaxRounds: String(settings.openaiChatToolMaxRounds)
  };
}

export function parseNumericSetting(value: string, config: NumericSettingConfig): number {
  const parsed = Number(value);
  if (!Number.isFinite(parsed)) {
    return config.fallback;
  }
  const normalized = config.integer ? Math.round(parsed) : parsed;
  return Math.min(config.max, Math.max(config.min, normalized));
}

export function formatProbeHint(state: ScopeProbeState): string {
  if (state.loading) {
    return "正在拉取模型列表与能力信息...";
  }
  if (state.error) {
    return `失败：${state.error}`;
  }
  if (state.available) {
    return `已拉取 ${state.models.length} 个模型${state.lastCheckedAt ? "，能力信息已更新" : ""}`;
  }
  return "尚未拉取";
}

export function resolveCapabilitySignal(
  capability: RuntimeModelCapability | undefined,
  key: "multimodal" | "webSearch"
): RuntimeCapabilitySignal {
  if (!capability) {
    return {
      status: "unknown",
      source: "unavailable",
      note: "先拉取当前连接的模型能力信息，才能对照这个开关。"
    };
  }
  return key === "multimodal" ? capability.multimodal : capability.webSearch;
}

export function capabilitySignalToBoolean(signal: RuntimeCapabilitySignal): boolean | null {
  if (signal.status === "supported") {
    return true;
  }
  if (signal.status === "unsupported") {
    return false;
  }
  return null;
}

export function formatCapabilityStatus(signal: RuntimeCapabilitySignal): string {
  if (signal.status === "supported") {
    return "已支持";
  }
  if (signal.status === "unsupported") {
    return "未支持";
  }
  return "未知";
}

export function formatCapabilitySource(signal: RuntimeCapabilitySignal): string {
  if (signal.source === "metadata") {
    return "来自模型元数据";
  }
  if (signal.source === "model_name") {
    return "来自模型名推断";
  }
  return "暂无显式能力信息";
}
