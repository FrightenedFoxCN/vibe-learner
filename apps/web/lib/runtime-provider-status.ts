import type { RuntimeSettings } from "@vibe-learner/shared";

type ProviderInputs = Pick<
  RuntimeSettings,
  | "planProvider"
  | "openaiApiKeyConfigured"
  | "openaiPlanApiKeyConfigured"
  | "openaiSettingApiKeyConfigured"
  | "openaiChatApiKeyConfigured"
>;

export function runtimeProviderStatus(settings: ProviderInputs) {
  if (settings.planProvider === "mock")
    return { provider: "mock", missing: [] } as const;
  const scopes = [
    ["计划", settings.openaiPlanApiKeyConfigured],
    ["人格与场景", settings.openaiSettingApiKeyConfigured],
    ["对话与酒馆", settings.openaiChatApiKeyConfigured],
  ] as const;
  if (
    !settings.openaiApiKeyConfigured &&
    scopes.every(([, configured]) => !configured)
  ) {
    return { provider: "mock", missing: scopes.map(([label]) => label) } as const;
  }
  return {
    provider: "litellm",
    missing: scopes.filter(([, configured]) => !configured).map(([label]) => label),
  } as const;
}
