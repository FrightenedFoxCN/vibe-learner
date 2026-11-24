"use client";

import type { RuntimeSettings } from "@vibe-learner/shared";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";

import { getRuntimeSettings } from "../../lib/data/runtime-settings";
import { SettingsWriteHandoff } from "../../lib/settings-write-handoff";

interface RuntimeSettingsContextValue {
  settings: RuntimeSettings | null;
  loading: boolean;
  error: string;
  showDebugInfo: boolean;
  refresh: () => Promise<RuntimeSettings | null>;
  replaceSettings: (settings: RuntimeSettings) => void;
  getConfirmedSettings: () => RuntimeSettings | null;
  settingsWriteHandoff: SettingsWriteHandoff;
}

const RuntimeSettingsContext = createContext<RuntimeSettingsContextValue | null>(null);

export function RuntimeSettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<RuntimeSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const confirmedSettings = useRef<RuntimeSettings | null>(null);
  const refreshVersion = useRef(0);
  const [settingsWriteHandoff] = useState(() => new SettingsWriteHandoff());

  const replaceSettings = useCallback((next: RuntimeSettings) => {
    // The handoff may release before React commits the provider update.
    confirmedSettings.current = next;
    setSettings(next);
  }, []);

  const refresh = useCallback(async () => {
    const version = ++refreshVersion.current;
    const before = confirmedSettings.current;
    const isCurrent = () =>
      version === refreshVersion.current && confirmedSettings.current === before;
    setLoading(true);
    setError("");
    try {
      const nextSettings = await getRuntimeSettings();
      // A delayed read must not replace a newer confirmed write receipt.
      if (isCurrent()) replaceSettings(nextSettings);
      return confirmedSettings.current;
    } catch (err) {
      if (!isCurrent()) return confirmedSettings.current;
      setError(err instanceof Error ? err.message : String(err));
      return null;
    } finally {
      if (version === refreshVersion.current) setLoading(false);
    }
  }, [replaceSettings]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  return (
    <RuntimeSettingsContext.Provider
      value={{
        settings,
        loading,
        error,
        showDebugInfo: Boolean(settings?.showDebugInfo),
        refresh,
        replaceSettings,
        getConfirmedSettings: () => confirmedSettings.current,
        settingsWriteHandoff,
      }}
    >
      {children}
    </RuntimeSettingsContext.Provider>
  );
}

export function useRuntimeSettings() {
  const value = useContext(RuntimeSettingsContext);
  if (!value) {
    throw new Error("useRuntimeSettings must be used within RuntimeSettingsProvider");
  }
  return value;
}
