"use client";

import { createOwnedDebugSnapshot } from "./owned-debug-snapshot";
import type { useLearningWorkspaceController } from "../hooks/use-learning-workspace-controller";

// Debug consumes only a published projection; it never initializes learning data.
export type LearningDebugSnapshot = Pick<ReturnType<typeof useLearningWorkspaceController>,
  | "activeDocument" | "selectedPersona" | "studySession" | "response"
  | "processStreamDocumentId" | "processStreamEvents" | "processStreamStatus"
  | "planStreamDocumentId" | "planStreamEvents" | "planStreamStatus"
>;

const learning = createOwnedDebugSnapshot<LearningDebugSnapshot>();
export const DebugProvider = learning.Provider;
export const useLearningDebugSnapshot = learning.useSnapshot;
export const useLearningDebugRegistration = learning.useRegistration;
export const usePublishLearningDebugSnapshot = learning.usePublish;
