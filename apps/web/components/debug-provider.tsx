"use client";

import { createContext, useContext, useEffect, useState } from "react";
import type { Dispatch, ReactNode, SetStateAction } from "react";
import type { useLearningWorkspaceController } from "../hooks/use-learning-workspace-controller";

// Debug consumes only a published projection; it never initializes learning data.
export type LearningDebugSnapshot = Pick<ReturnType<typeof useLearningWorkspaceController>,
  | "activeDocument" | "selectedPersona" | "studySession" | "response"
  | "processStreamDocumentId" | "processStreamEvents" | "processStreamStatus"
  | "planStreamDocumentId" | "planStreamEvents" | "planStreamStatus"
>;

const SnapshotContext = createContext<LearningDebugSnapshot | null>(null);
const PublishContext = createContext<Dispatch<SetStateAction<LearningDebugSnapshot | null>> | null>(null);

export function DebugProvider({ children }: { children: ReactNode }) {
  const [snapshot, setSnapshot] = useState<LearningDebugSnapshot | null>(null);
  return (
    <PublishContext.Provider value={setSnapshot}>
      <SnapshotContext.Provider value={snapshot}>{children}</SnapshotContext.Provider>
    </PublishContext.Provider>
  );
}

export function useLearningDebugSnapshot() {
  return useContext(SnapshotContext);
}

export function usePublishLearningDebugSnapshot(snapshot: LearningDebugSnapshot) {
  const publish = useContext(PublishContext);
  useEffect(() => {
    if (!publish) return;
    publish(snapshot);
    return () => publish(null);
  }, [publish, snapshot]);
}
