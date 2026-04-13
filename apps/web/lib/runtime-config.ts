import type { DesktopRuntimeConfig } from "@vibe-learner/shared";

declare global {
  interface Window {
    __VIBE_LEARNER_DESKTOP_CONFIG__?: DesktopRuntimeConfig;
  }
}

const DEFAULT_AI_BASE_URL = process.env.NEXT_PUBLIC_AI_BASE_URL ?? "http://127.0.0.1:8000";

function normalizeDesktopConfig(value: unknown): DesktopRuntimeConfig | null {
  if (!value || typeof value !== "object") {
    return null;
  }
  const record = value as Partial<DesktopRuntimeConfig>;
  if (typeof record.aiBaseUrl !== "string" || !record.aiBaseUrl.trim()) {
    return null;
  }
  return {
    aiBaseUrl: record.aiBaseUrl.trim(),
    isDesktop: Boolean(record.isDesktop),
    platform:
      record.platform === "macos" ||
      record.platform === "windows" ||
      record.platform === "linux" ||
      record.platform === "unknown"
        ? record.platform
        : "unknown",
    secretStorageMode: record.secretStorageMode === "stronghold" ? "stronghold" : "plain_text",
    vaultState:
      record.vaultState === "unconfigured" ||
      record.vaultState === "locked" ||
      record.vaultState === "unlocked"
        ? record.vaultState
        : "unconfigured",
    vaultPath: typeof record.vaultPath === "string" ? record.vaultPath : "",
    storageRoot: typeof record.storageRoot === "string" ? record.storageRoot : "",
  };
}

export function getDesktopRuntimeConfig(): DesktopRuntimeConfig | null {
  if (typeof window === "undefined") {
    return null;
  }
  return normalizeDesktopConfig(window.__VIBE_LEARNER_DESKTOP_CONFIG__);
}

export function getAiBaseUrl(): string {
  return getDesktopRuntimeConfig()?.aiBaseUrl ?? DEFAULT_AI_BASE_URL;
}
