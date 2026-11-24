"use client";

import { useEffect, useRef } from "react";
import { usePathname } from "next/navigation";

import { useAppNavigator } from "../../lib/app-navigation";
import {
  DESKTOP_STARTUP_QUERY_KEY,
  DESKTOP_STARTUP_QUERY_VALUE,
  requiresDesktopVaultCreation,
  resolveDesktopStartupRequirement,
} from "../../lib/desktop-startup";
import { useDesktopVaultState } from "../../hooks/use-desktop-vault-state";
import { getDesktopRuntimeConfig } from "../../lib/runtime-config";
import { useRuntimeSettings } from "./runtime-settings-provider";

export function DesktopStartupGuard() {
  const pathname = usePathname();
  const appNavigator = useAppNavigator();
  const runtimeSettings = useRuntimeSettings();
  const vaultState = useDesktopVaultState();
  const checkedInitialSetup = useRef(false);

  useEffect(() => {
    if (vaultState === null) return;

    const needsCreation = requiresDesktopVaultCreation(vaultState);
    // Creation is a standing requirement; unlock/key reminders are startup-only.
    if (!needsCreation && (checkedInitialSetup.current || runtimeSettings.loading))
      return;
    checkedInitialSetup.current = true;

    const requirement = resolveDesktopStartupRequirement({
      isDesktop: true,
      startupError: getDesktopRuntimeConfig()?.startupError,
      vaultState,
      settings: runtimeSettings.settings,
    });
    if (!requirement || pathname === "/settings") {
      return;
    }

    appNavigator.replace("/settings", {
      [DESKTOP_STARTUP_QUERY_KEY]: DESKTOP_STARTUP_QUERY_VALUE,
    });
  }, [
    appNavigator,
    pathname,
    runtimeSettings.loading,
    runtimeSettings.settings,
    vaultState,
  ]);

  return null;
}
