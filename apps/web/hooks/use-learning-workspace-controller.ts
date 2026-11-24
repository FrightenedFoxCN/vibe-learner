"use client";

import { useWorkspaceLibraries } from "./use-workspace-libraries";
import {
  resolvePlanGenerationBlockedReason,
  resolveSceneProfileFromLibrary,
  buildPlanDirectorySections,
  resolveStudyUnitTitle,
  resolveThemeHintByStudyUnitId,
} from "../lib/learning-workspace-model";
import { useStudyContinuation } from "./use-study-continuation";
import { useStudyCommitActions } from "./use-study-commit-actions";
import { useStudyMessages } from "./use-study-messages";
import { useStudySessionNavigation } from "./use-study-session-navigation";
import { useStudyChatRecovery } from "./use-study-chat-recovery";

import { usePlanMutations } from "./use-plan-mutations";
import { usePlanGeneration } from "./use-plan-generation";
import { useEffect, useEffectEvent, useMemo, useReducer, useRef } from "react";
import type {
  LearningPlan,
  PersonaProfile,
  StudyChatResponse,
  StudySessionRecord,
} from "@vibe-learner/shared";

import { listDocuments } from "../lib/data/documents";
import { listLearningPlans } from "../lib/data/learning-plans";
import { WorkspaceSnapshotLoader } from "../lib/workspace-snapshot-loader";
import { listPersonas } from "../lib/data/personas";
import { mockPersonas } from "../lib/mock-data";
import {
  buildPlanHistoryItems,
  findDocumentForPlan,
  findLearningPlan,
} from "../lib/plan-panel-data";
import {
  resolvePlanSelection,
  resolveSnapshotPersonaId,
  type PlanSelectionIntent,
  type WorkspaceSnapshot,
} from "../lib/learning-workspace-state";
import {
  createInitialLearningWorkspaceState,
  learningWorkspaceReducer,
} from "../lib/learning-workspace-reducer";
import {
  CONNECTED_NOTICE,
  DISCONNECTED_NOTICE,
  SNAPSHOT_REFRESHED_NOTICE,
} from "../lib/learning-workspace-copy";
import { resolveStudySessionErrorNotice } from "../lib/study-session-decode";
import { logWorkspaceError } from "../lib/learning-workspace-telemetry";
import { getDesktopRuntimeConfig } from "../lib/runtime-config";
import { useRuntimeSettings } from "../components/layout/runtime-settings-provider";
import { StudyAsyncViewFence } from "../lib/async-result-fence";

export type { GeneratePlanInput } from "./use-plan-generation";

interface UseLearningWorkspaceControllerOptions {
  initialSelection?: { planId: string; personaId: string; sceneLibraryId: string };
  initialPlan?: LearningPlan;
  initialPersonas?: PersonaProfile[];
}

export function useLearningWorkspaceController({
  initialPlan,
  initialSelection,
  initialPersonas = mockPersonas,
}: UseLearningWorkspaceControllerOptions) {
  const runtimeSettings = useRuntimeSettings();
  const [state, dispatch] = useReducer(
    learningWorkspaceReducer,
    createInitialLearningWorkspaceState({
      initialPlan,
      initialSelection,
      initialPersonas,
    }),
  );
  const mountedRef = useRef(true);
  const selectedPersonaIdRef = useRef(state.selectedPersonaId);
  const planSelectionRef = useRef({
    selectedPlanId: state.selectedPlanId,
    planHistory: state.planHistory,
  });
  const getSelectedPlanId = () => planSelectionRef.current.selectedPlanId;
  const snapshotLoaderRef = useRef<WorkspaceSnapshotLoader | null>(null);
  if (snapshotLoaderRef.current === null) {
    snapshotLoaderRef.current = new WorkspaceSnapshotLoader({
      listDocuments,
      listLearningPlans,
      listPersonas,
    });
  }
  const snapshotLoader = snapshotLoaderRef.current;
  const studyViewFenceRef = useRef(
    new StudyAsyncViewFence<StudySessionRecord>({
      initialPlanId: state.selectedPlanId,
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
    state.personas.find((persona) => persona.id === state.selectedPersonaId) ??
    state.personas[0];
  const activePlan = findLearningPlan(state.planHistory, state.selectedPlanId);
  const activeDocument = findDocumentForPlan(activePlan, state.documents);
  const activePersonaId =
    state.studySession?.personaId || activePlan?.personaId || state.selectedPersonaId;
  const activePersona =
    state.personas.find((persona) => persona.id === activePersonaId) ?? selectedPersona;
  const planSections = buildPlanDirectorySections(activePlan, activeDocument);
  const planHistoryItems = buildPlanHistoryItems({
    plans: state.planHistory,
    documents: state.documents,
    personas: state.personas,
  });
  const activeSection =
    planSections.find((section) => section.id === state.studySession?.studyUnitId) ??
    planSections[0] ??
    null;
  const {
    sceneLibraryItems,
    selectedSceneLibraryId,
    setSelectedSceneLibraryId,
    refreshPersonaLibrary,
    refreshSceneLibrary,
  } = useWorkspaceLibraries({
    initialSceneId: initialSelection?.sceneLibraryId,
    planScene: activePlan?.sceneProfile,
    onPersonas: (personas) => {
      snapshotLoader.acceptPersonas();
      dispatch({ type: "personas_refreshed", personas });
    },
  });
  const selectedSceneProfile = useMemo(
    () => resolveSceneProfileFromLibrary(sceneLibraryItems, selectedSceneLibraryId),
    [sceneLibraryItems, selectedSceneLibraryId],
  );

  const resolveActiveSceneProfile = () => selectedSceneProfile;
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
    const studyViewFence = studyViewFenceRef.current;
    mountedRef.current = true;
    snapshotLoader.activate();
    return () => {
      mountedRef.current = false;
      snapshotLoader.deactivate();
      studyViewFence.transition("learning-route:unmounted", true);
    };
  }, [snapshotLoader]);

  useEffect(() => {
    selectedPersonaIdRef.current = state.selectedPersonaId;
  }, [state.selectedPersonaId]);

  const publishStudySession = (
    studySession: StudySessionRecord | null,
    clearResponse = false,
  ) => {
    if (studySession) activateStudySessionView(studySession);
    else if (studyViewFenceRef.current.session)
      transitionStudyView(`study-plan:${getSelectedPlanId() || "none"}`, true);
    dispatch({ type: "study_session_set", studySession, clearResponse });
  };

  const publishPlanSelection = (
    intent: PlanSelectionIntent,
    updates: Omit<
      Extract<Parameters<typeof dispatch>[0], { type: "plan_transition" }>,
      "type" | "transition"
    > = {},
  ) => {
    // Async results can continue before React renders the queued action. Apply
    // the exact transition to the current plan selection and fence first.
    const transition = resolvePlanSelection(planSelectionRef.current, intent);
    if (!transition) return;
    if (
      intent.type === "generated" ||
      intent.type === "update" ||
      intent.type === "delete"
    )
      snapshotLoader.acceptWorkspaceWrite();
    planSelectionRef.current = transition.selection;
    if (transition.studyTarget) transitionStudyView(transition.studyTarget, true);
    dispatch({ type: "plan_transition", transition, ...updates });
  };

  const applyWorkspaceSnapshot = (
    snapshot: WorkspaceSnapshot,
    preferredPlanId: string,
  ) => {
    publishPlanSelection(
      { type: "snapshot", plans: snapshot.plans, preferredPlanId },
      {
        snapshot: {
          ...snapshot,
          selectedPersonaId: resolveSnapshotPersonaId(
            snapshot.personas,
            selectedPersonaIdRef.current,
          ),
        },
      },
    );
  };

  const syncWorkspaceSnapshot = (options: {
    includePersonas: boolean;
    preferredPlanId: string;
    successNotice?: string;
    initial?: boolean;
    onFocus?: boolean;
  }) => {
    const observer = {
      started: () => dispatch({ type: "snapshot_refresh_started" }),
      loaded: (snapshot: WorkspaceSnapshot) => {
        applyWorkspaceSnapshot(snapshot, options.preferredPlanId);
        if (options.successNotice)
          dispatch({ type: "notice_set", notice: options.successNotice });
      },
      failed: (error: unknown) => {
        dispatch({
          type: "notice_set",
          notice: options.initial
            ? resolveStudySessionErrorNotice(error, DISCONNECTED_NOTICE, "history")
            : DISCONNECTED_NOTICE,
        });
        if (options.initial)
          logWorkspaceError("workflow:workspace_snapshot:load_error", error);
      },
      finished: () => dispatch({ type: "snapshot_refresh_finished" }),
    };
    return options.onFocus
      ? snapshotLoader.loadOnFocus(observer)
      : snapshotLoader.load(options.includePersonas, observer);
  };

  const selectPlan = (planId: string, notice?: string) =>
    publishPlanSelection({ type: "select", planId }, { notice });

  const {
    generatePlanWorkflow,
    cancelPlanGeneration,
    checkPendingPlan,
    discardMissingPlan,
    hasPendingPlan,
    isCheckingPlan,
    missingPendingPlan,
    isGeneratingPlan,
    isInterruptingPlan,
    processStreamEvents,
    planStreamEvents,
    processStreamStatus,
    planStreamStatus,
    processStreamDocumentId,
    planStreamDocumentId,
  } = usePlanGeneration({
    personaId: selectedPersona?.id ?? "",
    blockedReason: planGenerationBlockedReason,
    resolveSceneProfile: resolveActiveSceneProfile,
    onStarted: () => {
      publishPlanSelection({ type: "generate" });
      dispatch({ type: "busy_started" });
    },
    onFinished: () => dispatch({ type: "busy_finished" }),
    onNotice: (notice) => dispatch({ type: "notice_set", notice }),
    onDocument: (document) => {
      snapshotLoader.acceptWorkspaceWrite();
      dispatch({ type: "generated_document_applied", document });
    },
    onPlan: (plan) =>
      publishPlanSelection({ type: "generated", plan }, { generatedPlan: plan }),
  });

  const {
    renamePlanTitle,
    removePlan,
    renameStudyUnitTitle,
    updatePlanProgress,
    answerPlanQuestion,
    isMutating,
  } = usePlanMutations({
    plans: state.planHistory,
    documents: state.documents,
    onPlan: (plan) => publishPlanSelection({ type: "update", plans: [plan] }),
    onDocumentAndPlans: ({ document, plans }) =>
      publishPlanSelection({ type: "update", plans }, { document }),
    onNotice: (notice) => dispatch({ type: "notice_set", notice }),
    onDeleted: (planId) => publishPlanSelection({ type: "delete", planId }),
  });

  const applyChatExchange = (
    next: StudyChatResponse & { session: StudySessionRecord },
  ) => {
    publishStudySession(next.session);
    dispatch({
      type: "response_set",
      response: next,
    });
  };

  const {
    chatFailure,
    setChatFailure,
    resetStudyRecovery,
    beginStudyResponseTicket,
    isCurrentStudyResponseTicket,
    applyStudyChatOperation,
    queryStudyChatOperation,
    refreshStudySessionAfterRejectedAdmission,
    isQuerying,
  } = useStudyChatRecovery({
    session: state.studySession,
    view: studyViewFenceRef.current,
    getSelectedPlanId,
    onExchange: applyChatExchange,
    onDialogueInterruptionChanged: () => continuation.syncDialogueInterruption(),
    onSession: publishStudySession,
    onResetView: () =>
      transitionStudyView(`study-plan:${getSelectedPlanId() || "none"}`, true),
    onNotice: (notice) => dispatch({ type: "notice_set", notice }),
  });

  const {
    createSessionForActivePlan,
    ensureSessionForSection,
    handleSwitchSection,
    isNavigating,
  } = useStudySessionNavigation({
    plan: activePlan,
    document: activeDocument,
    view: studyViewFenceRef.current,
    getSelectedPlanId,
    resolveSceneProfile: resolveActiveSceneProfile,
    resolveStudyUnitTitle: (id) =>
      resolveStudyUnitTitle(id, planSections, activeDocument),
    resolveThemeHint: (id) =>
      resolveThemeHintByStudyUnitId(id, activePlan, activeDocument),
    onTransition: transitionStudyView,
    onSession: publishStudySession,
    onNotice: (notice) => dispatch({ type: "notice_set", notice }),
  });

  const {
    handleAsk,
    handleAskForSection,
    retryFailedAsk,
    sendHiddenSessionMessage,
    automaticStudyRequest,
    forgetAutomaticStudyRequest,
    isSending,
  } = useStudyMessages({
    view: studyViewFenceRef.current,
    recovery: {
      chatFailure,
      setChatFailure,
      beginStudyResponseTicket,
      isCurrentStudyResponseTicket,
      applyStudyChatOperation,
    },
    ensureSessionForSection,
    onNotice: (notice) => dispatch({ type: "notice_set", notice }),
  });

  const {
    handleSubmitQuestionAttempt,
    handleResolvePlanConfirmation,
    getQuestionAttemptDiagnosticFlowId,
    isApplying,
  } = useStudyCommitActions({
    view: studyViewFenceRef.current,
    automaticStudyRequest,
    forgetAutomaticStudyRequest,
    onSession: publishStudySession,
    onPlan: (plan) => publishPlanSelection({ type: "update", plans: [plan] }),
    onNotice: (notice) => dispatch({ type: "notice_set", notice }),
  });

  const continuation = useStudyContinuation({
    session: state.studySession,
    view: studyViewFenceRef.current,
    ensureSessionForSection,
    sendHiddenSessionMessage,
    automaticStudyRequest,
    onSession: publishStudySession,
    onNotice: (notice) => dispatch({ type: "notice_set", notice }),
  });
  const {
    triggerSessionPrelude,
    interruptDialogue,
    isDialogueInterrupted,
    isContinuing,
  } = continuation;
  const continueAfterInteractiveQuestion = (turnId: string) => {
    const session = studyViewFenceRef.current.session;
    if (!session) return Promise.resolve(false);
    return continuation.triggerInteractiveQuestionCallback(session, {
      turnId,
      diagnosticFlowId: getQuestionAttemptDiagnosticFlowId(session.id, turnId),
    });
  };

  const loadInitialSnapshot = useEffectEvent(() => {
    void syncWorkspaceSnapshot({
      includePersonas: true,
      preferredPlanId: getSelectedPlanId(),
      successNotice: CONNECTED_NOTICE,
      initial: true,
    });
  });

  useEffect(() => {
    loadInitialSnapshot();
  }, []);

  const refreshOnFocusRef = useRef(() => {});
  refreshOnFocusRef.current = () => {
    void syncWorkspaceSnapshot({
      includePersonas: false,
      preferredPlanId: getSelectedPlanId(),
      onFocus: true,
    });
    // Initial/full snapshots already own the Persona read. Focus must not
    // start a second one from the independent library refresh path.
    if (!snapshotLoader.isLoadingPersonas())
      void refreshPersonaLibrary({ reuseInFlight: true });
    void refreshSceneLibrary({ reuseInFlight: true });
  };
  useEffect(() => {
    const handleFocus = () => refreshOnFocusRef.current();
    window.addEventListener("focus", handleFocus);
    return () => {
      window.removeEventListener("focus", handleFocus);
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
    isBusy:
      state.isBusy ||
      isMutating ||
      isQuerying ||
      isNavigating ||
      isSending ||
      isApplying ||
      isContinuing,
    chatImageUploadEnabled: Boolean(
      runtimeSettings.settings?.openaiChatModelMultimodal,
    ),
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
    checkPendingPlan,
    discardMissingPlan,
    hasPendingPlan,
    isCheckingPlan,
    missingPendingPlan,
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
    continueAfterInteractiveQuestion,
    handleResolvePlanConfirmation,
    interruptDialogue,
    refreshPlanSnapshot: () =>
      syncWorkspaceSnapshot({
        includePersonas: false,
        preferredPlanId: state.selectedPlanId,
        successNotice: SNAPSHOT_REFRESHED_NOTICE,
      }),
  };
}
