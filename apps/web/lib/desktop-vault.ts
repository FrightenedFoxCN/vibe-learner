"use client";

import { getDesktopRuntimeConfig } from "./runtime-config";

const CLIENT_NAME = "vibe-learner-runtime";

const SECRET_KEY_MAP = {
  openaiApiKey: "openai_api_key",
  openaiPlanApiKey: "openai_plan_api_key",
  openaiSettingApiKey: "openai_setting_api_key",
  openaiChatApiKey: "openai_chat_api_key"
} as const;

type SecretKey = keyof typeof SECRET_KEY_MAP;

export interface DesktopVaultSecrets {
  openaiApiKey: string;
  openaiPlanApiKey: string;
  openaiSettingApiKey: string;
  openaiChatApiKey: string;
}

let activeStronghold: any = null;
let activeClient: any = null;
let activeVaultPath = "";

export function isDesktopVaultAvailable() {
  const config = getDesktopRuntimeConfig();
  return Boolean(config?.isDesktop && config.vaultPath);
}

export function isDesktopVaultUnlocked() {
  return Boolean(activeStronghold && activeClient);
}

export async function initializeDesktopVault(password: string) {
  const { stronghold, client } = await loadStrongholdInstance(password);
  activeStronghold = stronghold;
  activeClient = client;
  activeVaultPath = stronghold.path;
  await stronghold.save();
}

export async function unlockDesktopVault(password: string) {
  const { stronghold, client } = await loadStrongholdInstance(password);
  activeStronghold = stronghold;
  activeClient = client;
  activeVaultPath = stronghold.path;
}

export async function lockDesktopVault() {
  if (activeStronghold) {
    await activeStronghold.unload();
  }
  activeStronghold = null;
  activeClient = null;
  activeVaultPath = "";
}

export async function loadDesktopVaultSecrets(): Promise<DesktopVaultSecrets> {
  const { store } = requireUnlockedStore();
  const values = await Promise.all(
    (Object.keys(SECRET_KEY_MAP) as SecretKey[]).map(async (key) => {
      const raw = await store.get(SECRET_KEY_MAP[key]);
      return [key, decodeSecret(raw)] as const;
    })
  );
  const records = Object.fromEntries(values) as Record<SecretKey, string>;
  return {
    openaiApiKey: records.openaiApiKey ?? "",
    openaiPlanApiKey: records.openaiPlanApiKey ?? "",
    openaiSettingApiKey: records.openaiSettingApiKey ?? "",
    openaiChatApiKey: records.openaiChatApiKey ?? ""
  };
}

export async function saveDesktopVaultSecrets(secrets: Partial<DesktopVaultSecrets>) {
  const { stronghold, store } = requireUnlockedStore();
  for (const key of Object.keys(SECRET_KEY_MAP) as SecretKey[]) {
    const value = String(secrets[key] ?? "");
    await store.insert(SECRET_KEY_MAP[key], encodeSecret(value));
  }
  await stronghold.save();
}

export async function clearDesktopVaultSecrets() {
  const { stronghold, store } = requireUnlockedStore();
  for (const key of Object.keys(SECRET_KEY_MAP) as SecretKey[]) {
    await store.remove(SECRET_KEY_MAP[key]);
  }
  await stronghold.save();
}

export function emptyDesktopVaultSecrets(): DesktopVaultSecrets {
  return {
    openaiApiKey: "",
    openaiPlanApiKey: "",
    openaiSettingApiKey: "",
    openaiChatApiKey: ""
  };
}

async function loadStrongholdInstance(password: string) {
  const runtimeConfig = getDesktopRuntimeConfig();
  if (!runtimeConfig?.isDesktop || !runtimeConfig.vaultPath) {
    throw new Error("desktop_vault_unavailable");
  }
  const strongholdModule = await import("@tauri-apps/plugin-stronghold");
  const stronghold = await strongholdModule.Stronghold.load(runtimeConfig.vaultPath, password);
  const client = await loadOrCreateClient(stronghold);
  return { stronghold, client };
}

async function loadOrCreateClient(stronghold: any) {
  try {
    return await stronghold.loadClient(CLIENT_NAME);
  } catch {
    return await stronghold.createClient(CLIENT_NAME);
  }
}

function requireUnlockedStore() {
  if (!activeStronghold || !activeClient || !activeVaultPath) {
    throw new Error("desktop_vault_locked");
  }
  return {
    stronghold: activeStronghold,
    store: activeClient.getStore()
  };
}

function encodeSecret(value: string) {
  return Array.from(new TextEncoder().encode(value));
}

function decodeSecret(value: Uint8Array | null) {
  if (!value) {
    return "";
  }
  return new TextDecoder().decode(value);
}
