export type DesktopPlatform = "macos" | "windows" | "linux" | "unknown";

export type DesktopSecretStorageMode = "plain_text" | "stronghold";

export type DesktopVaultState = "unconfigured" | "locked" | "unlocked";

export interface DesktopRuntimeConfig {
  aiBaseUrl: string;
  isDesktop: boolean;
  platform: DesktopPlatform;
  secretStorageMode: DesktopSecretStorageMode;
  vaultState: DesktopVaultState;
  vaultPath: string;
  storageRoot: string;
}
