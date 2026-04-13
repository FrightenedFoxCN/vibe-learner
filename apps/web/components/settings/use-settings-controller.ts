"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";

import type { DesktopVaultState, RuntimeSettings } from "@vibe-learner/shared";
import { useRuntimeSettings } from "../runtime-settings-provider";
import {
  applyRuntimeSessionSecrets,
  clearRuntimeSessionSecrets,
  probeRuntimeOpenAIModels,
  updateRuntimeSettings
} from "../../lib/data/runtime-settings";
import {
  clearDesktopVaultSecrets,
  emptyDesktopVaultSecrets,
  initializeDesktopVault,
  isDesktopVaultAvailable,
  isDesktopVaultUnlocked,
  loadDesktopVaultSecrets,
  lockDesktopVault as closeDesktopVault,
  saveDesktopVaultSecrets,
  unlockDesktopVault
} from "../../lib/desktop-vault";
import { getDesktopRuntimeConfig } from "../../lib/runtime-config";
import {
  AUTO_SAVE_DELAY_MS,
  buildProbeEndpointKey,
  buildNumericDrafts,
  buildRuntimeSettingsPatch,
  CAPABILITY_AUDIT_CONFIGS,
  capabilitySignalToBoolean,
  EMPTY_PROBE_STATE,
  type NumericDraftState,
  type NumericSettingKey,
  NUMERIC_SETTING_CONFIGS,
  parseNumericSetting,
  type ProbeScope,
  resolveCapabilitySignal,
  resolveScopeEndpoint,
  serializeSettings,
  type ScopeProbeState,
  type SettingsSavePhase
} from "./settings-utils";

export interface DesktopSecurityState {
  enabled: boolean;
  vaultState: DesktopVaultState;
  busy: boolean;
  error: string;
  vaultPath: string;
}

export interface SettingsController {
  settings: RuntimeSettings | null;
  numericDrafts: NumericDraftState;
  probeState: Record<ProbeScope, ScopeProbeState>;
  desktopSecurity: DesktopSecurityState;
  advancedExpanded: boolean;
  savePhase: SettingsSavePhase;
  saveError: string;
  lastSavedAt: string;
  loading: boolean;
  loadError: string;
  setAdvancedExpanded: (expanded: boolean) => void;
  setSettingField: <K extends keyof RuntimeSettings>(key: K, value: RuntimeSettings[K]) => void;
  setNumericDraft: (key: NumericSettingKey, value: string) => void;
  commitNumericSetting: (key: NumericSettingKey) => void;
  probeScope: (scope: ProbeScope) => Promise<void>;
  syncCapabilitySetting: (scope: Extract<ProbeScope, "plan" | "setting" | "chat">) => void;
  initializeDesktopVault: (password: string) => Promise<void>;
  unlockDesktopVault: (password: string) => Promise<void>;
  lockDesktopVault: () => Promise<void>;
  clearDesktopSecrets: () => Promise<void>;
  retrySave: () => void;
}

const PROBE_SCOPES: ProbeScope[] = ["global", "plan", "setting", "chat"];

interface CachedProbeResult {
  available: boolean;
  models: string[];
  capabilities: ScopeProbeState["capabilities"];
  error: string;
  lastCheckedAt: string;
  sourceScope: ProbeScope;
}

export function useSettingsController(): SettingsController {
  const runtimeSettings = useRuntimeSettings();
  const desktopRuntimeConfig = getDesktopRuntimeConfig();
  const desktopEnabled = Boolean(desktopRuntimeConfig?.isDesktop && isDesktopVaultAvailable());

  const [settings, setSettings] = useState<RuntimeSettings | null>(null);
  const [advancedExpanded, setAdvancedExpanded] = useState(false);
  const [savePhase, setSavePhase] = useState<SettingsSavePhase>("idle");
  const [saveError, setSaveError] = useState("");
  const [lastSavedAt, setLastSavedAt] = useState("");
  const [isSaving, setIsSaving] = useState(false);
  const [desktopSecurity, setDesktopSecurity] = useState<DesktopSecurityState>({
    enabled: desktopEnabled,
    vaultState: isDesktopVaultUnlocked() ? "unlocked" : desktopRuntimeConfig?.vaultState ?? "unconfigured",
    busy: false,
    error: "",
    vaultPath: desktopRuntimeConfig?.vaultPath ?? ""
  });
  const [numericDrafts, setNumericDrafts] = useState<NumericDraftState>({
    openaiTimeoutSeconds: "",
    openaiSettingTemperature: "",
    openaiChatTemperature: "",
    openaiSettingMaxTokens: "",
    openaiChatMaxTokens: "",
    openaiChatHistoryMessages: "",
    openaiChatToolMaxRounds: ""
  });
  const [probeState, setProbeState] = useState<Record<ProbeScope, ScopeProbeState>>({
    global: { ...EMPTY_PROBE_STATE },
    plan: { ...EMPTY_PROBE_STATE },
    setting: { ...EMPTY_PROBE_STATE },
    chat: { ...EMPTY_PROBE_STATE }
  });

  const initializedRef = useRef(false);
  const settingsRef = useRef<RuntimeSettings | null>(null);
  const desktopSecurityRef = useRef(desktopSecurity);
  const lastSavedSerializedRef = useRef("");
  const blockedSerializedRef = useRef("");
  const savingRef = useRef(false);
  const probeCacheRef = useRef<Map<string, CachedProbeResult>>(new Map());

  useEffect(() => {
    settingsRef.current = settings;
  }, [settings]);

  useEffect(() => {
    desktopSecurityRef.current = desktopSecurity;
  }, [desktopSecurity]);

  useEffect(() => {
    setDesktopSecurity((prev) => ({
      ...prev,
      enabled: desktopEnabled,
      vaultState: isDesktopVaultUnlocked()
        ? "unlocked"
        : prev.vaultState === "unlocked"
          ? prev.vaultState
          : desktopRuntimeConfig?.vaultState ?? "unconfigured",
      vaultPath: desktopRuntimeConfig?.vaultPath ?? ""
    }));
  }, [desktopEnabled, desktopRuntimeConfig?.vaultPath, desktopRuntimeConfig?.vaultState]);

  useEffect(() => {
    if (initializedRef.current || !runtimeSettings.settings) {
      return;
    }
    initializedRef.current = true;
    const nextSettings = runtimeSettings.settings;
    settingsRef.current = nextSettings;
    setSettings(nextSettings);
    setNumericDrafts(buildNumericDrafts(nextSettings));
    setLastSavedAt(nextSettings.updatedAt);
    lastSavedSerializedRef.current = serializeSettings(nextSettings);
    setSavePhase("saved");
  }, [runtimeSettings.settings]);

  useEffect(() => {
    if (!settings) {
      return;
    }

    setProbeState((prev) => {
      let changed = false;
      const next = { ...prev };

      for (const scope of PROBE_SCOPES) {
        const endpointKey = buildProbeEndpointKey(resolveScopeEndpoint(settings, scope));
        if (prev[scope].endpointKey === endpointKey) {
          continue;
        }

        const cached = endpointKey ? probeCacheRef.current.get(endpointKey) : null;
        next[scope] = cached
          ? buildScopeProbeState(cached, endpointKey, scope === cached.sourceScope ? null : cached.sourceScope)
          : { ...EMPTY_PROBE_STATE, endpointKey };
        changed = true;
      }

      return changed ? next : prev;
    });
  }, [settings]);

  const persistSnapshot = useEffectEvent(async (snapshot: RuntimeSettings, serialized: string) => {
    if (savingRef.current) {
      return;
    }

    savingRef.current = true;
    setIsSaving(true);
    setSavePhase("saving");
    setSaveError("");

    try {
      const shouldPersistSecrets =
        desktopSecurityRef.current.enabled && desktopSecurityRef.current.vaultState === "unlocked";

      if (shouldPersistSecrets) {
        const secrets = extractSecretPatch(snapshot);
        await saveDesktopVaultSecrets(secrets);
        await applyRuntimeSessionSecrets(secrets);
      }

      const backendNext = await updateRuntimeSettings(
        buildRuntimeSettingsPatch(snapshot, {
          includeSecrets: !desktopSecurityRef.current.enabled
        })
      );
      const next = shouldPersistSecrets
        ? mergeRuntimeSettingsWithSecrets(backendNext, extractSecretPatch(snapshot))
        : backendNext;
      const nextSerialized = serializeSettings(next);
      lastSavedSerializedRef.current = nextSerialized;
      blockedSerializedRef.current = "";
      setLastSavedAt(next.updatedAt);
      runtimeSettings.replaceSettings(next);

      if (settingsRef.current && serializeSettings(settingsRef.current) === serialized) {
        settingsRef.current = next;
        setSettings(next);
        setNumericDrafts(buildNumericDrafts(next));
      }

      setSavePhase("saved");
    } catch (err) {
      blockedSerializedRef.current = serialized;
      setSaveError(String(err));
      setSavePhase("error");
    } finally {
      savingRef.current = false;
      setIsSaving(false);
    }
  });

  useEffect(() => {
    if (!initializedRef.current || !settings || runtimeSettings.loading) {
      return;
    }

    const serialized = serializeSettings(settings);
    if (serialized === lastSavedSerializedRef.current) {
      if (!isSaving) {
        setSavePhase("saved");
      }
      return;
    }

    if (serialized === blockedSerializedRef.current) {
      if (!isSaving) {
        setSavePhase("error");
      }
      return;
    }

    if (!isSaving) {
      setSavePhase("pending");
    }
    if (isSaving) {
      return;
    }

    const timer = window.setTimeout(() => {
      void persistSnapshot(settings, serialized);
    }, AUTO_SAVE_DELAY_MS);

    return () => {
      window.clearTimeout(timer);
    };
  }, [isSaving, runtimeSettings.loading, settings, persistSnapshot]);

  function setSettingField<K extends keyof RuntimeSettings>(key: K, value: RuntimeSettings[K]) {
    setSaveError("");
    setSettings((prev) => (prev ? { ...prev, [key]: value } : prev));
  }

  function setNumericDraft(key: NumericSettingKey, value: string) {
    setNumericDrafts((prev) => ({ ...prev, [key]: value }));
  }

  function commitNumericSetting(key: NumericSettingKey) {
    if (!settings) {
      return;
    }
    const nextValue = parseNumericSetting(numericDrafts[key], NUMERIC_SETTING_CONFIGS[key]);
    setNumericDrafts((prev) => ({ ...prev, [key]: String(nextValue) }));
    setSettingField(key, nextValue as RuntimeSettings[typeof key]);
  }

  async function probeScope(scope: ProbeScope) {
    if (!settings) {
      return;
    }

    const endpoint = resolveScopeEndpoint(settings, scope);
    const endpointKey = buildProbeEndpointKey(endpoint);
    if (!endpoint.apiKey || !endpoint.baseUrl) {
      setProbeState((prev) => ({
        ...prev,
        [scope]: {
          ...prev[scope],
          loading: false,
          available: false,
          models: [],
          capabilities: {},
          error: "请先填写可用的访问密钥和服务地址",
          lastCheckedAt: prev[scope].lastCheckedAt,
          endpointKey,
          sharedFromScope: null
        }
      }));
      return;
    }

    const cached = probeCacheRef.current.get(endpointKey);
    if (cached) {
      const refreshed = {
        ...cached,
        sourceScope: scope,
      };
      probeCacheRef.current.set(endpointKey, refreshed);
      syncProbeScopesFromCache(settingsRef.current ?? settings, endpointKey, refreshed);
      return;
    }

    setProbeState((prev) => {
      const next = { ...prev };
      for (const candidate of PROBE_SCOPES) {
        if (buildProbeEndpointKey(resolveScopeEndpoint(settings, candidate)) !== endpointKey) {
          continue;
        }
        next[candidate] = {
          ...prev[candidate],
          loading: true,
          error: "",
          endpointKey,
          sharedFromScope: candidate === scope ? null : scope
        };
      }
      return next;
    });

    try {
      const result = await probeRuntimeOpenAIModels(endpoint);
      const nextCached: CachedProbeResult = {
        available: result.available,
        models: result.models,
        capabilities: result.capabilities,
        error: result.error,
        lastCheckedAt: new Date().toISOString(),
        sourceScope: scope
      };
      probeCacheRef.current.set(endpointKey, nextCached);
      syncProbeScopesFromCache(settingsRef.current ?? settings, endpointKey, nextCached);
    } catch (err) {
      setProbeState((prev) => ({
        ...prev,
        [scope]: {
          ...prev[scope],
          loading: false,
          available: false,
          models: [],
          capabilities: {},
          error: String(err),
          endpointKey,
          sharedFromScope: null
        }
      }));
    }
  }

  function syncProbeScopesFromCache(
    currentSettings: RuntimeSettings,
    endpointKey: string,
    cached: CachedProbeResult
  ) {
    setProbeState((prev) => {
      const next = { ...prev };

      for (const scope of PROBE_SCOPES) {
        if (buildProbeEndpointKey(resolveScopeEndpoint(currentSettings, scope)) !== endpointKey) {
          continue;
        }
        next[scope] = buildScopeProbeState(
          cached,
          endpointKey,
          scope === cached.sourceScope ? null : cached.sourceScope
        );
      }

      return next;
    });
  }

  function syncCapabilitySetting(scope: Extract<ProbeScope, "plan" | "setting" | "chat">) {
    if (!settings) {
      return;
    }
    const config = CAPABILITY_AUDIT_CONFIGS.find((item) => item.scope === scope);
    if (!config) {
      return;
    }
    const modelName = String(settings[config.modelKey] || "");
    const capability = probeState[scope].capabilities[modelName];
    const signal = resolveCapabilitySignal(capability, config.capabilityKey);
    const nextValue = capabilitySignalToBoolean(signal);
    if (nextValue === null) {
      return;
    }
    setSettingField(config.manualKey, nextValue as RuntimeSettings[typeof config.manualKey]);
  }

  async function activateDesktopVault(password: string, mode: "initialize" | "unlock") {
    if (!desktopEnabled) {
      return;
    }

    setDesktopSecurity((prev) => ({ ...prev, busy: true, error: "" }));
    try {
      if (mode === "initialize") {
        await initializeDesktopVault(password);
        if (settingsRef.current) {
          await saveDesktopVaultSecrets(extractSecretPatch(settingsRef.current));
        } else {
          await saveDesktopVaultSecrets(emptyDesktopVaultSecrets());
        }
      } else {
        await unlockDesktopVault(password);
      }

      const secrets = isDesktopVaultUnlocked()
        ? await loadDesktopVaultSecrets()
        : emptyDesktopVaultSecrets();
      const backendNext = await applyRuntimeSessionSecrets(secrets);
      const next = mergeRuntimeSettingsWithSecrets(backendNext, secrets);
      settingsRef.current = next;
      setSettings(next);
      setNumericDrafts(buildNumericDrafts(next));
      runtimeSettings.replaceSettings(next);
      lastSavedSerializedRef.current = serializeSettings(next);
      setLastSavedAt(next.updatedAt);
      setSavePhase("saved");
      setSaveError("");
      setDesktopSecurity((prev) => ({ ...prev, vaultState: "unlocked", busy: false, error: "" }));
    } catch (err) {
      setDesktopSecurity((prev) => ({
        ...prev,
        busy: false,
        error: String(err)
      }));
    }
  }

  async function handleLockDesktopVault() {
    if (!desktopEnabled) {
      return;
    }
    setDesktopSecurity((prev) => ({ ...prev, busy: true, error: "" }));
    try {
      await clearRuntimeSessionSecrets();
      await closeDesktopVault();
      const next = settingsRef.current ? maskRuntimeSecrets(settingsRef.current) : null;
      if (next) {
        settingsRef.current = next;
        setSettings(next);
        runtimeSettings.replaceSettings(next);
        lastSavedSerializedRef.current = serializeSettings(next);
      }
      setDesktopSecurity((prev) => ({
        ...prev,
        vaultState: "locked",
        busy: false,
        error: ""
      }));
    } catch (err) {
      setDesktopSecurity((prev) => ({
        ...prev,
        busy: false,
        error: String(err)
      }));
    }
  }

  async function handleClearDesktopSecrets() {
    if (!desktopEnabled) {
      return;
    }
    setDesktopSecurity((prev) => ({ ...prev, busy: true, error: "" }));
    try {
      if (isDesktopVaultUnlocked()) {
        await clearDesktopVaultSecrets();
      }
      const backendNext = await clearRuntimeSessionSecrets();
      const next = mergeRuntimeSettingsWithSecrets(backendNext, emptyDesktopVaultSecrets());
      settingsRef.current = next;
      setSettings(next);
      setNumericDrafts(buildNumericDrafts(next));
      runtimeSettings.replaceSettings(next);
      lastSavedSerializedRef.current = serializeSettings(next);
      setLastSavedAt(next.updatedAt);
      setSavePhase("saved");
      setDesktopSecurity((prev) => ({ ...prev, busy: false, error: "" }));
    } catch (err) {
      setDesktopSecurity((prev) => ({
        ...prev,
        busy: false,
        error: String(err)
      }));
    }
  }

  function retrySave() {
    if (!settings) {
      return;
    }
    blockedSerializedRef.current = "";
    setSavePhase("pending");
    void persistSnapshot(settings, serializeSettings(settings));
  }

  return {
    settings,
    numericDrafts,
    probeState,
    desktopSecurity,
    advancedExpanded,
    savePhase,
    saveError,
    lastSavedAt,
    loading: runtimeSettings.loading,
    loadError: runtimeSettings.error,
    setAdvancedExpanded,
    setSettingField,
    setNumericDraft,
    commitNumericSetting,
    probeScope,
    syncCapabilitySetting,
    initializeDesktopVault: async (password: string) => activateDesktopVault(password, "initialize"),
    unlockDesktopVault: async (password: string) => activateDesktopVault(password, "unlock"),
    lockDesktopVault: handleLockDesktopVault,
    clearDesktopSecrets: handleClearDesktopSecrets,
    retrySave
  };
}

function buildScopeProbeState(
  cached: CachedProbeResult,
  endpointKey: string,
  sharedFromScope: ProbeScope | null
): ScopeProbeState {
  return {
    loading: false,
    available: cached.available,
    models: cached.models,
    capabilities: cached.capabilities,
    error: cached.error,
    lastCheckedAt: cached.lastCheckedAt,
    endpointKey,
    sharedFromScope
  };
}

function extractSecretPatch(settings: RuntimeSettings) {
  return {
    openaiApiKey: settings.openaiApiKey.trim(),
    openaiPlanApiKey: settings.openaiPlanApiKey.trim(),
    openaiSettingApiKey: settings.openaiSettingApiKey.trim(),
    openaiChatApiKey: settings.openaiChatApiKey.trim()
  };
}

function mergeRuntimeSettingsWithSecrets(
  settings: RuntimeSettings,
  secrets: {
    openaiApiKey?: string;
    openaiPlanApiKey?: string;
    openaiSettingApiKey?: string;
    openaiChatApiKey?: string;
  },
  options: { configured?: boolean } = {}
): RuntimeSettings {
  const configured = options.configured;
  return {
    ...settings,
    openaiApiKey: String(secrets.openaiApiKey ?? ""),
    openaiPlanApiKey: String(secrets.openaiPlanApiKey ?? ""),
    openaiSettingApiKey: String(secrets.openaiSettingApiKey ?? ""),
    openaiChatApiKey: String(secrets.openaiChatApiKey ?? ""),
    openaiApiKeyConfigured:
      configured ?? Boolean(secrets.openaiApiKey || settings.openaiApiKeyConfigured),
    openaiPlanApiKeyConfigured:
      configured ?? Boolean(secrets.openaiPlanApiKey || secrets.openaiApiKey || settings.openaiPlanApiKeyConfigured),
    openaiSettingApiKeyConfigured:
      configured ?? Boolean(secrets.openaiSettingApiKey || secrets.openaiApiKey || settings.openaiSettingApiKeyConfigured),
    openaiChatApiKeyConfigured:
      configured ?? Boolean(secrets.openaiChatApiKey || secrets.openaiApiKey || settings.openaiChatApiKeyConfigured)
  };
}

function maskRuntimeSecrets(settings: RuntimeSettings): RuntimeSettings {
  return {
    ...settings,
    openaiApiKey: "",
    openaiApiKeyConfigured: false,
    openaiPlanApiKey: "",
    openaiPlanApiKeyConfigured: false,
    openaiSettingApiKey: "",
    openaiSettingApiKeyConfigured: false,
    openaiChatApiKey: "",
    openaiChatApiKeyConfigured: false
  };
}
