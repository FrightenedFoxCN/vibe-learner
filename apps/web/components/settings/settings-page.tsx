"use client";

import { useMemo } from "react";
import { useSearchParams } from "next/navigation";

import { TopNav } from "../layout/top-nav";
import {
  DESKTOP_STARTUP_QUERY_KEY,
  DESKTOP_STARTUP_QUERY_VALUE,
  resolveDesktopStartupRequirement,
} from "../../lib/desktop-startup";
import { Alert } from "../ui/alert";
import { AdvancedSettingsCard } from "./settings-advanced";
import { CapabilityAuditCard } from "./settings-capability-audit";
import {
  DesktopSecurityCard,
  StartupRequirementCard,
} from "./settings-desktop-security";
import { AutoSaveStatusBar, DebugVisibilityCard } from "./settings-feedback";
import { ConnectionModelsCard, ProviderCard } from "./settings-model-connection";
import { usePageDebugSnapshot } from "../debug/page-debug-context";
import { useSettingsController } from "./use-settings-controller";
import { buildSettingsDebugSnapshot } from "./settings-debug-snapshot";

export function SettingsPage() {
  const controller = useSettingsController();
  const searchParams = useSearchParams();
  const showDesktopSecurityCard =
    controller.desktopSecurity.enabled ||
    Boolean(controller.desktopSecurity.startupError);
  const startupRequirement = useMemo(() => {
    if (searchParams.get(DESKTOP_STARTUP_QUERY_KEY) !== DESKTOP_STARTUP_QUERY_VALUE) {
      return null;
    }
    return resolveDesktopStartupRequirement({
      isDesktop: controller.desktopSecurity.enabled,
      startupError: controller.desktopSecurity.startupError,
      vaultState: controller.desktopSecurity.vaultState,
      settings: controller.settings,
    });
  }, [
    controller.desktopSecurity.enabled,
    controller.desktopSecurity.startupError,
    controller.desktopSecurity.vaultState,
    controller.settings,
    searchParams,
  ]);
  const showConnectionModelsCard = Boolean(
    controller.settings &&
    (controller.settings.planProvider === "litellm" || startupRequirement),
  );
  const {
    loadError,
    saveError,
    loading,
    savePhase,
    lastSavedAt,
    settings,
    desktopSecurity,
    numericDrafts,
    probeState,
  } = controller;
  const debugSnapshot = useMemo(
    () =>
      buildSettingsDebugSnapshot({
        loadError,
        saveError,
        loading,
        savePhase,
        lastSavedAt,
        settings,
        desktopSecurity,
        numericDrafts,
        probeState,
      }),
    [
      loadError,
      saveError,
      loading,
      savePhase,
      lastSavedAt,
      settings,
      desktopSecurity,
      numericDrafts,
      probeState,
    ],
  );

  usePageDebugSnapshot(debugSnapshot);

  return (
    <main className="with-app-nav mx-auto grid min-h-screen min-w-0 max-w-[1160px] content-start gap-5 px-4 pt-[38px] pb-16 md:px-8">
      <TopNav currentPath="/settings" />

      <h1 className="m-0 text-[28px] leading-tight font-extrabold tracking-tight text-ink">
        统一设置
      </h1>
      {startupRequirement ? (
        <StartupRequirementCard
          title={startupRequirement.title}
          description={startupRequirement.description}
        />
      ) : null}

      {controller.loading ? (
        <div role="status" className="text-sm text-muted">
          正在加载设置…
        </div>
      ) : null}
      {controller.loadError ? (
        <Alert variant="negative">设置加载失败：{controller.loadError}</Alert>
      ) : null}
      {!controller.loading && !controller.settings && showDesktopSecurityCard ? (
        <div className="grid min-w-0 gap-4">
          <DesktopSecurityCard controller={controller} />
        </div>
      ) : null}

      {!controller.loading && controller.settings ? (
        <div className="grid min-w-0 gap-4">
          <ProviderCard controller={controller} settings={controller.settings} />
          {showDesktopSecurityCard ? (
            <DesktopSecurityCard controller={controller} />
          ) : null}

          {showConnectionModelsCard ? (
            <ConnectionModelsCard
              controller={controller}
              settings={controller.settings}
            />
          ) : null}
          {controller.settings.planProvider === "litellm" ? (
            <>
              <CapabilityAuditCard
                controller={controller}
                settings={controller.settings}
              />
              <AdvancedSettingsCard
                controller={controller}
                settings={controller.settings}
              />
            </>
          ) : null}

          <DebugVisibilityCard controller={controller} settings={controller.settings} />
          <AutoSaveStatusBar controller={controller} />
        </div>
      ) : null}
    </main>
  );
}
