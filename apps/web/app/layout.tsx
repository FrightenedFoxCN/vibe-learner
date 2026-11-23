import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { DiagnosticCollector } from "../components/debug/diagnostic-collector";
import { DebugProvider } from "../components/debug/debug-provider";
import { DebugOverlay } from "../components/debug/debug-overlay";
import { DesktopStartupGuard } from "../components/layout/desktop-startup-guard";
import { DesktopViewMenuBridge } from "../components/layout/desktop-view-menu-bridge";
import { LearningPageCacheProvider } from "../components/layout/learning-page-cache-provider";
import { PageDebugProvider } from "../components/debug/page-debug-context";
import { ConfirmProvider } from "../components/ui/confirm-provider";
import { RuntimeSettingsProvider } from "../components/layout/runtime-settings-provider";

export const metadata: Metadata = {
  title: "Vibe Learner",
  description: "本地优先的学习工作台。",
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <ConfirmProvider>
          <RuntimeSettingsProvider>
            <DesktopStartupGuard />
            <DiagnosticCollector />
            <DebugProvider>
              <PageDebugProvider>
                <LearningPageCacheProvider>
                  <DesktopViewMenuBridge />
                  {children}
                </LearningPageCacheProvider>
                <DebugOverlay />
              </PageDebugProvider>
            </DebugProvider>
          </RuntimeSettingsProvider>
        </ConfirmProvider>
      </body>
    </html>
  );
}
