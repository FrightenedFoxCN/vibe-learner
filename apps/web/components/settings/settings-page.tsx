"use client";

import { TopNav } from "../top-nav";
import { settingsStyles as styles } from "./settings-styles";
import {
  AutoSaveStatusBar,
  CapabilityAuditCard,
  ConnectionModelsCard,
  DebugVisibilityCard,
  ProviderCard,
  SettingsHeader,
  AdvancedSettingsCard
} from "./settings-sections";
import { useSettingsController } from "./use-settings-controller";

export function SettingsPage() {
  const controller = useSettingsController();

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/settings" />

      <SettingsHeader />

      {controller.loading ? <div style={styles.loading}>正在加载设置...</div> : null}
      {controller.loadError ? <div style={styles.error}>设置加载失败：{controller.loadError}</div> : null}

      {!controller.loading && controller.settings ? (
        <div className="settings-form" style={styles.form}>
          <ProviderCard controller={controller} settings={controller.settings} />

          {controller.settings.planProvider === "openai" ? (
            <>
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
