import type { PageDebugSnapshot } from "../page-debug-context";
import type { SettingsController } from "./use-settings-controller";
import { NUMERIC_SETTING_CONFIGS, type NumericSettingKey } from "./settings-utils";

type DebugState = Pick<SettingsController,
  "settings" | "numericDrafts" | "probeState" | "desktopSecurity" |
  "loading" | "loadError" | "saveError" | "savePhase" | "lastSavedAt">;

function allowed(value: unknown, values: readonly string[]) {
  return typeof value === "string" && values.includes(value) ? value : "unknown";
}

// Explicit projection: settings and provider results contain secrets, arbitrary
// endpoint/model text, and errors. Never spread them into a debug snapshot.
export function buildSettingsDebugSnapshot(state: DebugState): PageDebugSnapshot {
  const settings = state.settings;
  const security = state.desktopSecurity;
  const numeric = Object.fromEntries(
    (Object.keys(NUMERIC_SETTING_CONFIGS) as NumericSettingKey[]).map((key) => {
      const value = settings?.[key];
      const draft = state.numericDrafts[key];
      const config = NUMERIC_SETTING_CONFIGS[key];
      const parsed = typeof draft === "string" && draft.trim() ? Number(draft) : NaN;
      return [key, {
        committed: typeof value === "number" && Number.isFinite(value) ? value : null,
        draftValid: Number.isFinite(parsed) && parsed >= config.min && parsed <= config.max &&
          (!config.integer || Number.isInteger(parsed)),
        hasDraft: Boolean(draft)
      }];
    })
  );
  return {
    title: "设置页调试面板",
    subtitle: "查看设置状态与探测摘要；密钥、地址和原始错误不显示。",
    error: [state.loadError ? "设置加载失败" : "", state.saveError ? "设置保存失败" : ""].filter(Boolean).join("；"),
    summary: [
      { label: "加载状态", value: state.loading ? "加载中" : "就绪" },
      { label: "保存阶段", value: allowed(state.savePhase, ["idle", "pending", "saving", "saved", "error"]) },
      { label: "已有保存记录", value: state.lastSavedAt ? "是" : "否" },
      { label: "调试显示", value: settings?.showDebugInfo === true ? "开启" : "关闭" },
      { label: "提供器", value: settings ? allowed(settings.planProvider, ["mock", "litellm"]) : "-" },
      { label: "桌面 Vault", value: security.enabled ? allowed(security.vaultState, ["unconfigured", "locked", "unlocked"]) : "browser" }
    ],
    details: [
      { title: "运行时设置摘要", value: settings ? {
        keysConfigured: {
          global: settings.openaiApiKeyConfigured === true,
          plan: settings.openaiPlanApiKeyConfigured === true,
          setting: settings.openaiSettingApiKeyConfigured === true,
          chat: settings.openaiChatApiKeyConfigured === true
        },
        planMultimodal: settings.openaiPlanModelMultimodal === true,
        chatMultimodal: settings.openaiChatModelMultimodal === true,
        settingWebSearchEnabled: settings.openaiSettingWebSearchEnabled === true,
        planFallbackDisableTools: settings.openaiPlanFallbackDisableTools === true
      } : null },
      { title: "数值设置与草稿状态", value: numeric },
      { title: "能力探测摘要", value: Object.fromEntries(
        (["global", "plan", "setting", "chat"] as const).map((scope) => {
          const probe = state.probeState[scope];
          return [scope, {
            loading: probe.loading === true,
            available: probe.available === true,
            modelCount: Array.isArray(probe.models) ? probe.models.length : 0,
            hasError: Boolean(probe.error),
            hasChecked: Boolean(probe.lastCheckedAt),
            sharedFromScope: probe.sharedFromScope === null ? null : allowed(probe.sharedFromScope, ["global", "plan", "setting", "chat"]),
            features: Object.fromEntries((["plan", "study", "persona", "scene", "tavern"] as const).map((feature) => [
              feature, allowed(probe.featureReadiness[feature]?.status, ["ready", "unsupported", "failed", "not_tested"])
            ]))
          }];
        })
      ) },
      { title: "桌面安全摘要", value: {
        enabled: security.enabled === true,
        busy: security.busy === true,
        hasError: Boolean(security.error),
        hasStartupError: Boolean(security.startupError)
      } }
    ]
  };
}
