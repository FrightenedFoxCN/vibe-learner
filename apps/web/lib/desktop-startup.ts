import type { DesktopVaultState, RuntimeSettings } from "@vibe-learner/shared";

export const DESKTOP_STARTUP_GUARD_SESSION_KEY = "vibe-learner.desktop-startup-guard.v1";
export const DESKTOP_STARTUP_QUERY_KEY = "startup";
export const DESKTOP_STARTUP_QUERY_VALUE = "setup-required";

interface DesktopStartupRequirementInput {
  isDesktop: boolean;
  startupError?: string;
  vaultState?: DesktopVaultState;
  settings: RuntimeSettings | null;
}

export function hasConfiguredRuntimeApiKey(settings: RuntimeSettings | null | undefined) {
  if (!settings) {
    return false;
  }
  return Boolean(
    settings.openaiApiKeyConfigured ||
      settings.openaiPlanApiKeyConfigured ||
      settings.openaiSettingApiKeyConfigured ||
      settings.openaiChatApiKeyConfigured
  );
}

export function resolveDesktopStartupRequirement(input: DesktopStartupRequirementInput): {
  title: string;
  description: string;
} | null {
  if (!input.isDesktop) {
    return null;
  }

  const startupError = String(input.startupError ?? "").trim();
  if (startupError) {
    return {
      title: "桌面运行时启动失败",
      description: "先修复桌面后端启动问题，再继续配置 Vault 和 API Key。"
    };
  }

  const vaultState = input.vaultState ?? "unconfigured";
  if (vaultState === "unconfigured") {
    return {
      title: "先创建桌面 Vault",
      description: "当前是首次安全配置。先在下方创建并解锁桌面 Vault，然后填写至少一个可用的 API Key。"
    };
  }

  if (vaultState !== "unlocked") {
    return {
      title: "先解锁桌面 Vault",
      description: "当前启动还没有把密钥加载进运行时。先解锁桌面 Vault，然后确认下方已有可用的 API Key。"
    };
  }

  if (!hasConfiguredRuntimeApiKey(input.settings)) {
    return {
      title: "还缺少可用 API Key",
      description: "Vault 已解锁，但当前运行时还没有可用密钥。请在下方“连接与模型分配”里填写默认访问密钥或各场景密钥。"
    };
  }

  return null;
}
