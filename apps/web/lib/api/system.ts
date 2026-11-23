import {
  diagnosticDecode,
  DiagnosticContext as DiagnosticContext,
} from "../diagnostics";
import { SETTINGS_RESPONSE_CONTRACTS } from "@vibe-learner/shared/settings-response-contracts";
import {
  decodeRuntimeSettings,
  decodeRuntimeModelProbe,
} from "../runtime-settings-decode";
import { decodeModelToolConfig } from "../model-tools-decode";
import { decodeModelUsageStats } from "../model-usage-decode";
import type {
  ModelToolConfig,
  ModelToolToggle,
  RuntimeOpenAIProbeResult,
  RuntimeFeatureProbeName,
  RuntimeSettings,
  RuntimeSettingsPatch,
  TokenUsageStats,
} from "@vibe-learner/shared";

import { AI_BASE_URL, request, readJson } from "./_shared";

export async function getModelToolConfig(): Promise<ModelToolConfig> {
  const diagnosticResponse = await request(`${AI_BASE_URL()}/model-tools/config`);
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(
    diagnosticResponse,
    () => decodeModelToolConfig(payload),
    SETTINGS_RESPONSE_CONTRACTS.modelTools,
  );
}

export async function updateModelToolConfig(
  toggles: ModelToolToggle[],
): Promise<ModelToolConfig> {
  const diagnosticResponse = await request(`${AI_BASE_URL()}/model-tools/config`, {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      toggles: toggles.map((toggle) => ({
        stage_name: toggle.stageName,
        tool_name: toggle.toolName,
        enabled: toggle.enabled,
      })),
    }),
  });
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(
    diagnosticResponse,
    () => decodeModelToolConfig(payload),
    SETTINGS_RESPONSE_CONTRACTS.modelTools,
  );
}

export async function getRuntimeSettings(): Promise<RuntimeSettings> {
  const diagnosticResponse = await request(`${AI_BASE_URL()}/runtime-settings`);
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(
    diagnosticResponse,
    () => decodeRuntimeSettings(payload),
    SETTINGS_RESPONSE_CONTRACTS.runtimeSettings,
  );
}

export async function updateRuntimeSettings(
  patch: RuntimeSettingsPatch,
  context?: DiagnosticContext,
): Promise<RuntimeSettings> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/runtime-settings`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        plan_provider: patch.planProvider,
        openai_api_key: patch.openaiApiKey,
        openai_base_url: patch.openaiBaseUrl,
        openai_plan_api_key: patch.openaiPlanApiKey,
        openai_plan_base_url: patch.openaiPlanBaseUrl,
        openai_plan_model: patch.openaiPlanModel,
        openai_setting_api_key: patch.openaiSettingApiKey,
        openai_setting_base_url: patch.openaiSettingBaseUrl,
        openai_setting_model: patch.openaiSettingModel,
        openai_setting_web_search_enabled: patch.openaiSettingWebSearchEnabled,
        openai_chat_api_key: patch.openaiChatApiKey,
        openai_chat_base_url: patch.openaiChatBaseUrl,
        openai_chat_model: patch.openaiChatModel,
        openai_chat_temperature: patch.openaiChatTemperature,
        openai_setting_temperature: patch.openaiSettingTemperature,
        openai_setting_max_tokens: patch.openaiSettingMaxTokens,
        openai_chat_max_tokens: patch.openaiChatMaxTokens,
        openai_chat_history_messages: patch.openaiChatHistoryMessages,
        openai_chat_tool_max_rounds: patch.openaiChatToolMaxRounds,
        openai_embedding_model: patch.openaiEmbeddingModel,
        openai_chat_model_multimodal: patch.openaiChatModelMultimodal,
        openai_timeout_seconds: patch.openaiTimeoutSeconds,
        openai_plan_model_multimodal: patch.openaiPlanModelMultimodal,
        openai_plan_fallback_model: patch.openaiPlanFallbackModel,
        openai_plan_fallback_disable_tools: patch.openaiPlanFallbackDisableTools,
        show_debug_info: patch.showDebugInfo,
      }),
    },
    context,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(
    diagnosticResponse,
    () => decodeRuntimeSettings(payload),
    SETTINGS_RESPONSE_CONTRACTS.runtimeSettings,
  );
}

export async function probeRuntimeOpenAIModels(input: {
  apiKey: string;
  baseUrl: string;
  model?: string;
  features?: RuntimeFeatureProbeName[];
}): Promise<RuntimeOpenAIProbeResult> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/runtime-settings/check-openai-models`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        api_key: input.apiKey,
        base_url: input.baseUrl,
        model: input.model ?? "",
        features: input.features ?? [],
      }),
    },
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(
    diagnosticResponse,
    () =>
      decodeRuntimeModelProbe(payload, {
        model: input.model,
        features: input.features,
      }),
    SETTINGS_RESPONSE_CONTRACTS.modelProbe,
  );
}

export async function getModelUsageStats(): Promise<TokenUsageStats> {
  const response = await request(`${AI_BASE_URL()}/model-usage/stats`);
  const raw = await readJson<unknown>(response);
  return diagnosticDecode(
    response,
    () => decodeModelUsageStats(raw),
    SETTINGS_RESPONSE_CONTRACTS.modelUsage,
  );
}
