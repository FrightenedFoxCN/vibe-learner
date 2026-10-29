/** Public response versions; missing versions identify read-only legacy shapes. */
export const SETTINGS_RESPONSE_CONTRACTS = Object.freeze({
  runtimeSettings: "runtime-settings-response-v1",
  modelTools: "model-tool-config-response-v1",
  modelProbe: "runtime-model-probe-response-v1",
  modelUsage: "model-usage-stats-response-v1",
} as const);

export const RUNTIME_CAPABILITY_STATUSES = [
  "supported",
  "unsupported",
  "unknown",
] as const;
export const RUNTIME_CAPABILITY_SOURCES = [
  "metadata",
  "model_name",
  "unavailable",
] as const;
export const RUNTIME_PROBE_FEATURES = [
  "plan",
  "study",
  "persona",
  "scene",
  "tavern",
] as const;
export const RUNTIME_READINESS_STATUSES = [
  "ready",
  "unsupported",
  "failed",
  "not_tested",
] as const;
