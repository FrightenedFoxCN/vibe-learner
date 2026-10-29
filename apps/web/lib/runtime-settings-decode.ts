import type {
  RuntimeSettings,
  RuntimeOpenAIProbeResult,
  RuntimeModelCapability,
  RuntimeFeatureProbeName,
} from "@vibe-learner/shared";
import {
  SETTINGS_RESPONSE_CONTRACTS,
  RUNTIME_CAPABILITY_STATUSES,
  RUNTIME_CAPABILITY_SOURCES,
  RUNTIME_PROBE_FEATURES,
  RUNTIME_READINESS_STATUSES,
} from "@vibe-learner/shared/settings-response-contracts";
import { MODEL_RUNTIME_CONFIG as limits } from "@vibe-learner/shared/model-runtime-config";
import {
  modelResponseDecoder,
  responseEnvelope,
  legacyField,
  ModelResponseDecodeError,
} from "./model-response-decode.ts";

const d = modelResponseDecoder("runtime_settings");
const probe = modelResponseDecoder("runtime_model_probe");
export function decodeRuntimeSettings(raw: unknown): RuntimeSettings {
  const p = "runtime_settings";
  const { value: v, legacy } = responseEnvelope(
    raw,
    p,
    SETTINGS_RESPONSE_CONTRACTS.runtimeSettings,
    d,
  );
  const string = (key: string) =>
    d.string(d.field(v, key, p), `${p}.${key}`, true);
  const boolean = (key: string) => d.boolean(d.field(v, key, p), `${p}.${key}`);
  const configured = (key: string) =>
    d.boolean(legacyField(v, key, p, legacy, false, d), `${p}.${key}`);
  const integer = (key: string, bounds: { min: number; max: number }) =>
    d.integer(d.field(v, key, p), `${p}.${key}`, bounds.min, bounds.max);
  const number = (key: string, bounds: { min: number; max: number }) =>
    d.finiteNumber(d.field(v, key, p), `${p}.${key}`, bounds.min, bounds.max);
  const provider = d.enumeration(
    d.field(v, "plan_provider", p),
    ["mock", "litellm", "openai"] as const,
    `${p}.plan_provider`,
  );
  return {
    updatedAt: string("updated_at"),
    planProvider: provider === "openai" ? "litellm" : provider,
    openaiApiKey: string("openai_api_key"),
    openaiApiKeyConfigured: configured("openai_api_key_configured"),
    openaiBaseUrl: string("openai_base_url"),
    openaiPlanApiKey: string("openai_plan_api_key"),
    openaiPlanApiKeyConfigured: configured("openai_plan_api_key_configured"),
    openaiPlanBaseUrl: string("openai_plan_base_url"),
    openaiPlanModel: string("openai_plan_model"),
    openaiSettingApiKey: string("openai_setting_api_key"),
    openaiSettingApiKeyConfigured: configured(
      "openai_setting_api_key_configured",
    ),
    openaiSettingBaseUrl: string("openai_setting_base_url"),
    openaiSettingModel: string("openai_setting_model"),
    openaiSettingWebSearchEnabled: boolean("openai_setting_web_search_enabled"),
    openaiChatApiKey: string("openai_chat_api_key"),
    openaiChatApiKeyConfigured: configured("openai_chat_api_key_configured"),
    openaiChatBaseUrl: string("openai_chat_base_url"),
    openaiChatModel: string("openai_chat_model"),
    openaiChatTemperature: number(
      "openai_chat_temperature",
      limits.chatTemperature,
    ),
    openaiSettingTemperature: number(
      "openai_setting_temperature",
      limits.settingTemperature,
    ),
    openaiSettingMaxTokens: integer(
      "openai_setting_max_tokens",
      limits.settingMaxTokens,
    ),
    openaiChatMaxTokens: integer(
      "openai_chat_max_tokens",
      limits.chatMaxTokens,
    ),
    openaiChatHistoryMessages: integer(
      "openai_chat_history_messages",
      limits.chatHistoryMessages,
    ),
    openaiChatToolMaxRounds: integer(
      "openai_chat_tool_max_rounds",
      limits.chatToolMaxRounds,
    ),
    openaiEmbeddingModel: string("openai_embedding_model"),
    openaiChatModelMultimodal: boolean("openai_chat_model_multimodal"),
    openaiTimeoutSeconds: integer(
      "openai_timeout_seconds",
      limits.timeoutSeconds,
    ),
    openaiPlanModelMultimodal: boolean("openai_plan_model_multimodal"),
    openaiPlanFallbackModel: string("openai_plan_fallback_model"),
    openaiPlanFallbackDisableTools: boolean(
      "openai_plan_fallback_disable_tools",
    ),
    showDebugInfo: boolean("show_debug_info"),
  };
}

export function decodeRuntimeModelProbe(
  raw: unknown,
  expected?: { model?: string; features?: readonly RuntimeFeatureProbeName[] },
): RuntimeOpenAIProbeResult {
  const p = "runtime_model_probe";
  const { value: v, legacy } = responseEnvelope(
    raw,
    p,
    SETTINGS_RESPONSE_CONTRACTS.modelProbe,
    probe,
  );
  const field = (key: string, fallback: unknown) =>
    legacyField(v, key, p, legacy, fallback, probe);
  const available = probe.boolean(
    probe.field(v, "available", p),
    `${p}.available`,
  );
  const models = probe.stringArray(probe.field(v, "models", p), `${p}.models`);
  probe.unique(models, `${p}.models`);
  const capabilitiesRaw = probe.record(
    field("capabilities", {}),
    `${p}.capabilities`,
  );
  const capabilities = Object.fromEntries(
    Object.entries(capabilitiesRaw).map(([id, raw], index) => {
      const path = `${p}.capabilities[${index}]`;
      if (!models.includes(id))
        throw new ModelResponseDecodeError(
          "runtime_model_probe",
          path,
          "unlisted_model",
        );
      const c = probe.record(raw, path);
      const cf = (key: string, fallback: unknown) =>
        legacyField(c, key, path, legacy, fallback, probe);
      const signal = (key: string) => {
        const signalPath = `${path}.${key}`;
        const value = probe.record(
          cf(key, { status: "unknown", source: "unavailable", note: "" }),
          signalPath,
        );
        const sf = (name: string, fallback: unknown) =>
          legacyField(value, name, signalPath, legacy, fallback, probe);
        return {
          status: probe.enumeration(
            sf("status", "unknown"),
            RUNTIME_CAPABILITY_STATUSES,
            `${signalPath}.status`,
          ),
          source: probe.enumeration(
            sf("source", "unavailable"),
            RUNTIME_CAPABILITY_SOURCES,
            `${signalPath}.source`,
          ),
          note: probe.string(sf("note", ""), `${signalPath}.note`, true),
        };
      };
      const result: RuntimeModelCapability = {
        inputModalities: probe.stringArray(
          cf("input_modalities", []),
          `${path}.input_modalities`,
        ),
        outputModalities: probe.stringArray(
          cf("output_modalities", []),
          `${path}.output_modalities`,
        ),
        toolTypes: probe.stringArray(
          cf("tool_types", []),
          `${path}.tool_types`,
        ),
        multimodal: signal("multimodal"),
        webSearch: signal("web_search"),
      };
      return [id, result];
    }),
  );
  const readinessRaw = probe.record(
    field("feature_readiness", {}),
    `${p}.feature_readiness`,
  );
  const featureReadiness = Object.fromEntries(
    Object.entries(readinessRaw).map(([key, raw], index) => {
      const path = `${p}.feature_readiness[${index}]`;
      const feature = probe.enumeration(key, RUNTIME_PROBE_FEATURES, path);
      if (expected && !expected.features?.includes(feature))
        throw new ModelResponseDecodeError(
          "runtime_model_probe",
          path,
          "unrequested_feature",
        );
      const entry = probe.record(raw, path);
      const ef = (key: string, fallback: unknown) =>
        legacyField(entry, key, path, legacy, fallback, probe);
      const model = probe.string(
        probe.field(entry, "model", path),
        `${path}.model`,
      );
      if (expected)
        probe.equal(model, (expected.model ?? "").trim(), `${path}.model`);
      return [
        feature,
        {
          model,
          status: probe.enumeration(
            probe.field(entry, "status", path),
            RUNTIME_READINESS_STATUSES,
            `${path}.status`,
          ),
          code: probe.string(ef("code", ""), `${path}.code`, true),
          note: probe.string(ef("note", ""), `${path}.note`, true),
          parameterAdjustments: probe.stringArray(
            ef("parameter_adjustments", []),
            `${path}.parameter_adjustments`,
          ),
        },
      ];
    }),
  );
  if (
    expected &&
    (!legacy || Object.hasOwn(v, "feature_readiness")) &&
    (expected.features ?? []).some(
      (feature) => !Object.hasOwn(featureReadiness, feature),
    )
  ) {
    throw new ModelResponseDecodeError(
      "runtime_model_probe",
      `${p}.feature_readiness`,
      "missing_requested_feature",
    );
  }
  return {
    available,
    models,
    capabilities,
    featureReadiness,
    error: probe.string(field("error", ""), `${p}.error`, true),
  };
}
