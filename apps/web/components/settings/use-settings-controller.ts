"use client";

import {
  useEffect,
  useEffectEvent,
  useRef,
  useState,
  useSyncExternalStore,
} from "react";

import type {
  DesktopVaultState,
  RuntimeFeatureProbeName,
  RuntimeSettings,
} from "@vibe-learner/shared";
import { useSettingsSave } from "../../hooks/use-settings-save";
import { useRuntimeSettings } from "../layout/runtime-settings-provider";
import {
  applyRuntimeSessionSecrets,
  clearRuntimeSessionSecrets,
  probeRuntimeOpenAIModels,
  updateRuntimeSettings,
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
  unlockDesktopVault,
} from "../../lib/desktop-vault";
import { enqueueVaultOperation, saveWithVault } from "../../lib/desktop-vault-workflow";
import { getDesktopRuntimeConfig } from "../../lib/runtime-config";
import {
  resolveSettingsPublication,
  type SettingsForm,
  type SettingsPublication,
} from "./settings-publication";
import {
  AUTO_SAVE_DELAY_MS,
  buildProbeEndpointKey,
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
  resolveProbeConflictScopes,
  resolveScopeEndpoint,
  serializeSettings,
  type ScopeProbeState,
  type SettingsSavePhase,
} from "./settings-utils";

export interface DesktopSecurityState {
  enabled: boolean;
  vaultState: DesktopVaultState;
  busy: boolean;
  error: string;
  vaultPath: string;
  startupError: string;
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
  setSettingField: <K extends keyof RuntimeSettings>(
    key: K,
    value: RuntimeSettings[K],
  ) => void;
  setNumericDraft: (key: NumericSettingKey, value: string) => void;
  commitNumericSetting: (key: NumericSettingKey) => boolean;
  probeScope: (scope: ProbeScope) => Promise<void>;
  syncCapabilitySetting: (
    scope: Extract<ProbeScope, "plan" | "setting" | "chat">,
  ) => void;
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
  featureReadiness: ScopeProbeState["featureReadiness"];
  error: string;
  lastCheckedAt: string;
  sourceScope: ProbeScope;
}

export function useSettingsController(): SettingsController {
  const runtimeSettings = useRuntimeSettings();
  const { settingsWriteHandoff } = runtimeSettings;
  const handoff = useSyncExternalStore(
    settingsWriteHandoff.subscribe,
    settingsWriteHandoff.getSnapshot,
    settingsWriteHandoff.getServerSnapshot,
  );
  const desktopRuntimeConfig = getDesktopRuntimeConfig();
  const desktopEnabled = Boolean(
    desktopRuntimeConfig?.isDesktop && isDesktopVaultAvailable(),
  );

  const [advancedExpanded, setAdvancedExpanded] = useState(false);
  const [savePhase, setSavePhase] = useState<SettingsSavePhase>("idle");
  const [saveError, setSaveError] = useState("");
  const [lastSavedAt, setLastSavedAt] = useState("");
  const [desktopSecurity, setDesktopSecurity] = useState<DesktopSecurityState>({
    enabled: desktopEnabled,
    vaultState: isDesktopVaultUnlocked()
      ? "unlocked"
      : (desktopRuntimeConfig?.vaultState ?? "unconfigured"),
    busy: false,
    error: "",
    vaultPath: desktopRuntimeConfig?.vaultPath ?? "",
    startupError: desktopRuntimeConfig?.startupError ?? "",
  });
  const [form, setForm] = useState<SettingsForm>({
    settings: null,
    numericDrafts: {
      openaiTimeoutSeconds: "",
      openaiSettingTemperature: "",
      openaiChatTemperature: "",
      openaiSettingMaxTokens: "",
      openaiChatMaxTokens: "",
      openaiChatHistoryMessages: "",
      openaiChatToolMaxRounds: "",
    },
  });
  const { settings, numericDrafts } = form;
  const [probeState, setProbeState] = useState<Record<ProbeScope, ScopeProbeState>>({
    global: { ...EMPTY_PROBE_STATE },
    plan: { ...EMPTY_PROBE_STATE },
    setting: { ...EMPTY_PROBE_STATE },
    chat: { ...EMPTY_PROBE_STATE },
  });

  const initializedRef = useRef(false);
  const formRef = useRef(form);
  const desktopSecurityRef = useRef(desktopSecurity);
  const vaultTransitionRef = useRef(false);
  const vaultVersionRef = useRef(0);
  const probeCacheRef = useRef<Map<string, CachedProbeResult>>(new Map());
  const activeProbeRef = useRef(new Map<string, symbol>());

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
          : (desktopRuntimeConfig?.vaultState ?? "unconfigured"),
      vaultPath: desktopRuntimeConfig?.vaultPath ?? "",
      startupError: desktopRuntimeConfig?.startupError ?? "",
    }));
  }, [
    desktopEnabled,
    desktopRuntimeConfig?.startupError,
    desktopRuntimeConfig?.vaultPath,
    desktopRuntimeConfig?.vaultState,
  ]);

  useEffect(() => {
    if (!settings) {
      return;
    }

    setProbeState((prev) => {
      let changed = false;
      const next = { ...prev };

      for (const scope of PROBE_SCOPES) {
        const endpointKey = buildProbeEndpointKey(
          resolveScopeEndpoint(settings, scope),
        );
        if (prev[scope].endpointKey === endpointKey) {
          continue;
        }

        const cached = endpointKey ? probeCacheRef.current.get(endpointKey) : null;
        next[scope] = cached
          ? buildScopeProbeState(
              cached,
              endpointKey,
              scope === cached.sourceScope ? null : cached.sourceScope,
            )
          : { ...EMPTY_PROBE_STATE, endpointKey };
        changed = true;
      }

      return changed ? next : prev;
    });
  }, [settings]);

  // Follow the editor's submitted lineage while newer edits are queued. A
  // receipt may also include fields changed by another client: those fields
  // are not new intent in a queued snapshot made before the receipt.
  const saveBaselineRef = useRef<RuntimeSettings | null>(null);
  const saveCoordinator = useSettingsSave(
    {
      serialize: serializeSettings,
      persist: async (snapshot: RuntimeSettings, context) => {
        const shouldUseVault = desktopSecurityRef.current.enabled;
        const baseline = saveBaselineRef.current ?? undefined;
        const patch = buildRuntimeSettingsPatch(snapshot, {
          includeSecrets: !shouldUseVault,
          baseline,
        });
        const commit = () => updateRuntimeSettings(patch, context);
        const finish = (confirmed: RuntimeSettings) => {
          const current = formRef.current.settings;
          saveBaselineRef.current =
            current && serializeSettings(current) === serializeSettings(snapshot)
              ? confirmed
              : snapshot;
          return confirmed;
        };
        if (!shouldUseVault) return finish(await commit());
        const version = vaultVersionRef.current;
        return enqueueVaultOperation(async () => {
          if (version !== vaultVersionRef.current || vaultTransitionRef.current) {
            throw new Error("保险库状态正在变更，该次自动保存未应用。");
          }
          const secrets = extractSecretPatch(snapshot);
          const previousSecrets = baseline && extractSecretPatch(baseline);
          const secretChanged =
            !previousSecrets ||
            (Object.keys(secrets) as (keyof typeof secrets)[]).some(
              (key) => secrets[key] !== previousSecrets[key],
            );
          if (
            !isDesktopVaultUnlocked() ||
            desktopSecurityRef.current.vaultState !== "unlocked"
          ) {
            return finish(await commit());
          }
          if (!secretChanged)
            return finish(mergeRuntimeSettingsWithSecrets(await commit(), secrets));
          const backendNext = await saveWithVault(
            {
              read: () => loadDesktopVaultSecrets(context),
              store: (value) => saveDesktopVaultSecrets(value, context),
              apply: (value) => applyRuntimeSessionSecrets(value, context),
              commit,
            },
            secrets,
          );
          return finish(mergeRuntimeSettingsWithSecrets(backendNext, secrets));
        });
      },
      saved: (next, submittedKey) =>
        publishSettings({ kind: "autosave", settings: next, submittedKey }),
      status: (phase, error) => {
        setSavePhase(phase);
        if (phase !== "error" || error) setSaveError(error);
      },
    },
    AUTO_SAVE_DELAY_MS,
    settingsWriteHandoff,
  );

  function publishForm(next: SettingsForm) {
    // Async receipts must inspect the latest input, even before React commits.
    formRef.current = next;
    setForm(next);
  }

  function publishSettings(publication: SettingsPublication) {
    const current = formRef.current;
    const next = resolveSettingsPublication(current, publication);
    if (next.form !== current) publishForm(next.form);
    if (next.runtimeSettings) runtimeSettings.replaceSettings(next.runtimeSettings);
    setLastSavedAt(next.lastSavedAt);
    if (next.baseline) {
      saveBaselineRef.current = next.baseline;
      saveCoordinator.acceptSaved(next.baseline);
      setSavePhase("saved");
      setSaveError("");
    }
  }

  const initializeForm = useEffectEvent(() => {
    // Recheck synchronously: outgoing layout cleanup can run after the
    // incoming render, but before this effect runs.
    if (initializedRef.current) return;
    const next = settingsWriteHandoff.readBaseline(
      runtimeSettings.getConfirmedSettings,
    );
    if (!next) return;
    initializedRef.current = true;
    setVaultState(
      isDesktopVaultUnlocked()
        ? "unlocked"
        : (getDesktopRuntimeConfig()?.vaultState ?? "unconfigured"),
    );
    publishSettings({ kind: "initial", settings: next });
  });
  useEffect(() => {
    initializeForm();
  }, [runtimeSettings.settings, handoff]);

  function setSettingField<K extends keyof RuntimeSettings>(
    key: K,
    value: RuntimeSettings[K],
  ) {
    const current = formRef.current;
    if (vaultTransitionRef.current || !current.settings) return;
    setSaveError("");
    const next = { ...current.settings, [key]: value };
    publishForm({ ...current, settings: next });
    // Admit the input in the same turn, even if navigation prevents a render.
    saveCoordinator.edit(next);
  }

  function setNumericDraft(key: NumericSettingKey, value: string) {
    const current = formRef.current;
    publishForm({
      ...current,
      numericDrafts: { ...current.numericDrafts, [key]: value },
    });
  }

  function commitNumericSetting(key: NumericSettingKey) {
    const current = formRef.current;
    if (!current.settings || vaultTransitionRef.current) return true;
    const nextValue = parseNumericSetting(
      current.numericDrafts[key],
      NUMERIC_SETTING_CONFIGS[key],
    );
    if (nextValue === null) return false;
    setNumericDraft(key, String(nextValue));
    setSettingField(key, nextValue);
    return true;
  }

  async function probeScope(scope: ProbeScope) {
    if (!settings) {
      return;
    }

    const endpoint = resolveScopeEndpoint(settings, scope);
    const endpointKey = buildProbeEndpointKey(endpoint);
    const featureProbe = resolveFeatureProbe(settings, scope);
    if (!endpoint.apiKey || !endpoint.baseUrl) {
      setProbeState((prev) => ({
        ...prev,
        [scope]: {
          ...prev[scope],
          loading: false,
          available: false,
          models: [],
          capabilities: {},
          featureReadiness: prev[scope].featureReadiness,
          error: "请先填写可用的访问密钥和服务地址",
          lastCheckedAt: prev[scope].lastCheckedAt,
          endpointKey,
          sharedFromScope: null,
        },
      }));
      return;
    }

    // Clicks always send a new request. Cached results are for sharing evidence, not skipping probes.
    const requestId = Symbol();
    activeProbeRef.current.set(endpointKey, requestId);
    const stillActive = () => activeProbeRef.current.get(endpointKey) === requestId;

    setProbeState((prev) => {
      const next = { ...prev };
      for (const candidate of resolveProbeConflictScopes(settings, scope)) {
        next[candidate] = {
          ...prev[candidate],
          loading: true,
          error: "",
          endpointKey,
          sharedFromScope: candidate === scope ? null : scope,
        };
      }
      return next;
    });

    try {
      const result = await probeRuntimeOpenAIModels({
        ...endpoint,
        model: featureProbe.model,
        features: featureProbe.features,
      });
      if (!stillActive()) return;
      const cached = probeCacheRef.current.get(endpointKey);
      const nextCached: CachedProbeResult = {
        available: result.available,
        models: result.models,
        capabilities: result.capabilities,
        featureReadiness: {
          ...(cached?.featureReadiness ?? {}),
          ...result.featureReadiness,
        },
        error: result.error,
        lastCheckedAt: new Date().toISOString(),
        sourceScope: scope,
      };
      probeCacheRef.current.set(endpointKey, nextCached);
      syncProbeScopesFromCache(
        formRef.current.settings ?? settings,
        endpointKey,
        nextCached,
      );
    } catch (err) {
      if (!stillActive()) return;
      const failure: CachedProbeResult = {
        available: false,
        models: [],
        capabilities: {},
        featureReadiness: {},
        error: String(err),
        lastCheckedAt: new Date().toISOString(),
        sourceScope: scope,
      };
      probeCacheRef.current.set(endpointKey, failure);
      syncProbeScopesFromCache(
        formRef.current.settings ?? settings,
        endpointKey,
        failure,
      );
    } finally {
      if (stillActive()) activeProbeRef.current.delete(endpointKey);
    }
  }

  function syncProbeScopesFromCache(
    currentSettings: RuntimeSettings,
    endpointKey: string,
    cached: CachedProbeResult,
  ) {
    setProbeState((prev) => {
      const next = { ...prev };

      for (const scope of PROBE_SCOPES) {
        if (
          buildProbeEndpointKey(resolveScopeEndpoint(currentSettings, scope)) !==
          endpointKey
        ) {
          continue;
        }
        next[scope] = buildScopeProbeState(
          cached,
          endpointKey,
          scope === cached.sourceScope ? null : cached.sourceScope,
        );
      }

      return next;
    });
  }

  function syncCapabilitySetting(
    scope: Extract<ProbeScope, "plan" | "setting" | "chat">,
  ) {
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
    setSettingField(
      config.manualKey,
      nextValue as RuntimeSettings[typeof config.manualKey],
    );
  }

  function publishVaultSettings(next: RuntimeSettings) {
    initializedRef.current = true;
    publishSettings({ kind: "vault", settings: next });
  }

  function setVaultState(vaultState: DesktopVaultState) {
    desktopSecurityRef.current = { ...desktopSecurityRef.current, vaultState };
    setDesktopSecurity((prev) => ({ ...prev, vaultState }));
  }

  async function runVaultTransition(operation: () => Promise<void>) {
    if (
      !desktopEnabled ||
      vaultTransitionRef.current ||
      settingsWriteHandoff.isPending()
    )
      return;
    vaultTransitionRef.current = true;
    vaultVersionRef.current++;
    saveCoordinator.discardPending();
    setDesktopSecurity((prev) => ({ ...prev, busy: true, error: "" }));
    const completion = enqueueVaultOperation(operation)
      .catch((error) => {
        setDesktopSecurity((prev) => ({ ...prev, error: String(error) }));
      })
      .finally(() => {
        vaultTransitionRef.current = false;
        setDesktopSecurity((prev) => ({ ...prev, busy: false }));
      });
    // A new editor cannot hydrate credentials mid-transition, even if this
    // page unmounts while the shared Vault queue is still running.
    settingsWriteHandoff.track(completion);
    await completion;
  }

  async function activateDesktopVault(password: string, mode: "initialize" | "unlock") {
    await runVaultTransition(async () => {
      let created = false;
      let applyAttempted = false;
      try {
        if (mode === "initialize") {
          await initializeDesktopVault(password);
          created = true;
          const current = formRef.current.settings;
          const initial = current
            ? extractSecretPatch(current)
            : emptyDesktopVaultSecrets();
          await saveDesktopVaultSecrets(initial);
        } else {
          await unlockDesktopVault(password);
        }
        const secrets = await loadDesktopVaultSecrets();
        applyAttempted = true;
        const next = await applyRuntimeSessionSecrets(secrets);
        publishVaultSettings(mergeRuntimeSettingsWithSecrets(next, secrets));
        setVaultState("unlocked");
      } catch (error) {
        const failures: string[] = [];
        if (applyAttempted) {
          try {
            const next = await clearRuntimeSessionSecrets();
            publishVaultSettings(maskRuntimeSecrets(next));
          } catch {
            failures.push("运行时密钥未确认清除");
          }
        }
        if (isDesktopVaultUnlocked()) {
          try {
            await closeDesktopVault();
          } catch {
            failures.push("保险库未确认锁定");
          }
        }
        if (created || mode === "unlock") setVaultState("locked");
        if (failures.length)
          throw new Error(failures.join("；") + "，请重试或重启应用。", {
            cause: error,
          });
        throw error;
      }
    });
  }

  async function handleLockDesktopVault() {
    await runVaultTransition(async () => {
      const next = await clearRuntimeSessionSecrets();
      publishVaultSettings(maskRuntimeSecrets(next));
      setVaultState("locked");
      try {
        await closeDesktopVault();
      } catch (error) {
        throw new Error("运行时密钥已清除，但保险库未确认关闭。请重启应用。", {
          cause: error,
        });
      }
    });
  }

  async function handleClearDesktopSecrets() {
    await runVaultTransition(async () => {
      const next = await clearRuntimeSessionSecrets();
      publishVaultSettings(maskRuntimeSecrets(next));
      try {
        if (
          desktopSecurityRef.current.vaultState === "unlocked" &&
          isDesktopVaultUnlocked()
        ) {
          await clearDesktopVaultSecrets();
        }
      } catch (error) {
        setVaultState("locked");
        try {
          await closeDesktopVault();
        } catch {
          /* report both as unconfirmed */
        }
        throw new Error(
          "运行时密钥已清除，但无法确认磁盘保险库已清空；请重启后检查。",
          { cause: error },
        );
      }
    });
  }

  function retrySave() {
    const current = formRef.current.settings;
    if (!current || vaultTransitionRef.current) return;
    saveCoordinator.retry(current);
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
    loading: runtimeSettings.loading || (!settings && handoff.pending),
    loadError: runtimeSettings.error,
    setAdvancedExpanded,
    setSettingField,
    setNumericDraft,
    commitNumericSetting,
    probeScope,
    syncCapabilitySetting,
    initializeDesktopVault: async (password: string) =>
      activateDesktopVault(password, "initialize"),
    unlockDesktopVault: async (password: string) =>
      activateDesktopVault(password, "unlock"),
    lockDesktopVault: handleLockDesktopVault,
    clearDesktopSecrets: handleClearDesktopSecrets,
    retrySave,
  };
}

function resolveFeatureProbe(
  settings: RuntimeSettings,
  scope: ProbeScope,
): { model: string; features: RuntimeFeatureProbeName[] } {
  if (scope === "plan") {
    return { model: settings.openaiPlanModel.trim(), features: ["plan"] };
  }
  if (scope === "setting") {
    return {
      model: settings.openaiSettingModel.trim(),
      features: ["persona", "scene"],
    };
  }
  if (scope === "chat") {
    return {
      model: settings.openaiChatModel.trim(),
      features: ["study", "tavern"],
    };
  }
  return { model: "", features: [] };
}

function buildScopeProbeState(
  cached: CachedProbeResult,
  endpointKey: string,
  sharedFromScope: ProbeScope | null,
): ScopeProbeState {
  return {
    loading: false,
    available: cached.available,
    models: cached.models,
    capabilities: cached.capabilities,
    featureReadiness: cached.featureReadiness,
    error: cached.error,
    lastCheckedAt: cached.lastCheckedAt,
    endpointKey,
    sharedFromScope,
  };
}

function extractSecretPatch(settings: RuntimeSettings) {
  return {
    openaiApiKey: settings.openaiApiKey.trim(),
    openaiPlanApiKey: settings.openaiPlanApiKey.trim(),
    openaiSettingApiKey: settings.openaiSettingApiKey.trim(),
    openaiChatApiKey: settings.openaiChatApiKey.trim(),
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
  options: { configured?: boolean } = {},
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
      configured ??
      Boolean(
        secrets.openaiPlanApiKey ||
        secrets.openaiApiKey ||
        settings.openaiPlanApiKeyConfigured,
      ),
    openaiSettingApiKeyConfigured:
      configured ??
      Boolean(
        secrets.openaiSettingApiKey ||
        secrets.openaiApiKey ||
        settings.openaiSettingApiKeyConfigured,
      ),
    openaiChatApiKeyConfigured:
      configured ??
      Boolean(
        secrets.openaiChatApiKey ||
        secrets.openaiApiKey ||
        settings.openaiChatApiKeyConfigured,
      ),
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
    openaiChatApiKeyConfigured: false,
  };
}
