import type { ReactNode } from "react";
import { LearningWorkspaceProvider } from "../../components/learning-workspace-provider";

export default function LearningLayout({ children }: { children: ReactNode }) {
  return <LearningWorkspaceProvider>{children}</LearningWorkspaceProvider>;
}
