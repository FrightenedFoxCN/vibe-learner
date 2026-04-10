"use client";

import { createContext, useContext } from "react";
import type { ReactNode } from "react";

import { useLearningWorkspaceController } from "../hooks/use-learning-workspace-controller";
import { mockPersonas } from "../lib/mock-data";

type LearningWorkspaceControllerValue = ReturnType<typeof useLearningWorkspaceController>;

const LearningWorkspaceContext = createContext<LearningWorkspaceControllerValue | null>(null);

export function LearningWorkspaceProvider({ children }: { children: ReactNode }) {
  const controller = useLearningWorkspaceController({
    initialPersonas: mockPersonas
  });

  return (
    <LearningWorkspaceContext.Provider value={controller}>
      {children}
    </LearningWorkspaceContext.Provider>
  );
}

export function useLearningWorkspace() {
  const value = useContext(LearningWorkspaceContext);
  if (!value) {
    throw new Error("useLearningWorkspace must be used within LearningWorkspaceProvider");
  }
  return value;
}
