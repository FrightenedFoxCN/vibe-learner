import "react-pdf/dist/Page/TextLayer.css";
import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { DiagnosticCollector } from "../components/diagnostic-collector";
import { DebugProvider } from "../components/debug-provider";
import { DebugOverlay } from "../components/debug-overlay";
import { DesktopStartupGuard } from "../components/desktop-startup-guard";
import { DesktopViewMenuBridge } from "../components/desktop-view-menu-bridge";
import { LearningPageCacheProvider } from "../components/learning-page-cache-provider";
import { PageDebugProvider } from "../components/page-debug-context";
import { RuntimeSettingsProvider } from "../components/runtime-settings-provider";

export const metadata: Metadata = {
  title: "Vibe Learner",
  description: "本地优先的学习工作台。"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
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
      </body>
    </html>
  );
}
