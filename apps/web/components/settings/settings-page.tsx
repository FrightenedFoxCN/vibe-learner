"use client";

import { useMemo } from "react";
import { useSearchParams } from "next/navigation";

import { TopNav } from "../top-nav";
import {
  DESKTOP_STARTUP_QUERY_KEY,
  DESKTOP_STARTUP_QUERY_VALUE,
  resolveDesktopStartupRequirement
} from "../../lib/desktop-startup";
import { settingsStyles as styles } from "./settings-styles";
import {
  AutoSaveStatusBar,
  CapabilityAuditCard,
  ConnectionModelsCard,
  DesktopSecurityCard,
  DebugVisibilityCard,
  ProviderCard,
  SettingsHeader,
  StartupRequirementCard,
  AdvancedSettingsCard
} from "./settings-sections";
import { usePageDebugSnapshot } from "../page-debug-context";
import { useSettingsController } from "./use-settings-controller";
import { buildSettingsDebugSnapshot } from "./settings-debug-snapshot";

export function SettingsPage() {
  const controller = useSettingsController();
  const searchParams = useSearchParams();
  const showDesktopSecurityCard =
    controller.desktopSecurity.enabled || Boolean(controller.desktopSecurity.startupError);
  const startupRequirement = useMemo(() => {
    if (searchParams.get(DESKTOP_STARTUP_QUERY_KEY) !== DESKTOP_STARTUP_QUERY_VALUE) {
      return null;
    }
    return resolveDesktopStartupRequirement({
      isDesktop: controller.desktopSecurity.enabled,
      startupError: controller.desktopSecurity.startupError,
      vaultState: controller.desktopSecurity.vaultState,
      settings: controller.settings
    });
  }, [
    controller.desktopSecurity.enabled,
    controller.desktopSecurity.startupError,
    controller.desktopSecurity.vaultState,
    controller.settings,
    searchParams
  ]);
  const showConnectionModelsCard = Boolean(
    controller.settings && (controller.settings.planProvider === "litellm" || startupRequirement)
  );
  const debugSnapshot = useMemo(
    () => buildSettingsDebugSnapshot(controller),
    [
      controller.loadError,
      controller.saveError,
      controller.loading,
      controller.savePhase,
      controller.lastSavedAt,
      controller.settings,
      controller.desktopSecurity,
      controller.numericDrafts,
      controller.probeState
    ]
  );

  usePageDebugSnapshot(debugSnapshot);

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/settings" />

      <SettingsHeader />
      {startupRequirement ? (
        <StartupRequirementCard
          title={startupRequirement.title}
          description={startupRequirement.description}
        />
      ) : null}

      {controller.loading ? <div style={styles.loading}>正在加载设置…</div> : null}
      {controller.loadError ? <div style={styles.error}>设置加载失败：{controller.loadError}</div> : null}
      {!controller.loading && !controller.settings && showDesktopSecurityCard ? (
        <div className="settings-form" style={styles.form}>
          <DesktopSecurityCard controller={controller} />
        </div>
      ) : null}

      {!controller.loading && controller.settings ? (
        <div className="settings-form" style={styles.form}>
          <ProviderCard controller={controller} settings={controller.settings} />
          {showDesktopSecurityCard ? <DesktopSecurityCard controller={controller} /> : null}

          {showConnectionModelsCard ? (
            <ConnectionModelsCard controller={controller} settings={controller.settings} />
          ) : null}
          {controller.settings.planProvider === "litellm" ? (
            <>
              <CapabilityAuditCard controller={controller} settings={controller.settings} />
              <AdvancedSettingsCard controller={controller} settings={controller.settings} />
            </>
          ) : null}

          <DebugVisibilityCard controller={controller} settings={controller.settings} />
          <AutoSaveStatusBar controller={controller} />
        </div>
      ) : null}
    </main>
  );
}
