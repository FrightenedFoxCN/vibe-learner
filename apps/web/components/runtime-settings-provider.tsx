"use client";

import type { RuntimeSettings } from "@vibe-learner/shared";
import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

import { getRuntimeSettings } from "../lib/data/runtime-settings";

interface RuntimeSettingsContextValue {
  settings: RuntimeSettings | null;
  loading: boolean;
  error: string;
  showDebugInfo: boolean;
  refresh: () => Promise<RuntimeSettings | null>;
  replaceSettings: (settings: RuntimeSettings) => void;
}

const RuntimeSettingsContext = createContext<RuntimeSettingsContextValue | null>(null);

export function RuntimeSettingsProvider({ children }: { children: ReactNode }) {
  const [settings, setSettings] = useState<RuntimeSettings | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const refresh = async () => {
    setLoading(true);
    setError("");
    try {
      const nextSettings = await getRuntimeSettings();
      setSettings(nextSettings);
      return nextSettings;
    } catch (err) {
      setError(String(err));
      return null;
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    void refresh();
  }, []);

  return (
    <RuntimeSettingsContext.Provider
      value={{
        settings,
        loading,
        error,
        showDebugInfo: Boolean(settings?.showDebugInfo),
        refresh,
        replaceSettings: setSettings
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
