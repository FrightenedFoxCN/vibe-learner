import "./globals.css";
import type { Metadata } from "next";
import type { ReactNode } from "react";
import { LearningWorkspaceProvider } from "../components/learning-workspace-provider";

export const metadata: Metadata = {
  title: "Vibe Learner",
  description: "本地优先的大模型辅助学习工作台，包含教材解析、学习计划与教师人格层。"
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="zh-CN">
      <body>
        <LearningWorkspaceProvider>{children}</LearningWorkspaceProvider>
      </body>
    </html>
  );
}
