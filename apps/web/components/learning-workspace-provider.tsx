"use client";

import { createContext, useContext, useEffect, useMemo } from "react";
import type { ReactNode } from "react";

import { useLearningWorkspaceController } from "../hooks/use-learning-workspace-controller";
import { useLearningPageCache } from "./learning-page-cache-provider";
import type { LearningWorkspacePageCache } from "../lib/learning-workspace-page-cache";
import { usePublishLearningDebugSnapshot } from "./debug-provider";
import { mockPersonas } from "../lib/mock-data";

type LearningWorkspaceControllerValue = ReturnType<typeof useLearningWorkspaceController> & {
  getPageCache: <K extends keyof LearningWorkspacePageCache>(
    key: K
  ) => LearningWorkspacePageCache[K] | undefined;
  setPageCache: <K extends keyof LearningWorkspacePageCache>(
    key: K,
    value: LearningWorkspacePageCache[K]
  ) => void;
};

const LearningWorkspaceContext = createContext<LearningWorkspaceControllerValue | null>(null);

export function LearningWorkspaceProvider({ children }: { children: ReactNode }) {
  const { getPageCache, setPageCache } = useLearningPageCache();
  const controller = useLearningWorkspaceController({
    initialSelection: getPageCache("selection"),
    initialPersonas: mockPersonas
  });
  const debugSnapshot = useMemo(() => ({
    activeDocument: controller.activeDocument,
    selectedPersona: controller.selectedPersona,
    studySession: controller.studySession,
    response: controller.response,
    processStreamDocumentId: controller.processStreamDocumentId,
    processStreamEvents: controller.processStreamEvents,
    processStreamStatus: controller.processStreamStatus,
    planStreamDocumentId: controller.planStreamDocumentId,
    planStreamEvents: controller.planStreamEvents,
    planStreamStatus: controller.planStreamStatus,
  }), [
    controller.activeDocument,
    controller.selectedPersona,
    controller.studySession,
    controller.response,
    controller.processStreamDocumentId,
    controller.processStreamEvents,
    controller.processStreamStatus,
    controller.planStreamDocumentId,
    controller.planStreamEvents,
    controller.planStreamStatus,
  ]);
  usePublishLearningDebugSnapshot(debugSnapshot);
  useEffect(() => {
    setPageCache("selection", {
      planId: controller.selectedPlanId,
      personaId: controller.selectedPersonaId,
      sceneLibraryId: controller.selectedSceneLibraryId,
    });
  }, [controller.selectedPlanId, controller.selectedPersonaId, controller.selectedSceneLibraryId, setPageCache]);
  const value: LearningWorkspaceControllerValue = {
    ...controller,
    getPageCache,
    setPageCache,
  };

  return (
    <LearningWorkspaceContext.Provider value={value}>
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
