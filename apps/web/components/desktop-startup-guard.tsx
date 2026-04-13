"use client";

import { useEffect } from "react";
import { usePathname } from "next/navigation";

import { useAppNavigator } from "../lib/app-navigation";
import {
  DESKTOP_STARTUP_GUARD_SESSION_KEY,
  DESKTOP_STARTUP_QUERY_KEY,
  DESKTOP_STARTUP_QUERY_VALUE,
  resolveDesktopStartupRequirement
} from "../lib/desktop-startup";
import { getDesktopRuntimeConfig } from "../lib/runtime-config";
import { useRuntimeSettings } from "./runtime-settings-provider";

export function DesktopStartupGuard() {
  const pathname = usePathname();
  const appNavigator = useAppNavigator();
  const runtimeSettings = useRuntimeSettings();

  useEffect(() => {
    if (typeof window === "undefined" || runtimeSettings.loading) {
      return;
    }

    const desktopRuntimeConfig = getDesktopRuntimeConfig();
    if (!desktopRuntimeConfig?.isDesktop) {
      return;
    }

    if (window.sessionStorage.getItem(DESKTOP_STARTUP_GUARD_SESSION_KEY) === "1") {
      return;
    }
    window.sessionStorage.setItem(DESKTOP_STARTUP_GUARD_SESSION_KEY, "1");

    const requirement = resolveDesktopStartupRequirement({
      isDesktop: desktopRuntimeConfig.isDesktop,
      startupError: desktopRuntimeConfig.startupError,
      vaultState: desktopRuntimeConfig.vaultState,
      settings: runtimeSettings.settings
    });
    if (!requirement || pathname === "/settings") {
      return;
    }

    appNavigator.replace("/settings", {
      [DESKTOP_STARTUP_QUERY_KEY]: DESKTOP_STARTUP_QUERY_VALUE
    });
  }, [appNavigator, pathname, runtimeSettings.loading, runtimeSettings.settings]);

  return null;
}
