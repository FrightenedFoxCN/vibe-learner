"use client";

import type { Client, Stronghold } from "@tauri-apps/plugin-stronghold";
import { requiresDesktopVaultCreation } from "./desktop-startup.ts";
import { createDesktopVaultSession } from "./desktop-vault-state.ts";
import { getDesktopRuntimeConfig } from "./runtime-config";

import { observeLocalAction } from "./diagnostic-actions.ts";
import type { DiagnosticContext } from "./diagnostics";

const CLIENT_NAME = "vibe-learner-runtime";
const DESKTOP_VAULT_BOOTSTRAP_EVENT = "vibe-learner:desktop-vault-bootstrap";

const SECRET_KEY_MAP = {
  openaiApiKey: "openai_api_key",
  openaiPlanApiKey: "openai_plan_api_key",
  openaiSettingApiKey: "openai_setting_api_key",
  openaiChatApiKey: "openai_chat_api_key",
} as const;

type SecretKey = keyof typeof SECRET_KEY_MAP;

export interface DesktopVaultSecrets {
  openaiApiKey: string;
  openaiPlanApiKey: string;
  openaiSettingApiKey: string;
  openaiChatApiKey: string;
}

const vault = createDesktopVaultSession<{ stronghold: Stronghold; client: Client }>(
  () => {
    const config = getDesktopRuntimeConfig();
    return config?.isDesktop ? config.vaultState : null;
  },
);

export const getDesktopVaultState = vault.getSnapshot;
export const getServerDesktopVaultState = () => null;

export function subscribeDesktopVaultState(listener: () => void) {
  const unsubscribe = vault.subscribe(listener);
  window.addEventListener(DESKTOP_VAULT_BOOTSTRAP_EVENT, listener);
  return () => {
    unsubscribe();
    window.removeEventListener(DESKTOP_VAULT_BOOTSTRAP_EVENT, listener);
  };
}

export function isDesktopVaultAvailable() {
  const config = getDesktopRuntimeConfig();
  return Boolean(config?.isDesktop && config.vaultPath);
}

export function isDesktopVaultUnlocked() {
  return getDesktopVaultState() === "unlocked";
}

export function isDesktopVaultCreationRequired() {
  return requiresDesktopVaultCreation(getDesktopVaultState());
}

export async function initializeDesktopVault(
  password: string,
  context?: DiagnosticContext,
) {
  return observeLocalAction(
    "vault_create",
    async () => vault.activate(await loadStrongholdInstance(password), "initialize"),
    { context },
  );
}

export async function unlockDesktopVault(
  password: string,
  context?: DiagnosticContext,
) {
  return observeLocalAction(
    "vault_unlock",
    async () => vault.activate(await loadStrongholdInstance(password), "unlock"),
    { context },
  );
}

export async function lockDesktopVault(context?: DiagnosticContext) {
  return observeLocalAction("vault_lock", () => vault.lock(), { context });
}

export async function loadDesktopVaultSecrets(
  context?: DiagnosticContext,
): Promise<DesktopVaultSecrets> {
  return observeLocalAction(
    "vault_load_secrets",
    () => loadDesktopVaultSecretsUnobserved(),
    { context },
  );
}

async function loadDesktopVaultSecretsUnobserved(): Promise<DesktopVaultSecrets> {
  const { store } = requireUnlockedStore();
  const values = await Promise.all(
    (Object.keys(SECRET_KEY_MAP) as SecretKey[]).map(async (key) => {
      const raw = await store.get(SECRET_KEY_MAP[key]);
      return [key, decodeSecret(raw)] as const;
    }),
  );
  const records = Object.fromEntries(values) as Record<SecretKey, string>;
  return {
    openaiApiKey: records.openaiApiKey ?? "",
    openaiPlanApiKey: records.openaiPlanApiKey ?? "",
    openaiSettingApiKey: records.openaiSettingApiKey ?? "",
    openaiChatApiKey: records.openaiChatApiKey ?? "",
  };
}

export async function saveDesktopVaultSecrets(
  secrets: Partial<DesktopVaultSecrets>,
  context?: DiagnosticContext,
) {
  return observeLocalAction(
    "vault_save_secrets",
    () => saveDesktopVaultSecretsUnobserved(secrets),
    { context },
  );
}

async function saveDesktopVaultSecretsUnobserved(
  secrets: Partial<DesktopVaultSecrets>,
) {
  const { stronghold, store } = requireUnlockedStore();
  for (const key of Object.keys(SECRET_KEY_MAP) as SecretKey[]) {
    const value = String(secrets[key] ?? "");
    await store.insert(SECRET_KEY_MAP[key], encodeSecret(value));
  }
  await stronghold.save();
}

export async function clearDesktopVaultSecrets(context?: DiagnosticContext) {
  return observeLocalAction(
    "vault_clear_secrets",
    () => clearDesktopVaultSecretsUnobserved(),
    { context },
  );
}

async function clearDesktopVaultSecretsUnobserved() {
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
    openaiChatApiKey: "",
  };
}

async function loadStrongholdInstance(password: string) {
  const runtimeConfig = getDesktopRuntimeConfig();
  if (!runtimeConfig?.isDesktop || !runtimeConfig.vaultPath) {
    throw new Error("desktop_vault_unavailable");
  }
  const strongholdModule = await import("@tauri-apps/plugin-stronghold");
  const stronghold = await strongholdModule.Stronghold.load(
    runtimeConfig.vaultPath,
    password,
  );
  const client = await loadOrCreateClient(stronghold);
  return { stronghold, client };
}

async function loadOrCreateClient(stronghold: Stronghold) {
  try {
    return await stronghold.loadClient(CLIENT_NAME);
  } catch {
    return await stronghold.createClient(CLIENT_NAME);
  }
}

function requireUnlockedStore() {
  const session = vault.getSession();
  if (!session) {
    throw new Error("desktop_vault_locked");
  }
  return { stronghold: session.stronghold, store: session.client.getStore() };
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
