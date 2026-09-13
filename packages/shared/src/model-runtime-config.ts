/** Browser-visible mirror of backend model setting defaults and validation. */
export const MODEL_RUNTIME_CONFIG = Object.freeze({
  defaultModelName: "gpt-4.1-mini",
  defaultEmbeddingModel: "text-embedding-3-small",
  timeoutSeconds: { min: 5, max: 300, default: 30 },
  settingTemperature: { min: 0, max: 2, default: 0.4 },
  chatTemperature: { min: 0, max: 2, default: 0.35 },
  settingMaxTokens: { min: 64, max: 16_384, default: 900 },
  chatMaxTokens: { min: 64, max: 16_384, default: 800 },
  chatHistoryMessages: { min: 1, max: 40, default: 8 },
  chatToolMaxRounds: { min: 1, max: 12, default: 4 },
} as const);

export const modelRuntimeConfigSnapshot = () => ({
  schema_version: "model-runtime-config-v1",
  default_model_name: MODEL_RUNTIME_CONFIG.defaultModelName,
  default_embedding_model: MODEL_RUNTIME_CONFIG.defaultEmbeddingModel,
  timeout_seconds: MODEL_RUNTIME_CONFIG.timeoutSeconds,
  setting_temperature: MODEL_RUNTIME_CONFIG.settingTemperature,
  chat_temperature: MODEL_RUNTIME_CONFIG.chatTemperature,
  setting_max_tokens: MODEL_RUNTIME_CONFIG.settingMaxTokens,
  chat_max_tokens: MODEL_RUNTIME_CONFIG.chatMaxTokens,
  chat_history_messages: MODEL_RUNTIME_CONFIG.chatHistoryMessages,
  chat_tool_max_rounds: MODEL_RUNTIME_CONFIG.chatToolMaxRounds,
});
