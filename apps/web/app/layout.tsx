import "react-pdf/dist/Page/TextLayer.css";
import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { DebugOverlay } from "../components/debug-overlay";
import { LearningWorkspaceProvider } from "../components/learning-workspace-provider";
import { PageDebugProvider } from "../components/page-debug-context";
import { RuntimeSettingsProvider } from "../components/runtime-settings-provider";

export const metadata: Metadata = {
  title: "Vibe Learner",
  description: "本地优先的大模型辅助学习工作台，包含教材解析、学习计划与教师人格层。"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <RuntimeSettingsProvider>
          <PageDebugProvider>
            <LearningWorkspaceProvider>
              {children}
              <DebugOverlay />
            </LearningWorkspaceProvider>
          </PageDebugProvider>
        </RuntimeSettingsProvider>
      </body>
    </html>
  );
}
