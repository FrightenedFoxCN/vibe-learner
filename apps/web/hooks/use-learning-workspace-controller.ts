"use client";


import { useState } from "react";
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
import {
  cancelStudySessionFollowUps,
  resolveStudyPlanConfirmation,
  submitStudyQuestionAttempt,
} from "../lib/data/study-sessions";
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
import {
  appendDeferredInteractiveCallback,
  clearDeferredInteractiveCallbacks as clearPersistedDeferredInteractiveCallbacks,
  readDeferredInteractiveCallbacks,
  readInterruptedDialogueSessionId,
  writeInterruptedDialogueSessionId,
} from "../lib/study-dialogue-interruption";
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
import { decideStudyQuestionAttemptApply } from "../lib/study-question-attempt";
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
  const [interruptedDialogueSessionId, setInterruptedDialogueSessionId] = useState("");
  const mountedRef = useRef(true);
  const selectedPersonaIdRef = useRef(state.selectedPersonaId);
  const selectedPlanIdRef = useRef(state.selectedPlanId);
  const preludeInFlightRef = useRef<Set<string>>(new Set());
  const preludeFailedRef = useRef<Set<string>>(new Set());
  const snapshotLoaderRef = useRef<WorkspaceSnapshotLoader | null>(null);
  if (snapshotLoaderRef.current === null) {
    snapshotLoaderRef.current = new WorkspaceSnapshotLoader({ listDocuments, listLearningPlans, listPersonas });
  }
  const snapshotLoader = snapshotLoaderRef.current;
  const followUpTimerRef = useRef<Map<string, number>>(new Map());
  const followUpInFlightRef = useRef<Set<string>>(new Set());
  const interruptedDialogueSessionIdRef = useRef("");
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
  const isDialogueInterrupted = Boolean(
    state.studySession?.id && state.studySession.id === interruptedDialogueSessionId
  );

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
    const persistedSessionId = readInterruptedDialogueSessionId();
    interruptedDialogueSessionIdRef.current = persistedSessionId;
    setInterruptedDialogueSessionId(persistedSessionId);
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

  const syncInterruptedDialogueSessionId = (sessionId: string) => {
    const normalizedSessionId = sessionId.trim();
    interruptedDialogueSessionIdRef.current = normalizedSessionId;
    setInterruptedDialogueSessionId(normalizedSessionId);
    writeInterruptedDialogueSessionId(normalizedSessionId);
  };

  const isDialogueInterruptedForSession = (sessionId: string) => {
    const normalizedSessionId = sessionId.trim();
    return Boolean(
      normalizedSessionId &&
      interruptedDialogueSessionIdRef.current === normalizedSessionId
    );
  };

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

  const queueDeferredInteractiveCallback = (sessionId: string, callbackMessage: string) => {
    const normalizedSessionId = sessionId.trim();
    const normalizedMessage = callbackMessage.trim();
    if (!normalizedSessionId || !normalizedMessage) {
      return;
    }
    appendDeferredInteractiveCallback(normalizedSessionId, normalizedMessage);
  };

  const peekDeferredInteractiveCallbackPrefix = (sessionId: string) => {
    const normalizedSessionId = sessionId.trim();
    if (!normalizedSessionId) {
      return "";
    }
    return readDeferredInteractiveCallbacks(normalizedSessionId).join("\n\n");
  };

  const clearDeferredInteractiveCallbacks = (sessionId: string) => {
    const normalizedSessionId = sessionId.trim();
    if (!normalizedSessionId) {
      return;
    }
    clearPersistedDeferredInteractiveCallbacks(normalizedSessionId);
  };

  const clearInterruptedDialogueState = (sessionId: string) => {
    const normalizedSessionId = sessionId.trim();
    if (!normalizedSessionId) {
      return;
    }
    clearDeferredInteractiveCallbacks(normalizedSessionId);
    if (interruptedDialogueSessionIdRef.current === normalizedSessionId) {
      syncInterruptedDialogueSessionId("");
    }
  };

  const clearPendingFollowUpTimers = (followUpIds: string[]) => {
    const timers = followUpTimerRef.current;
    followUpIds.forEach((followUpId) => {
      const timer = timers.get(followUpId);
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
      timers.delete(followUpId);
    });
  };

  const { handleAsk, handleAskForSection, retryFailedAsk, sendHiddenSessionMessage,
    automaticStudyRequest, forgetAutomaticStudyRequest, isSending } = useStudyMessages({
    view: studyViewFenceRef.current,
    recovery: { chatFailure, setChatFailure, beginStudyResponseTicket, isCurrentStudyResponseTicket, applyStudyChatOperation },
    ensureSessionForSection, isDialogueInterruptedForSession,
    peekDeferredInteractiveCallbackPrefix, clearInterruptedDialogueState,
    onNotice: (notice) => dispatch({ type: "notice_set", notice }),
  });

  const runSessionPrelude = async (input: {
    session: StudySessionRecord;
    studyUnitId: string;
    sectionTitle: string;
    themeHint: string;
    force?: boolean;
  }) => {
    const normalizedStudyUnitId = input.studyUnitId.trim();
    if (!normalizedStudyUnitId) {
      return false;
    }
    if (!input.force && input.session.preparedStudyUnitIds?.includes(normalizedStudyUnitId)) {
      return false;
    }
    const requestKey = `${input.session.id}:${normalizedStudyUnitId}`;
    if (input.force) {
      preludeFailedRef.current.delete(requestKey);
    } else if (preludeFailedRef.current.has(requestKey)) {
      return false;
    }
    if (preludeInFlightRef.current.has(requestKey)) {
      return false;
    }
    preludeInFlightRef.current.add(requestKey);
    try {
      dispatch({ type: "busy_started" });
      const operationKey = `prelude:${requestKey}:${input.session.revision}`;
      const operationIdentity = automaticStudyRequest(
        operationKey,
        "prelude",
      );
      await sendHiddenSessionMessage({
        session: input.session,
        operationKey,
        ...operationIdentity,
        message: buildSessionPreludeMessage({
          sectionTitle: input.sectionTitle,
          themeHint: input.themeHint,
        }),
        messageKind: "session_prelude",
      });
      return true;
    } catch (error) {
      preludeFailedRef.current.add(requestKey);
      dispatch({
        type: "notice_set",
        notice: resolveStudySessionErrorNotice(
          error,
          `章节准备失败：${String(error)}`,
          "response",
        ),
      });
      logWorkspaceError("workflow:study_session:prelude_error", error);
      return false;
    } finally {
      preludeInFlightRef.current.delete(requestKey);
      dispatch({ type: "busy_finished" });
    }
  };

  const triggerSessionPrelude = async (input: {
    studyUnitId: string;
    sectionTitle?: string;
    themeHint?: string;
  }) => {
    const session = await ensureSessionForSection(input.studyUnitId, {
      clearResponseOnSwitch: false,
    });
    if (!session) {
      return false;
    }
    return runSessionPrelude({
      session,
      studyUnitId: input.studyUnitId,
      sectionTitle: input.sectionTitle || session.studyUnitTitle || session.studyUnitId,
      themeHint: input.themeHint ?? session.themeHint ?? "",
      force: true,
    });
  };

  const triggerInteractiveQuestionCallback = async (
    session: StudySessionRecord,
    input: { turnId: string }
  ) => {
    const committedQuestion = session.turns.find(
      (turn) => turn.id === input.turnId
    )?.interactiveQuestion;
    if (!committedQuestion?.callBack) {
      return;
    }
    const committedResult = committedQuestion.result;
    if (
      !committedResult?.submittedAnswer ||
      typeof committedResult.isCorrect !== "boolean" ||
      !committedResult.feedbackText.trim()
    ) {
      logWorkspaceError(
        "workflow:study_attempt:callback_read_back_missing",
        new Error("study_question_attempt_callback_read_back_missing"),
      );
      return;
    }
    const callbackMessage = buildInteractiveCallbackMessage({
      questionType: committedQuestion.questionType,
      prompt: committedQuestion.prompt,
      topic: committedQuestion.topic,
      submittedAnswer: committedResult.submittedAnswer,
      isCorrect: committedResult.isCorrect,
      explanation: committedResult.explanation,
    });
    if (isDialogueInterruptedForSession(session.id)) {
      queueDeferredInteractiveCallback(session.id, callbackMessage);
      dispatch({
        type: "notice_set",
        notice: "答案已记录；已暂停自动续接，会在你下次主动发言前补入答题结果。"
      });
      return;
    }
    try {
      dispatch({ type: "busy_started" });
      const operationKey = `callback:${session.id}:${input.turnId}:${session.revision}`;
      const operationIdentity = automaticStudyRequest(
        operationKey,
        "callback",
      );
      await sendHiddenSessionMessage({
        session,
        operationKey,
        ...operationIdentity,
        message: callbackMessage,
        messageKind: "interactive_callback",
      });
    } catch (callbackError) {
      dispatch({
        type: "notice_set",
        notice: resolveStudySessionErrorNotice(
          callbackError,
          `答案已记录，续问失败：${String(callbackError)}`,
          "response",
        )
      });
      logWorkspaceError("workflow:study_attempt:callback_error", callbackError);
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

  const handleSubmitQuestionAttempt = async (input: {
    turnId: string;
    submittedAnswer: string;
  }) => {
    const currentSession = studyViewFenceRef.current.session;
    if (!currentSession) {
      return false;
    }
    const attemptKey = `attempt:${currentSession.id}:${input.turnId}`;
    const attemptIdentity = automaticStudyRequest(
      attemptKey,
      "attempt",
    );
    try {
      const committed = await submitStudyQuestionAttempt({
        sessionId: currentSession.id,
        turnId: input.turnId,
        expectedSessionRevision: currentSession.revision,
        clientAttemptId: attemptIdentity.clientRequestId,
        submittedAnswer: input.submittedAnswer,
      });
      const nextSession = committed.session;
      const latestSession = studyViewFenceRef.current.session;
      const applyDecision = decideStudyQuestionAttemptApply({
        before: currentSession,
        after: nextSession,
        current: latestSession,
        turnId: input.turnId,
        submittedAnswer: input.submittedAnswer,
        attempt: committed.attempt,
      });
      if (applyDecision === "reject") {
        throw new Error("study_question_attempt_read_back_mismatch");
      }
      if (applyDecision === "apply_returned") {
        activateStudySessionView(nextSession);
        dispatch({
          type: "study_session_set",
          studySession: nextSession,
          clearResponse: false
        });
      }
      const authoritativeSession = applyDecision === "apply_returned"
        ? nextSession
        : applyDecision === "keep_current"
          ? latestSession
          : null;
      if (authoritativeSession) {
        void triggerInteractiveQuestionCallback(authoritativeSession, {
          turnId: input.turnId,
        });
      }
      forgetAutomaticStudyRequest(
        attemptKey,
      );
      return true;
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: resolveStudySessionErrorNotice(
          error,
          `记录答案失败：${String(error)}`,
          "update",
        )
      });
      logWorkspaceError("workflow:study_attempt:error", error);
      return false;
    }
  };

  const handleResolvePlanConfirmation = async (input: {
    confirmationId: string;
    decision: "approve" | "reject";
    note?: string;
  }) => {
    const targetSession = studyViewFenceRef.current.session;
    if (!targetSession) {
      return false;
    }
    const targetViewRevision = studyViewFenceRef.current.viewRevision;
    try {
      dispatch({ type: "busy_started" });
      const next = await resolveStudyPlanConfirmation({
        sessionId: targetSession.id,
        confirmationId: input.confirmationId,
        decision: input.decision,
        note: input.note,
      });
      if (
        studyViewFenceRef.current.session?.id !== targetSession.id ||
        studyViewFenceRef.current.viewRevision !== targetViewRevision
      ) {
        return false;
      }
      activateStudySessionView(next.session);
      dispatch({
        type: "study_session_set",
        studySession: next.session,
        clearResponse: false,
      });
      if (next.plan) {
        dispatch({
          type: "plan_updated",
          plan: next.plan,
        });
      }
      dispatch({
        type: "notice_set",
        notice: input.decision === "approve" ? "计划已更新。" : "已保留原计划。",
      });
      return true;
    } catch (error) {
      if (
        studyViewFenceRef.current.session?.id !== targetSession.id ||
        studyViewFenceRef.current.viewRevision !== targetViewRevision
      ) {
        return false;
      }
      dispatch({
        type: "notice_set",
        notice: resolveStudySessionErrorNotice(
          error,
          `处理计划变更失败：${String(error)}`,
          "update",
        ),
      });
      logWorkspaceError("workflow:study_plan_confirmation:error", error);
      return false;
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

  const interruptDialogue = async () => {
    const session = studyViewFenceRef.current.session;
    if (!session) {
      dispatch({
        type: "notice_set",
        notice: "当前还没有可打断的学习单元会话。"
      });
      return false;
    }
    const pendingFollowUpIds = (session?.pendingFollowUps ?? [])
      .filter((item) => item.status === "pending")
      .map((item) => item.id);
    if (isDialogueInterruptedForSession(session.id) && !pendingFollowUpIds.length) {
      dispatch({
        type: "notice_set",
        notice: "当前已暂停自动续接；答题结果会等你下次主动发言时再补入。"
      });
      return false;
    }
    if (!pendingFollowUpIds.length) {
      syncInterruptedDialogueSessionId(session.id);
      dispatch({
        type: "notice_set",
        notice: "已暂停当前自动续接；之后提交答案不会立即续聊。"
      });
      return true;
    }
    clearPendingFollowUpTimers(pendingFollowUpIds);
    const targetViewRevision = studyViewFenceRef.current.viewRevision;
    try {
      dispatch({ type: "busy_started" });
      const nextSession = await cancelStudySessionFollowUps({
        sessionId: session.id,
      });
      if (
        studyViewFenceRef.current.session?.id !== session.id ||
        studyViewFenceRef.current.viewRevision !== targetViewRevision
      ) {
        return false;
      }
      activateStudySessionView(nextSession);
      dispatch({
        type: "study_session_set",
        studySession: nextSession,
        clearResponse: false,
      });
      syncInterruptedDialogueSessionId(nextSession.id);
      dispatch({
        type: "notice_set",
        notice: "已打断当前自动续接；之后提交答案不会立即续聊。"
      });
      return true;
    } catch (error) {
      if (
        studyViewFenceRef.current.session?.id !== session.id ||
        studyViewFenceRef.current.viewRevision !== targetViewRevision
      ) {
        return false;
      }
      dispatch({
        type: "notice_set",
        notice: resolveStudySessionErrorNotice(
          error,
          `打断自动续接失败：${String(error)}`,
          "update",
        )
      });
      logWorkspaceError("workflow:study_follow_up:interrupt_error", error);
      return false;
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

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

  useEffect(() => {
    if (!state.studySession) {
      return;
    }
    const session = state.studySession;
    const studyUnitId = session.studyUnitId;
    if (!studyUnitId || state.isBusy || isMutating || isQuerying || isNavigating || isSending) {
      return;
    }
    void runSessionPrelude({
      session,
      studyUnitId,
      sectionTitle: session.studyUnitTitle ?? session.studyUnitId,
      themeHint: session.themeHint ?? "",
      force: false,
    });
  }, [state.isBusy, isMutating, isQuerying, isNavigating, isSending, state.studySession]);

  useEffect(() => {
    const session = state.studySession;
    const timers = followUpTimerRef.current;
    const pendingIds = new Set(
      (session?.pendingFollowUps ?? [])
        .filter((item) => item.status === "pending")
        .map((item) => item.id)
    );
    Array.from(timers.keys()).forEach((id) => {
      if (pendingIds.has(id)) {
        return;
      }
      const timer = timers.get(id);
      if (timer !== undefined) {
        window.clearTimeout(timer);
      }
      timers.delete(id);
    });
    if (!session) {
      return;
    }
    (session.pendingFollowUps ?? [])
      .filter((item) => item.status === "pending")
      .forEach((item) => {
        if (timers.has(item.id) || followUpInFlightRef.current.has(item.id)) {
          return;
        }
        const dueAt = Date.parse(item.dueAt || "");
        const delay = Number.isFinite(dueAt) ? Math.max(0, dueAt - Date.now()) : 0;
        const timer = window.setTimeout(() => {
          timers.delete(item.id);
          if (followUpInFlightRef.current.has(item.id)) {
            return;
          }
          followUpInFlightRef.current.add(item.id);
          void (async () => {
            try {
              dispatch({ type: "busy_started" });
              const operationKey = `follow-up:${session.id}:${item.id}`;
              const operationIdentity = automaticStudyRequest(
                operationKey,
                "follow-up",
              );
              await sendHiddenSessionMessage({
                session,
                operationKey,
                ...operationIdentity,
                message: item.hiddenMessage,
                messageKind: "scheduled_follow_up",
                followUpId: item.id,
              });
            } catch (error) {
              if (String(error).includes("follow_up_not_pending")) {
                return;
              }
              dispatch({
                type: "notice_set",
                notice: resolveStudySessionErrorNotice(
                  error,
                  `自动续接失败：${String(error)}`,
                  "response",
                ),
              });
              logWorkspaceError("workflow:study_follow_up:error", error);
            } finally {
              followUpInFlightRef.current.delete(item.id);
              dispatch({ type: "busy_finished" });
            }
          })();
        }, delay);
        timers.set(item.id, timer);
      });
  }, [state.isBusy, isMutating, isQuerying, isNavigating, isSending, state.studySession]);

  useEffect(() => {
    return () => {
      const timers = followUpTimerRef.current;
      Array.from(timers.values()).forEach((timer) => window.clearTimeout(timer));
      timers.clear();
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
    isBusy: state.isBusy || isMutating || isQuerying || isNavigating || isSending,
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

function buildInteractiveCallbackMessage(input: {
  questionType: "multiple_choice" | "fill_blank";
  prompt: string;
  topic: string;
  submittedAnswer: string;
  isCorrect: boolean;
  explanation: string;
}) {
  const verdict = input.isCorrect ? "正确" : "不正确";
  return [
    `学习者刚完成了一道${input.questionType === "multiple_choice" ? "选择题" : "填空题"}。`,
    `题目：${input.prompt}`,
    `主题：${input.topic || "章节练习"}`,
    `学习者答案：${input.submittedAnswer || "（空）"}`,
    `判定：${verdict}`,
    input.explanation ? `解析：${input.explanation}` : "",
    input.isCorrect
      ? "请基于这次正确作答继续推进下一步讲解或追问。"
      : "请先针对错误点做纠正，再继续推进下一步讲解或追问。"
  ].filter(Boolean).join("\n");
}

function buildSessionPreludeMessage(input: {
  sectionTitle: string;
  themeHint: string;
}) {
  return [
    "正式对话开始前，请先完成一轮隐藏的学习单元预处理和自然引入。",
    `当前学习单元：${input.sectionTitle || "未命名学习单元"}`,
    `当前主题：${input.themeHint || "未额外指定"}`,
    "要求：",
    "1. 如果需要，可先调用计划、场景、教材或时间相关工具，确认当前上下文。",
    "2. 用 2 到 4 句自然地把学习者带入这一学习单元，说明你准备如何陪他学。",
    "3. 如果场景、物体、教材页码或公式焦点有帮助，可以顺手把它们纳入引入。",
    "4. 不要提到这是隐藏消息、预处理消息或内部流程。"
  ].join("\n");
}
