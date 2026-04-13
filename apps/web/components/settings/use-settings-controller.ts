"use client";

import { useEffect, useEffectEvent, useRef, useState } from "react";

import type { RuntimeSettings } from "@vibe-learner/shared";
import { useRuntimeSettings } from "../runtime-settings-provider";
import { probeRuntimeOpenAIModels, updateRuntimeSettings } from "../../lib/data/runtime-settings";
import {
  AUTO_SAVE_DELAY_MS,
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

export interface SettingsController {
  settings: RuntimeSettings | null;
  numericDrafts: NumericDraftState;
  probeState: Record<ProbeScope, ScopeProbeState>;
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
  retrySave: () => void;
}

export function useSettingsController(): SettingsController {
  const runtimeSettings = useRuntimeSettings();
  const [settings, setSettings] = useState<RuntimeSettings | null>(null);
  const [advancedExpanded, setAdvancedExpanded] = useState(false);
  const [savePhase, setSavePhase] = useState<SettingsSavePhase>("idle");
  const [saveError, setSaveError] = useState("");
  const [lastSavedAt, setLastSavedAt] = useState("");
  const [isSaving, setIsSaving] = useState(false);
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
  const lastSavedSerializedRef = useRef("");
  const blockedSerializedRef = useRef("");
  const savingRef = useRef(false);

  useEffect(() => {
    settingsRef.current = settings;
  }, [settings]);

  useEffect(() => {
    if (initializedRef.current || !runtimeSettings.settings) {
      return;
    }
    initializedRef.current = true;
    settingsRef.current = runtimeSettings.settings;
    setSettings(runtimeSettings.settings);
    setNumericDrafts(buildNumericDrafts(runtimeSettings.settings));
    setLastSavedAt(runtimeSettings.settings.updatedAt);
    lastSavedSerializedRef.current = serializeSettings(runtimeSettings.settings);
    setSavePhase("saved");
  }, [runtimeSettings.settings]);

  const persistSnapshot = useEffectEvent(async (snapshot: RuntimeSettings, serialized: string) => {
    if (savingRef.current) {
      return;
    }

    savingRef.current = true;
    setIsSaving(true);
    setSavePhase("saving");
    setSaveError("");

    try {
      const next = await updateRuntimeSettings(buildRuntimeSettingsPatch(snapshot));
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
          lastCheckedAt: prev[scope].lastCheckedAt
        }
      }));
      return;
    }

    setProbeState((prev) => ({
      ...prev,
      [scope]: {
        ...prev[scope],
        loading: true,
        error: ""
      }
    }));

    try {
      const result = await probeRuntimeOpenAIModels(endpoint);
      setProbeState((prev) => ({
        ...prev,
        [scope]: {
          ...result,
          loading: false,
          lastCheckedAt: new Date().toISOString()
        }
      }));
    } catch (err) {
      setProbeState((prev) => ({
        ...prev,
        [scope]: {
          ...prev[scope],
          loading: false,
          available: false,
          models: [],
          capabilities: {},
          error: String(err)
        }
      }));
    }
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
    retrySave
  };
}
