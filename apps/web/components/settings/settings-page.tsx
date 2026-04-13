"use client";

import { useMemo } from "react";

import { TopNav } from "../top-nav";
import { settingsStyles as styles } from "./settings-styles";
import {
  AutoSaveStatusBar,
  CapabilityAuditCard,
  ConnectionModelsCard,
  DesktopSecurityCard,
  DebugVisibilityCard,
  ProviderCard,
  SettingsHeader,
  AdvancedSettingsCard
} from "./settings-sections";
import { usePageDebugSnapshot } from "../page-debug-context";
import { useSettingsController } from "./use-settings-controller";

export function SettingsPage() {
  const controller = useSettingsController();
  const debugSnapshot = useMemo(
    () => ({
      title: "设置页调试面板",
      subtitle: "查看设置、保存状态和探测结果。",
      error: [controller.loadError, controller.saveError].filter(Boolean).join("；"),
      summary: [
        { label: "加载状态", value: controller.loading ? "加载中" : "就绪" },
        { label: "保存阶段", value: mapSavePhase(controller.savePhase) },
        { label: "上次保存", value: controller.lastSavedAt || "-" },
        { label: "调试显示", value: controller.settings?.showDebugInfo ? "开启" : "关闭" },
        { label: "提供器", value: controller.settings?.planProvider ?? "-" },
        { label: "桌面 Vault", value: controller.desktopSecurity.enabled ? controller.desktopSecurity.vaultState : "browser" }
      ],
      details: [
        { title: "运行时设置", value: controller.settings },
        { title: "数值输入草稿", value: controller.numericDrafts },
        { title: "能力探测状态", value: controller.probeState },
        { title: "桌面安全状态", value: controller.desktopSecurity }
      ]
    }),
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

      {controller.loading ? <div style={styles.loading}>正在加载设置…</div> : null}
      {controller.loadError ? <div style={styles.error}>设置加载失败：{controller.loadError}</div> : null}

      {!controller.loading && controller.settings ? (
        <div className="settings-form" style={styles.form}>
          <ProviderCard controller={controller} settings={controller.settings} />

          {controller.settings.planProvider === "litellm" ? (
            <>
              <DesktopSecurityCard controller={controller} />
              <ConnectionModelsCard controller={controller} settings={controller.settings} />
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

function mapSavePhase(phase: "idle" | "pending" | "saving" | "saved" | "error") {
  if (phase === "idle") {
    return "空闲";
  }
  if (phase === "pending") {
    return "待保存";
  }
  if (phase === "saving") {
    return "保存中";
  }
  if (phase === "saved") {
    return "已保存";
  }
  return "失败";
}
