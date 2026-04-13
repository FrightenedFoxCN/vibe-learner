import "react-pdf/dist/Page/TextLayer.css";
import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { DebugOverlay } from "../components/debug-overlay";
import { DesktopStartupGuard } from "../components/desktop-startup-guard";
import { DesktopViewMenuBridge } from "../components/desktop-view-menu-bridge";
import { LearningWorkspaceProvider } from "../components/learning-workspace-provider";
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
          <PageDebugProvider>
            <LearningWorkspaceProvider>
              <DesktopViewMenuBridge />
              {children}
              <DebugOverlay />
            </LearningWorkspaceProvider>
          </PageDebugProvider>
        </RuntimeSettingsProvider>
      </body>
    </html>
  );
}
