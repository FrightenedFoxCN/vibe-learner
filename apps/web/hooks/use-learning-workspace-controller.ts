"use client";


import { useState } from "react";
import { useStudyContinuation } from "./use-study-continuation";
import { useStudyCommitActions } from "./use-study-commit-actions";
import { useStudyMessages } from "./use-study-messages";
import { useStudySessionNavigation } from "./use-study-session-navigation";
import { useStudyChatRecovery } from "./use-study-chat-recovery";

import { usePlanMutations } from "./use-plan-mutations";
import { usePlanGeneration } from "./use-plan-generation";
import { useEffect, useMemo, useReducer, useRef } from "react";
import type {
  DocumentRecord,
  DocumentSection,
  LearningPlan,
  PersonaProfile,
  SceneProfile,
  StudyChatResponse,
  StudySessionRecord
} from "@vibe-learner/shared";

import {
  listDocuments,
} from "../lib/data/documents";
import {
  listLearningPlans,
} from "../lib/data/learning-plans";
import { WorkspaceSnapshotLoader } from "../lib/workspace-snapshot-loader";
import { listPersonas } from "../lib/data/personas";
import { listSceneLibrary, type SceneLibraryItemPayload } from "../lib/data/scenes";
import { mockPersonas } from "../lib/mock-data";
import {
  buildPlanHistoryItems,
  findDocumentForPlan,
  findLearningPlan
} from "../lib/plan-panel-data";
import {
  resolveWorkspaceSnapshot,
  type WorkspaceSnapshot,
} from "../lib/learning-workspace-state";
import { readSceneProfileFromLocalStorage } from "../lib/scene-profile";
import {
  PERSONA_LIBRARY_UPDATED_EVENT,
  isPersonaLibraryStorageEvent,
} from "../lib/persona-library-sync";
import {
  createInitialLearningWorkspaceState,
  learningWorkspaceReducer
} from "../lib/learning-workspace-reducer";
import {
  CONNECTED_NOTICE,
  DISCONNECTED_NOTICE,
  SNAPSHOT_REFRESHED_NOTICE
} from "../lib/learning-workspace-copy";
import { resolveStudySessionErrorNotice } from "../lib/study-session-decode";
import {
  logWorkspaceError,
  logWorkspaceInfo
} from "../lib/learning-workspace-telemetry";
import { getDesktopRuntimeConfig } from "../lib/runtime-config";
import { useRuntimeSettings } from "../components/runtime-settings-provider";
import {
  StudyAsyncViewFence,
} from "../lib/async-result-fence";


export type { GeneratePlanInput } from "./use-plan-generation";

interface UseLearningWorkspaceControllerOptions {
  initialSelection?: { planId: string; personaId: string; sceneLibraryId: string };
  initialPlan?: LearningPlan;
  initialPersonas?: PersonaProfile[];
}

export function useLearningWorkspaceController({
  initialPlan,
  initialSelection,
  initialPersonas = mockPersonas
}: UseLearningWorkspaceControllerOptions) {
  const runtimeSettings = useRuntimeSettings();
  const [state, dispatch] = useReducer(
    learningWorkspaceReducer,
    createInitialLearningWorkspaceState({
      initialPlan,
      initialSelection,
      initialPersonas
    })
  );
  const [sceneLibraryItems, setSceneLibraryItems] = useState<SceneLibraryItemPayload[]>([]);
  const [selectedSceneLibraryId, setSelectedSceneLibraryId] = useState(initialSelection?.sceneLibraryId ?? "");
  const mountedRef = useRef(true);
  const selectedPersonaIdRef = useRef(state.selectedPersonaId);
  const selectedPlanIdRef = useRef(state.selectedPlanId);
  const snapshotLoaderRef = useRef<WorkspaceSnapshotLoader | null>(null);
  if (snapshotLoaderRef.current === null) {
    snapshotLoaderRef.current = new WorkspaceSnapshotLoader({ listDocuments, listLearningPlans, listPersonas });
  }
  const snapshotLoader = snapshotLoaderRef.current;
  const studyViewFenceRef = useRef(
    new StudyAsyncViewFence<StudySessionRecord>({
      initialPlanId: initialPlan?.id,
      session: state.studySession,
    }),
  );
  const desktopRuntimeConfig = getDesktopRuntimeConfig();
  const planGenerationBlockedReason = resolvePlanGenerationBlockedReason({
    runtimeSettings: runtimeSettings.settings,
    runtimeSettingsLoading: runtimeSettings.loading,
    desktopRuntimeConfig,
  });

  const selectedPersona =
    state.personas.find((persona) => persona.id === state.selectedPersonaId) ?? state.personas[0];
  const activePlan = findLearningPlan(state.planHistory, state.selectedPlanId);
  const activeDocument = findDocumentForPlan(activePlan, state.documents);
  const activePersonaId = state.studySession?.personaId || activePlan?.personaId || state.selectedPersonaId;
  const activePersona =
    state.personas.find((persona) => persona.id === activePersonaId) ?? selectedPersona;
  const planSections = buildPlanDirectorySections(activePlan, activeDocument);
  const planHistoryItems = buildPlanHistoryItems({
    plans: state.planHistory,
    documents: state.documents,
    personas: state.personas
  });
  const activeSection =
    planSections.find((section) => section.id === state.studySession?.studyUnitId) ??
    planSections[0] ??
    null;
  const selectedSceneProfile = useMemo(
    () => resolveSceneProfileFromLibrary(sceneLibraryItems, selectedSceneLibraryId),
    [sceneLibraryItems, selectedSceneLibraryId]
  );

  const resolveActiveSceneProfile = () => selectedSceneProfile ?? readSceneProfileFromLocalStorage();
  const transitionStudyView = (fieldTarget: string, clearSession = false) => {
    studyViewFenceRef.current.transition(fieldTarget, clearSession);
    resetStudyRecovery();
  };

  const activateStudySessionView = (session: StudySessionRecord) => {
    if (studyViewFenceRef.current.activateSession(session)) {
      resetStudyRecovery();
    }
  };

  useEffect(() => {
    mountedRef.current = true;
    snapshotLoader.activate();
    return () => {
      mountedRef.current = false;
      snapshotLoader.deactivate();
      studyViewFenceRef.current.transition("learning-route:unmounted", true);
    };
  }, []);

  useEffect(() => {
    selectedPersonaIdRef.current = state.selectedPersonaId;
    selectedPlanIdRef.current = state.selectedPlanId;
  }, [state.selectedPersonaId, state.selectedPlanId]);

  useEffect(() => {
    const nextSession = state.studySession;
    const previousSession = studyViewFenceRef.current.session;
    if (
      previousSession?.id !== nextSession?.id ||
      previousSession?.studyUnitId !== nextSession?.studyUnitId
    ) {
      transitionStudyView(
        nextSession
          ? `study-session:${nextSession.id}:unit:${nextSession.studyUnitId}`
          : `study-plan:${selectedPlanIdRef.current || "none"}`,
        nextSession === null,
      );
    }
    studyViewFenceRef.current.session = nextSession;
  }, [state.studySession]);

  const resolveStudyUnitTitle = (studyUnitId: string) => {
    const sectionFromPlan = planSections.find((section) => section.id === studyUnitId);
    if (sectionFromPlan?.title) {
      return sectionFromPlan.title;
    }
    const sectionFromDocument = activeDocument?.sections.find((section) => section.id === studyUnitId);
    if (sectionFromDocument?.title) {
      return sectionFromDocument.title;
    }
    return studyUnitId;
  };

  const resolveThemeHintByStudyUnitId = (studyUnitId: string) => {
    if (!activePlan) {
      return "";
    }
    const studyUnitProgress = activePlan.studyUnitProgress.find((item) => item.unitId === studyUnitId);
    if (studyUnitProgress?.objectiveFragment?.trim()) {
      return studyUnitProgress.objectiveFragment.trim();
    }
    const scheduleItem = activePlan.schedule.find((item) => item.unitId === studyUnitId);
    if (scheduleItem?.focus) {
      return scheduleItem.focus;
    }
    const containingUnit = activePlan.studyUnits.find((unit) =>
      unit.id === studyUnitId ||
      unit.sourceSectionIds.includes(studyUnitId) ||
      (
        activeDocument?.sections.some((section) =>
          section.id === studyUnitId &&
          Math.max(unit.pageStart, section.pageStart) <= Math.min(unit.pageEnd, section.pageEnd)
        ) ?? false
      )
    );
    if (containingUnit) {
      const containingSchedule = activePlan.schedule.find((item) => item.unitId === containingUnit.id);
      if (containingSchedule?.focus) {
        return containingSchedule.focus;
      }
      const containingChapter = containingSchedule?.scheduleChapters.find((chapter) => chapter.title.trim());
      if (containingChapter?.title) {
        return containingChapter.title;
      }
    }
    return activePlan.schedule[0]?.scheduleChapters[0]?.title ?? activePlan.objective;
  };

  const refreshSceneLibrary = async () => {
    try {
      const items = await listSceneLibrary();
      setSceneLibraryItems(items);
      setSelectedSceneLibraryId((current) => {
        if (current && items.some((item) => item.sceneId === current)) {
          return current;
        }
        return items[0]?.sceneId ?? "";
      });
    } catch {
      setSceneLibraryItems([]);
      setSelectedSceneLibraryId("");
    }
  };

  const refreshPersonaLibrary = async () => {
    try {
      const personas = await listPersonas();
      dispatch({
        type: "personas_refreshed",
        personas,
      });
    } catch (error) {
      logWorkspaceError("workflow:persona_library:refresh_error", error);
    }
  };

  const applyWorkspaceSnapshot = (
    snapshot: WorkspaceSnapshot,
    preferredPlanId: string
  ) => {
    const nextState = resolveWorkspaceSnapshot({
      snapshot,
      preferredPlanId,
      currentSelectedPlanId: selectedPlanIdRef.current,
      currentSelectedPersonaId: selectedPersonaIdRef.current
    });

    if (nextState.shouldResetStudySession) {
      selectedPlanIdRef.current = nextState.selectedPlanId;
      transitionStudyView(
        `study-plan:${nextState.selectedPlanId || "none"}`,
        true,
      );
    }

    dispatch({
      type: "snapshot_applied",
      personas: snapshot.personas,
      resolution: nextState
    });
  };

  const syncWorkspaceSnapshot = (options: {
    includePersonas: boolean;
    preferredPlanId: string;
    successNotice?: string;
    initial?: boolean;
  }) => snapshotLoader.load(options.includePersonas, {
    started: () => dispatch({ type: "snapshot_refresh_started" }),
    loaded: (snapshot) => {
      applyWorkspaceSnapshot(snapshot, selectedPlanIdRef.current || options.preferredPlanId);
      if (options.successNotice) dispatch({ type: "notice_set", notice: options.successNotice });
    },
    failed: (error) => {
      dispatch({
        type: "notice_set",
        notice: options.initial
          ? resolveStudySessionErrorNotice(error, DISCONNECTED_NOTICE, "history")
          : DISCONNECTED_NOTICE,
      });
      if (options.initial) logWorkspaceError("workflow:workspace_snapshot:load_error", error);
    },
    finished: () => dispatch({ type: "snapshot_refresh_finished" }),
  });

  const selectPlan = (planId: string, noticeMessage?: string) => {
    const nextPlan = findLearningPlan(state.planHistory, planId);
    if (!nextPlan || nextPlan.id === state.selectedPlanId) {
      return;
    }
    selectedPlanIdRef.current = nextPlan.id;
    transitionStudyView(`study-plan:${nextPlan.id}`, true);
    dispatch({
      type: "plan_selected",
      planId: nextPlan.id,
      notice: noticeMessage
    });
  };

  const {
    generatePlanWorkflow, cancelPlanGeneration, isGeneratingPlan, isInterruptingPlan,
    processStreamEvents, planStreamEvents, processStreamStatus, planStreamStatus,
    processStreamDocumentId, planStreamDocumentId,
  } = usePlanGeneration({
    personaId: selectedPersona?.id ?? "",
    blockedReason: planGenerationBlockedReason,
    resolveSceneProfile: resolveActiveSceneProfile,
    onStarted: () => {
      selectedPlanIdRef.current = "";
      transitionStudyView("study-plan:generating", true);
      dispatch({ type: "generation_started" });
      dispatch({ type: "busy_started" });
    },
    onFinished: () => dispatch({ type: "busy_finished" }),
    onNotice: (notice) => dispatch({ type: "notice_set", notice }),
    onDocument: (document) => dispatch({ type: "generated_document_applied", document }),
    onPlan: (plan) => {
      selectedPlanIdRef.current = plan.id;
      transitionStudyView(`study-plan:${plan.id}`, true);
      dispatch({ type: "generated_plan_applied", plan });
      const revision = studyViewFenceRef.current.viewRevision;
      return () => mountedRef.current && selectedPlanIdRef.current === plan.id && studyViewFenceRef.current.viewRevision === revision;
    },
    onSession: (studySession) => {
      activateStudySessionView(studySession);
      dispatch({ type: "study_session_set", studySession, clearResponse: true });
    },
  });

  const { renamePlanTitle, removePlan, renameStudyUnitTitle, updatePlanProgress, answerPlanQuestion, isMutating } = usePlanMutations({
    onPlan: (plan) => dispatch({ type: "plan_updated", plan }),
    onDocumentAndPlans: (payload) => dispatch({ type: "document_and_plans_updated", ...payload }),
    onNotice: (notice) => dispatch({ type: "notice_set", notice }),
    onDeleted: (planId) => {
      const selected = selectedPlanIdRef.current;
      const preferredPlanId = selected === planId
        ? state.planHistory.find((plan) => plan.id !== planId)?.id ?? ""
        : selected;
      if (selected === planId) {
        selectedPlanIdRef.current = preferredPlanId;
        transitionStudyView(`study-plan:${preferredPlanId || "none"}`, true);
      }
      dispatch({ type: "plan_deleted", planId, preferredPlanId });
    },
  });

  const applyChatExchange = (next: StudyChatResponse & { session: StudySessionRecord }) => {
    activateStudySessionView(next.session);
    dispatch({
      type: "study_session_set",
      studySession: next.session,
      clearResponse: false
    });
    dispatch({
      type: "response_set",
      response: next
    });
  };

  const {
    chatFailure, setChatFailure, resetStudyRecovery, beginStudyResponseTicket,
    isCurrentStudyResponseTicket, applyStudyChatOperation, queryStudyChatOperation,
    refreshStudySessionAfterRejectedAdmission, isQuerying,
  } = useStudyChatRecovery({
    session: state.studySession,
    view: studyViewFenceRef.current,
    getSelectedPlanId: () => selectedPlanIdRef.current,
    onExchange: applyChatExchange,
    onSession: (studySession, clearResponse) => {
      if (studySession) activateStudySessionView(studySession);
      dispatch({ type: "study_session_set", studySession, clearResponse });
    },
    onResetView: () => transitionStudyView(`study-plan:${selectedPlanIdRef.current || "none"}`, true),
    onNotice: (notice) => dispatch({ type: "notice_set", notice }),
  });

  const { createSessionForActivePlan, ensureSessionForSection, handleSwitchSection, isNavigating } = useStudySessionNavigation({
    plan: activePlan, document: activeDocument, view: studyViewFenceRef.current,
    getSelectedPlanId: () => selectedPlanIdRef.current,
    resolveSceneProfile: resolveActiveSceneProfile,
    resolveStudyUnitTitle, resolveThemeHint: resolveThemeHintByStudyUnitId,
    onTransition: transitionStudyView,
    onSession: (studySession, clearResponse) => {
      if (studySession) activateStudySessionView(studySession);
      dispatch({ type: "study_session_set", studySession, clearResponse });
    },
    onNotice: (notice) => dispatch({ type: "notice_set", notice }),
  });

  const { handleAsk, handleAskForSection, retryFailedAsk, sendHiddenSessionMessage,
    automaticStudyRequest, forgetAutomaticStudyRequest, isSending } = useStudyMessages({
    view: studyViewFenceRef.current,
    recovery: { chatFailure, setChatFailure, beginStudyResponseTicket, isCurrentStudyResponseTicket, applyStudyChatOperation },
    ensureSessionForSection,
    isDialogueInterruptedForSession: (id) => continuation.isDialogueInterruptedForSession(id),
    peekDeferredInteractiveCallbackPrefix: (id) => continuation.peekDeferredInteractiveCallbackPrefix(id),
    clearInterruptedDialogueState: (id, prefix) => continuation.clearInterruptedDialogueState(id, prefix),
    onNotice: (notice) => dispatch({ type: "notice_set", notice }),
  });

  const { handleSubmitQuestionAttempt, handleResolvePlanConfirmation, isApplying } = useStudyCommitActions({
    view: studyViewFenceRef.current, automaticStudyRequest, forgetAutomaticStudyRequest,
    onSession: (studySession) => {
      activateStudySessionView(studySession);
      dispatch({ type: "study_session_set", studySession, clearResponse: false });
    },
    onPlan: (plan) => dispatch({ type: "plan_updated", plan }),
    onCommittedQuestion: (session, input) => continuation.triggerInteractiveQuestionCallback(session, input),
    onNotice: (notice) => dispatch({ type: "notice_set", notice }),
  });

  const continuation = useStudyContinuation({
    session: state.studySession, view: studyViewFenceRef.current,
    busy: state.isBusy || isMutating || isQuerying || isNavigating || isSending || isApplying,
    ensureSessionForSection, sendHiddenSessionMessage, automaticStudyRequest,
    onSession: (studySession) => {
      activateStudySessionView(studySession);
      dispatch({ type: "study_session_set", studySession, clearResponse: false });
    },
    onNotice: (notice) => dispatch({ type: "notice_set", notice }),
  });
  const { triggerSessionPrelude, interruptDialogue, isDialogueInterrupted, isContinuing } = continuation;

  useEffect(() => {
    void syncWorkspaceSnapshot({
      includePersonas: true,
      preferredPlanId: selectedPlanIdRef.current,
      successNotice: CONNECTED_NOTICE,
      initial: true,
    });
  }, []);

  useEffect(() => {
    void refreshSceneLibrary();
  }, []);

  useEffect(() => {
    if (!activePlan?.sceneProfile || selectedSceneLibraryId) {
      return;
    }
    const matched = sceneLibraryItems.find(
      (item) => item.sceneName === activePlan.sceneProfile?.sceneName
    );
    if (matched) {
      setSelectedSceneLibraryId(matched.sceneId);
    }
  }, [activePlan?.id, activePlan?.sceneProfile, sceneLibraryItems, selectedSceneLibraryId]);

  useEffect(() => {
    const handleFocus = () => {
      void syncWorkspaceSnapshot({
        includePersonas: false,
        preferredPlanId: selectedPlanIdRef.current,
      });
      void refreshPersonaLibrary();
      void refreshSceneLibrary();
    };
    window.addEventListener("focus", handleFocus);
    return () => {
      window.removeEventListener("focus", handleFocus);
    };
  }, []);

  useEffect(() => {
    const handlePersonasUpdated = () => {
      void refreshPersonaLibrary();
    };
    const handleStorage = (event: StorageEvent) => {
      if (isPersonaLibraryStorageEvent(event)) {
        void refreshPersonaLibrary();
      }
    };

    window.addEventListener(PERSONA_LIBRARY_UPDATED_EVENT, handlePersonasUpdated);
    window.addEventListener("storage", handleStorage);
    return () => {
      window.removeEventListener(PERSONA_LIBRARY_UPDATED_EVENT, handlePersonasUpdated);
      window.removeEventListener("storage", handleStorage);
    };
  }, []);


  return {
    personas: state.personas,
    selectedPersona,
    activePersona,
    selectedPersonaId: state.selectedPersonaId,
    setSelectedPersonaId: (personaId: string) =>
      dispatch({ type: "persona_selected", personaId }),
    selectedPlanId: state.selectedPlanId,
    activePlan,
    activeDocument,
    planSections,
    activeSection,
    planHistory: state.planHistory,
    planHistoryItems,
    studySession: state.studySession,
    response: state.response,
    notice: state.notice,
    isBusy: state.isBusy || isMutating || isQuerying || isNavigating || isSending || isApplying || isContinuing,
    chatImageUploadEnabled: Boolean(runtimeSettings.settings?.openaiChatModelMultimodal),
    isGeneratingPlan,
    isInterruptingPlan,
    isDialogueInterrupted,
    planGenerationBlockedReason,
    processStreamDocumentId,
    planStreamDocumentId,
    processStreamEvents,
    planStreamEvents,
    processStreamStatus,
    planStreamStatus,
    isSnapshotRefreshing: state.isSnapshotRefreshing,
    sceneLibraryItems,
    selectedSceneLibraryId,
    setSelectedSceneLibraryId,
    selectedSceneProfile,
    generatePlanWorkflow,
    cancelPlanGeneration,
    selectPlan,
    createSessionForActivePlan,
    renamePlanTitle,
    updatePlanProgress,
    answerPlanQuestion,
    renameStudyUnitTitle,
    removePlan,
    handleSwitchSection,
    triggerSessionPrelude,
    handleAsk,
    handleAskForSection,
    chatFailure,
    queryStudyChatOperation,
    retryFailedAsk,
    refreshStudySessionAfterRejectedAdmission,
    handleSubmitQuestionAttempt,
    handleResolvePlanConfirmation,
    interruptDialogue,
    refreshPlanSnapshot: () =>
      syncWorkspaceSnapshot({
        includePersonas: false,
        preferredPlanId: state.selectedPlanId,
        successNotice: SNAPSHOT_REFRESHED_NOTICE
      })
  };
}

function resolvePlanGenerationBlockedReason(input: {
  runtimeSettings: ReturnType<typeof useRuntimeSettings>["settings"];
  runtimeSettingsLoading: boolean;
  desktopRuntimeConfig: ReturnType<typeof getDesktopRuntimeConfig>;
}) {
  if (input.runtimeSettingsLoading) {
    return "";
  }
  const settings = input.runtimeSettings;
  if (!settings || settings.planProvider !== "litellm") {
    return "";
  }
  if (settings.openaiPlanApiKeyConfigured || settings.openaiApiKeyConfigured) {
    return "";
  }
  if (input.desktopRuntimeConfig?.isDesktop) {
    return input.desktopRuntimeConfig.vaultState !== "unlocked"
      ? "当前计划提供器设为 LiteLLM，但桌面 Vault 尚未解锁；继续会静默回退到 mock。先去统一设置解锁 Vault。"
      : "当前计划提供器设为 LiteLLM，但还没有可用的计划模型密钥。先去统一设置补齐连接信息。";
  }
  return "当前计划提供器设为 LiteLLM，但还没有可用的计划模型密钥。先去统一设置补齐连接信息。";
}

function resolveSceneProfileFromLibrary(
  items: SceneLibraryItemPayload[],
  selectedSceneLibraryId: string
): SceneProfile | undefined {
  if (!selectedSceneLibraryId) {
    return undefined;
  }
  const selectedItem = items.find((item) => item.sceneId === selectedSceneLibraryId);
  if (!selectedItem) {
    return undefined;
  }
  if (selectedItem.sceneProfile) {
    return selectedItem.sceneProfile;
  }
  return {
    sceneName: selectedItem.sceneName,
    sceneId: selectedItem.selectedLayerId || selectedItem.sceneId,
    title: selectedItem.sceneName || "未命名场景",
    summary: selectedItem.sceneSummary || "",
    tags: [],
    selectedPath: [],
    focusObjectNames: [],
    sceneTree: [],
  };
}

function buildPlanDirectorySections(
  plan: LearningPlan | null,
  document: DocumentRecord | null
): DocumentSection[] {
  if (!plan) {
    return [];
  }

  const studyUnitById = new Map(
    (document?.studyUnits ?? plan.studyUnits).map((unit) => [unit.id, unit])
  );
  const sections: DocumentSection[] = [];

  for (const item of plan.schedule) {
    const unit = studyUnitById.get(item.unitId);
    if (!unit) {
      continue;
    }
    sections.push({
      id: unit.id,
      documentId: unit.documentId,
      title: item.title || unit.title,
      pageStart: unit.pageStart,
      pageEnd: unit.pageEnd,
      level: 1
    });
  }

  if (!sections.length) {
    const baseSections = document?.sections.length
      ? document.sections
      : plan.studyUnits
          .filter((unit) => unit.includeInPlan)
          .map((unit) => ({
            id: unit.id,
            documentId: unit.documentId,
            title: unit.title,
            pageStart: unit.pageStart,
            pageEnd: unit.pageEnd,
            level: 1 as const,
          }));
    return baseSections;
  }

  return sections.filter(
    (section, index) => sections.findIndex((candidate) => candidate.id === section.id) === index
  );
}
