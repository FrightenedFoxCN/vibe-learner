"use client";

import { useState } from "react";
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
  processDocumentStream,
  updateDocumentStudyUnitTitle as updateDocumentStudyUnitTitleRequest,
  uploadDocument,
} from "../lib/data/documents";
import {
  answerLearningPlanQuestion,
  cancelStreamRun,
  createLearningPlanStream,
  deleteLearningPlan as deleteLearningPlanRequest,
  listLearningPlans,
  updateLearningPlanProgress as updateLearningPlanProgressRequest,
  updateLearningPlanTitle as updateLearningPlanTitleRequest,
} from "../lib/data/learning-plans";
import { listPersonas } from "../lib/data/personas";
import { listSceneLibrary, type SceneLibraryItemPayload } from "../lib/data/scenes";
import {
  cancelStudySessionFollowUps,
  createStudySession,
  getStudyChatOperation,
  listStudySessions,
  resolveStudyPlanConfirmation,
  sendStudyMessage,
  submitStudyQuestionAttempt,
  updateStudySessionStudyUnit,
  type StudyChatOperationResponse,
} from "../lib/data/study-sessions";
import { mockPersonas } from "../lib/mock-data";
import {
  buildPlanHistoryItems,
  findDocumentForPlan,
  findLearningPlan
} from "../lib/plan-panel-data";
import {
  buildInitialStudySessionInput,
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
  PLAN_GENERATED_NOTICE,
  PLAN_GENERATED_SESSION_FAILED_NOTICE,
  SESSION_CREATED_NOTICE,
  SNAPSHOT_REFRESHED_NOTICE
} from "../lib/learning-workspace-copy";
import { resolveStudySessionErrorNotice } from "../lib/study-session-decode";
import { decideStudyQuestionAttemptApply } from "../lib/study-question-attempt";
import {
  logWorkspaceError,
  logWorkspaceInfo
} from "../lib/learning-workspace-telemetry";
import { compactPreviewValue } from "../lib/preview";
import { getDesktopRuntimeConfig } from "../lib/runtime-config";
import { useRuntimeSettings } from "../components/runtime-settings-provider";
import type { StudyChatOperationStatus } from "../lib/study-chat-operation-decode";
import {
  isDefiniteStudyChatPreAdmissionError,
  isMissingStudyChatOperationError,
  studyChatPreAdmissionNotice,
} from "../lib/http-error";

export interface GeneratePlanInput {
  mode: "document" | "goal_only";
  file?: File | null;
  objective: string;
}

type StreamEventItem = {
  stage: string;
  payload: Record<string, unknown>;
};

type ChatFailureState = {
  message: string;
  studyUnitId: string;
  detail: string;
  attachments: File[];
  sessionId: string;
  clientRequestId: string;
  expectedSessionRevision: number;
  messageKind: string;
  followUpId?: string;
  hiddenMessagePrefix?: string;
  operationStatus: StudyChatOperationStatus | "unresolved";
  canQuery: boolean;
  canResend: boolean;
  canRefreshSession: boolean;
};

type StudyChatDraft = Omit<
  ChatFailureState,
  "detail" | "operationStatus" | "canQuery" | "canResend" | "canRefreshSession"
>;

type PendingStudyOperationIdentity = Pick<
  StudyChatDraft,
  "sessionId" | "clientRequestId" | "expectedSessionRevision"
> & {
  messageKind?: string;
  studyUnitId?: string;
};

const PENDING_STUDY_OPERATION_STORAGE_KEY = "vibe-learner:pending-study-chat-operation:v1";
const AUTOMATIC_STUDY_REQUEST_STORAGE_KEY = "vibe-learner:automatic-study-chat-requests:v1";

interface UseLearningWorkspaceControllerOptions {
  initialPlan?: LearningPlan;
  initialPersonas?: PersonaProfile[];
}

export function useLearningWorkspaceController({
  initialPlan,
  initialPersonas = mockPersonas
}: UseLearningWorkspaceControllerOptions) {
  const runtimeSettings = useRuntimeSettings();
  const [state, dispatch] = useReducer(
    learningWorkspaceReducer,
    createInitialLearningWorkspaceState({
      initialPlan,
      initialPersonas
    })
  );
  const [isGeneratingPlan, setIsGeneratingPlan] = useState(false);
  const [isInterruptingPlan, setIsInterruptingPlan] = useState(false);
  const [processStreamEvents, setProcessStreamEvents] = useState<StreamEventItem[]>([]);
  const [planStreamEvents, setPlanStreamEvents] = useState<StreamEventItem[]>([]);
  const [processStreamStatus, setProcessStreamStatus] = useState("idle");
  const [planStreamStatus, setPlanStreamStatus] = useState("idle");
  const [processStreamDocumentId, setProcessStreamDocumentId] = useState("");
  const [planStreamDocumentId, setPlanStreamDocumentId] = useState("");
  const [chatFailure, setChatFailure] = useState<ChatFailureState | null>(null);
  const [sceneLibraryItems, setSceneLibraryItems] = useState<SceneLibraryItemPayload[]>([]);
  const [selectedSceneLibraryId, setSelectedSceneLibraryId] = useState("");
  const [interruptedDialogueSessionId, setInterruptedDialogueSessionId] = useState("");
  const selectedPersonaIdRef = useRef(state.selectedPersonaId);
  const selectedPlanIdRef = useRef(state.selectedPlanId);
  const generationAbortControllerRef = useRef<AbortController | null>(null);
  const processStreamIdRef = useRef("");
  const planStreamIdRef = useRef("");
  const preludeInFlightRef = useRef<Set<string>>(new Set());
  const automaticRequestIdsRef = useRef<Map<string, string>>(new Map());
  const followUpTimerRef = useRef<Map<string, number>>(new Map());
  const followUpInFlightRef = useRef<Set<string>>(new Set());
  const interruptedDialogueSessionIdRef = useRef("");
  const studySessionRef = useRef<StudySessionRecord | null>(state.studySession);
  const restoredStudyOperationRef = useRef("");
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
    studySessionRef.current = state.studySession;
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

  const fetchLatestSessionForPlan = async (): Promise<StudySessionRecord | null> => {
    if (!activePlan) {
      return null;
    }
    const sessions = await listStudySessions({
      documentId: activeDocument?.id,
      personaId: activePlan.personaId,
      planId: activePlan.id,
    });
    if (!sessions.length) {
      return null;
    }
    const sorted = [...sessions].sort((a, b) => {
      const aTime = Date.parse(a.updatedAt || "") || 0;
      const bTime = Date.parse(b.updatedAt || "") || 0;
      return bTime - aTime;
    });
    return sorted[0] ?? null;
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

    dispatch({
      type: "snapshot_applied",
      personas: snapshot.personas,
      resolution: nextState
    });
  };

  const readWorkspaceSnapshot = async (includePersonas: boolean): Promise<WorkspaceSnapshot> => {
    if (includePersonas) {
      const [remotePersonas, remoteDocuments, remotePlans] = await Promise.all([
        listPersonas(),
        listDocuments(),
        listLearningPlans()
      ]);
      return {
        personas: remotePersonas,
        documents: remoteDocuments,
        plans: remotePlans
      };
    }

    const [remoteDocuments, remotePlans] = await Promise.all([
      listDocuments(),
      listLearningPlans()
    ]);
    return {
      documents: remoteDocuments,
      plans: remotePlans
    };
  };

  const syncWorkspaceSnapshot = async (options: {
    includePersonas: boolean;
    preferredPlanId: string;
    successNotice?: string;
  }) => {
    try {
      dispatch({ type: "snapshot_refresh_started" });
      const snapshot = await readWorkspaceSnapshot(options.includePersonas);
      applyWorkspaceSnapshot(snapshot, options.preferredPlanId);
      if (options.successNotice) {
        dispatch({ type: "notice_set", notice: options.successNotice });
      }
    } catch {
      dispatch({ type: "notice_set", notice: DISCONNECTED_NOTICE });
    } finally {
      dispatch({ type: "snapshot_refresh_finished" });
    }
  };

  const selectPlan = (planId: string, noticeMessage?: string) => {
    const nextPlan = findLearningPlan(state.planHistory, planId);
    if (!nextPlan || nextPlan.id === state.selectedPlanId) {
      return;
    }
    dispatch({
      type: "plan_selected",
      planId: nextPlan.id,
      notice: noticeMessage
    });
  };

  const applyGeneratedDocument = (nextDocument: DocumentRecord) => {
    dispatch({
      type: "generated_document_applied",
      document: nextDocument
    });
  };

  const applyGeneratedPlan = (nextPlan: LearningPlan) => {
    dispatch({
      type: "generated_plan_applied",
      plan: nextPlan
    });
  };

  const createInitialStudySession = async (input: {
    plan: LearningPlan;
    document?: DocumentRecord | null;
    planId: string;
    personaId: string;
  }): Promise<StudySessionRecord> => {
    const sceneProfile = resolveActiveSceneProfile();
    const nextSession = await createStudySession(
      {
        ...buildInitialStudySessionInput(input),
        sceneProfile,
      }
    );
    logWorkspaceInfo("workflow:upload:session_ready", {
      sessionId: nextSession.id,
      studyUnitId: nextSession.studyUnitId
    });
    return nextSession;
  };

  const cancelPlanGeneration = async () => {
    if (!isGeneratingPlan) {
      return;
    }
    setIsInterruptingPlan(true);
    dispatch({
      type: "notice_set",
      notice: "正在中断当前任务…"
    });
    const streamIds = Array.from(
      new Set(
        [processStreamIdRef.current, planStreamIdRef.current]
          .map((item) => item.trim())
          .filter(Boolean)
      )
    );
    generationAbortControllerRef.current?.abort();
    if (streamIds.length) {
      await Promise.allSettled(streamIds.map((streamId) => cancelStreamRun(streamId)));
    }
  };

  const generatePlanWorkflow = async (input: GeneratePlanInput) => {
    if (planGenerationBlockedReason) {
      dispatch({
        type: "notice_set",
        notice: planGenerationBlockedReason,
      });
      return;
    }
    generationAbortControllerRef.current?.abort();
    const abortController = new AbortController();
    generationAbortControllerRef.current = abortController;
    processStreamIdRef.current = "";
    planStreamIdRef.current = "";
    setIsInterruptingPlan(false);
    setIsGeneratingPlan(true);
    dispatch({ type: "generation_started" });
    dispatch({ type: "busy_started" });
    setProcessStreamEvents([]);
    setPlanStreamEvents([]);
    setProcessStreamStatus(input.mode === "document" ? "running" : "idle");
    setPlanStreamStatus("idle");
    try {
      const sceneProfile = resolveActiveSceneProfile();
      let nextDocument: DocumentRecord | null = null;

      if (input.mode === "document") {
        if (!input.file) {
          throw new Error("missing_plan_source_document");
        }
        logWorkspaceInfo("workflow:upload:start", {
          filename: input.file.name,
          sizeBytes: input.file.size,
          personaId: selectedPersona.id
        });

        const uploadedDocument = await uploadDocument(input.file, {
          signal: abortController.signal,
        });
        setProcessStreamDocumentId(uploadedDocument.id);
        setPlanStreamDocumentId(uploadedDocument.id);
        dispatch({
          type: "notice_set",
          notice: "教材已上传，正在解析。"
        });
        logWorkspaceInfo("workflow:upload:document_uploaded", {
          documentId: uploadedDocument.id,
          status: uploadedDocument.status
        });

        nextDocument = await processDocumentStream(
          uploadedDocument.id,
          {
            signal: abortController.signal,
          },
          (event) => {
            const streamId = event.operationId?.trim() ?? "";
            if (streamId) {
              processStreamIdRef.current = streamId;
            }
            setProcessStreamEvents((current) => [
              ...current.slice(-79),
              {
                stage: event.stage,
                payload: compactPreviewValue(event.payload) as Record<string, unknown>
              }
            ]);
            setProcessStreamStatus(resolveStreamStatus(event.stage));
            dispatch({
              type: "notice_set",
              notice: "正在解析教材…"
            });
            logWorkspaceInfo("workflow:upload:process_event", {
              documentId: uploadedDocument.id,
              stage: event.stage,
              ...event.payload
            });
          }
        );
        logWorkspaceInfo("workflow:upload:document_ready", {
          documentId: nextDocument.id,
          pageCount: nextDocument.pageCount,
          chunkCount: nextDocument.chunkCount,
          ocrStatus: nextDocument.ocrStatus
        });
        applyGeneratedDocument(nextDocument);
        dispatch({
          type: "notice_set",
          notice: "教材解析完成，正在生成计划。"
        });
      } else {
        setProcessStreamDocumentId("");
        setPlanStreamDocumentId("");
        dispatch({
          type: "notice_set",
          notice: "正在生成计划。"
        });
        logWorkspaceInfo("workflow:goal_only:start", {
          personaId: selectedPersona.id,
          objectiveLength: input.objective.length
        });
      }

      setPlanStreamStatus("running");
      const planClientRequestId = createStudyChatRequestId("learning-plan");
      const nextPlan = await createLearningPlanStream(
        {
          documentId: nextDocument?.id ?? "",
          personaId: selectedPersona.id,
          clientRequestId: planClientRequestId,
          expectedDocumentUpdatedAt: nextDocument?.updatedAt ?? "",
          objective: input.objective,
          sceneProfileSummary: sceneProfile?.summary ?? "",
          sceneProfile,
        },
        (event) => {
          const streamId = event.operationId?.trim() ?? "";
          if (streamId) {
            planStreamIdRef.current = streamId;
          }
          setPlanStreamEvents((current) => [
            ...current.slice(-119),
            {
              stage: event.stage,
              payload: compactPreviewValue(event.payload) as Record<string, unknown>
            }
          ]);
          setPlanStreamStatus(resolveStreamStatus(event.stage));
          dispatch({
            type: "notice_set",
            notice: "正在生成计划…"
          });
          logWorkspaceInfo("workflow:plan_event", {
            documentId: nextDocument?.id ?? "",
            stage: event.stage,
            ...event.payload
          });
        },
        {
          signal: abortController.signal,
        }
      );
      logWorkspaceInfo("workflow:upload:plan_ready", {
        planId: nextPlan.id,
        taskCount: nextPlan.todayTasks.length
      });
      applyGeneratedPlan(nextPlan);

      try {
        const nextSession = await createInitialStudySession({
          plan: nextPlan,
          document: nextDocument,
          planId: nextPlan.id,
          personaId: selectedPersona.id
        });
        dispatch({
          type: "study_session_set",
          studySession: nextSession,
          clearResponse: true
        });
        dispatch({
          type: "notice_set",
          notice:
            nextPlan.creationMode === "goal_only"
              ? "目标计划已生成，会话已创建。"
              : PLAN_GENERATED_NOTICE
        });
      } catch (sessionError) {
        dispatch({
          type: "notice_set",
          notice: PLAN_GENERATED_SESSION_FAILED_NOTICE
        });
        logWorkspaceError("workflow:upload:session_error", sessionError);
      }
    } catch (error) {
      if (isAbortLikeError(error)) {
        setProcessStreamStatus((current) => (current === "running" ? "cancelled" : current));
        setPlanStreamStatus((current) => (current === "running" ? "cancelled" : current));
        dispatch({
          type: "notice_set",
          notice: "已中断当前任务。"
        });
        logWorkspaceInfo("workflow:upload:interrupted", {
          mode: input.mode,
        });
        return;
      }
      setProcessStreamStatus((current) => (current === "running" ? "error" : current));
      setPlanStreamStatus((current) => (current === "running" ? "error" : current));
      dispatch({
        type: "notice_set",
        notice: `${input.mode === "document" ? "教材处理失败" : "目标计划生成失败"}：${String(error)}`
      });
      logWorkspaceError("workflow:upload:error", error);
    } finally {
      generationAbortControllerRef.current = null;
      processStreamIdRef.current = "";
      planStreamIdRef.current = "";
      setIsInterruptingPlan(false);
      dispatch({ type: "busy_finished" });
      setIsGeneratingPlan(false);
    }
  };

  const createSessionForActivePlan = async () => {
    if (!activePlan) {
      return;
    }
    try {
      dispatch({ type: "busy_started" });
      const nextSession = await createStudySession(
        {
          ...buildInitialStudySessionInput({
            plan: activePlan,
            document: activeDocument,
            planId: activePlan.id,
            personaId: activePlan.personaId
          }),
          sceneProfile: resolveActiveSceneProfile(),
        }
      );
      dispatch({
        type: "study_session_set",
        studySession: nextSession,
        clearResponse: true
      });
      dispatch({
        type: "notice_set",
        notice: SESSION_CREATED_NOTICE
      });
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: resolveStudySessionErrorNotice(
          error,
          `创建会话失败：${String(error)}`,
          "update",
        )
      });
      logWorkspaceError("workflow:session_create:error", error);
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

  const renamePlanTitle = async (planId: string, courseTitle: string) => {
    const normalizedTitle = courseTitle.trim();
    if (!planId || !normalizedTitle) {
      return false;
    }
    try {
      dispatch({ type: "busy_started" });
      const updatedPlan = await updateLearningPlanTitleRequest(planId, normalizedTitle);
      dispatch({
        type: "plan_updated",
        plan: updatedPlan
      });
      dispatch({
        type: "notice_set",
        notice: "题目已更新。"
      });
      return true;
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: `更新题目失败：${String(error)}`
      });
      logWorkspaceError("workflow:plan_title_update:error", error);
      return false;
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

  const removePlan = async (planId: string) => {
    if (!planId) {
      return false;
    }
    const preferredPlanId =
      state.selectedPlanId === planId
        ? state.planHistory.find((plan) => plan.id !== planId)?.id ?? ""
        : state.selectedPlanId;
    try {
      dispatch({ type: "busy_started" });
      await deleteLearningPlanRequest(planId);
      dispatch({
        type: "plan_deleted",
        planId,
        preferredPlanId
      });
      dispatch({
        type: "notice_set",
        notice: "计划已删除。"
      });
      return true;
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: `删除计划失败：${String(error)}`
      });
      logWorkspaceError("workflow:plan_delete:error", error);
      return false;
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

  const renameStudyUnitTitle = async (
    documentId: string,
    studyUnitId: string,
    title: string
  ) => {
    const normalizedTitle = title.trim();
    if (!documentId || !studyUnitId || !normalizedTitle) {
      return false;
    }
    try {
      dispatch({ type: "busy_started" });
      const payload = await updateDocumentStudyUnitTitleRequest(
        documentId,
        studyUnitId,
        normalizedTitle
      );
      dispatch({
        type: "document_and_plans_updated",
        document: payload.document,
        plans: payload.plans
      });
      dispatch({
        type: "notice_set",
        notice: "学习单元已更新。"
      });
      return true;
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: `更新学习单元失败：${String(error)}`
      });
      logWorkspaceError("workflow:study_unit_title_update:error", error);
      return false;
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

  const updatePlanProgress = async (input: {
    planId: string;
    scheduleIds: string[];
    status: string;
    note?: string;
  }) => {
    if (!input.planId || !input.scheduleIds.length || !input.status.trim()) {
      return false;
    }
    try {
      dispatch({ type: "busy_started" });
      const updatedPlan = await updateLearningPlanProgressRequest(input);
      dispatch({
        type: "plan_updated",
        plan: updatedPlan
      });
      dispatch({
        type: "notice_set",
        notice: "完成度已更新。"
      });
      return true;
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: `更新完成度失败：${String(error)}`
      });
      logWorkspaceError("workflow:plan_progress_update:error", error);
      return false;
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

  const answerPlanQuestion = async (input: {
    planId: string;
    questionId: string;
    answer: string;
  }) => {
    if (!input.planId || !input.questionId || !input.answer.trim()) {
      return false;
    }
    try {
      dispatch({ type: "busy_started" });
      const updatedPlan = await answerLearningPlanQuestion(input);
      dispatch({
        type: "plan_updated",
        plan: updatedPlan
      });
      dispatch({
        type: "notice_set",
        notice: "回答已保存，计划已更新。"
      });
      return true;
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: `保存回答失败：${String(error)}`
      });
      logWorkspaceError("workflow:plan_question_answer:error", error);
      return false;
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

  const applyChatExchange = (next: StudyChatResponse & { session: StudySessionRecord }) => {
    studySessionRef.current = next.session;
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

  const applyStudyChatOperation = (
    receipt: StudyChatOperationResponse,
    draft: StudyChatDraft,
  ): boolean => {
    const learnerOperation = draft.messageKind === "learner";
    if (receipt.status === "committed" && receipt.result) {
      const currentSession = studySessionRef.current;
      if (currentSession?.id !== receipt.sessionId) {
        setChatFailure({
          ...draft,
          detail: "本次回复已完成，但当前已切换到其他会话。请返回原会话查看结果。",
          operationStatus: "committed",
          canQuery: false,
          canResend: false,
          canRefreshSession: false,
        });
        if (learnerOperation) {
          clearPendingStudyOperation(receipt);
        }
        return false;
      }
      if (currentSession.revision <= receipt.result.session.revision) {
        applyChatExchange(receipt.result);
      }
      setChatFailure(null);
      if (learnerOperation) {
        clearPendingStudyOperation(receipt);
      }
      return true;
    }

    const presentation = presentStudyChatOperation(receipt);
    const canResend = presentation.canResend &&
      draft.messageKind === "learner" &&
      Boolean(draft.message.trim());
    setChatFailure({
      ...draft,
      detail: presentation.canResend && !canResend
        ? draft.messageKind === "learner"
          ? "已确认本次请求没有写入会话。刷新后原消息或附件不可恢复，请重新填写后再发送。"
          : "已确认这次自动消息没有写入会话；流程继续时会使用新的请求身份安全重试。"
        : presentation.detail,
      operationStatus: receipt.status,
      canQuery: presentation.canQuery,
      canResend,
      canRefreshSession: false,
    });
    if (learnerOperation) {
      if (receipt.status === "not_committed") {
        clearPendingStudyOperation(receipt);
      } else {
        persistPendingStudyOperation(draft);
      }
    }
    return false;
  };

  const queryStudyChatOperation = async () => {
    if (!chatFailure?.canQuery) {
      return false;
    }
    try {
      dispatch({ type: "busy_started" });
      const receipt = await getStudyChatOperation({
        sessionId: chatFailure.sessionId,
        clientRequestId: chatFailure.clientRequestId,
      });
      const applied = applyStudyChatOperation(receipt, chatFailure);
      if (applied) {
        dispatch({ type: "notice_set", notice: "已找回并载入本次回复。" });
      }
      return applied;
    } catch (error) {
      if (isMissingStudyChatOperationError(error)) {
        clearPendingStudyOperation(chatFailure);
        setChatFailure((current) => current ? {
          ...current,
          detail: "服务器确认没有找到这次请求。请刷新会话状态后重新发送。",
          canQuery: false,
          canResend: false,
          canRefreshSession: true,
        } : current);
        dispatch({
          type: "notice_set",
          notice: "没有找到这次请求；请先刷新会话状态。",
        });
        return false;
      }
      setChatFailure((current) => current ? {
        ...current,
        detail: "暂时无法确认本次请求结果。请稍后继续查询，不要重新发送。",
        canQuery: true,
        canResend: false,
        canRefreshSession: false,
      } : current);
      dispatch({
        type: "notice_set",
        notice: "暂时无法查询本次请求；已保留请求身份，请不要重复发送。",
      });
      logWorkspaceError("workflow:study_chat:operation_query_error", error);
      return false;
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

  useEffect(() => {
    const session = state.studySession;
    const pending = readPendingStudyOperation();
    if (
      !session ||
      !pending ||
      pending.sessionId !== session.id ||
      restoredStudyOperationRef.current === pending.clientRequestId
    ) {
      return;
    }
    restoredStudyOperationRef.current = pending.clientRequestId;
    const restoredDraft: StudyChatDraft = {
      ...pending,
      message: "",
      studyUnitId: pending.studyUnitId || session.studyUnitId,
      attachments: [],
      messageKind: pending.messageKind || "learner",
    };
    setChatFailure({
      ...restoredDraft,
      detail: "正在查询刷新前尚未确认的请求结果，请不要重新发送。",
      operationStatus: "unresolved",
      canQuery: true,
      canResend: false,
      canRefreshSession: false,
    });
    void (async () => {
      try {
        const receipt = await getStudyChatOperation(pending);
        applyStudyChatOperation(receipt, restoredDraft);
      } catch (error) {
        if (isMissingStudyChatOperationError(error)) {
          clearPendingStudyOperation(pending);
          setChatFailure((current) => current ? {
            ...current,
            detail: "服务器没有找到刷新前的请求。请刷新会话状态后重新发送。",
            canQuery: false,
            canResend: false,
            canRefreshSession: true,
          } : current);
          return;
        }
        setChatFailure((current) => current ? {
          ...current,
          detail: "尚未确认刷新前请求的结果。请点击“查询本次请求结果”，不要重新发送。",
          canQuery: true,
          canResend: false,
          canRefreshSession: false,
        } : current);
        logWorkspaceError("workflow:study_chat:operation_restore_error", error);
      }
    })();
  }, [state.studySession?.id]);

  const sendHiddenSessionMessage = async (input: {
    session: StudySessionRecord;
    clientRequestId: string;
    operationKey: string;
    queryExisting: boolean;
    message: string;
    messageKind: "session_prelude" | "scheduled_follow_up" | "interactive_callback";
    followUpId?: string;
  }) => {
    const draft: StudyChatDraft = {
      sessionId: input.session.id,
      clientRequestId: input.clientRequestId,
      expectedSessionRevision: input.session.revision,
      message: input.message,
      studyUnitId: input.session.studyUnitId,
      attachments: [],
      messageKind: input.messageKind,
      followUpId: input.followUpId,
    };
    persistPendingStudyOperation(draft);
    let next: StudyChatOperationResponse;
    try {
      next = input.queryExisting
        ? await getStudyChatOperation({
            sessionId: input.session.id,
            clientRequestId: input.clientRequestId,
          })
        : await sendStudyMessage({
            sessionId: input.session.id,
            clientRequestId: input.clientRequestId,
            expectedSessionRevision: input.session.revision,
            message: input.message,
            messageKind: input.messageKind,
            followUpId: input.followUpId,
          });
    } catch (error) {
      if (isDefiniteStudyChatPreAdmissionError(error)) {
        clearPendingStudyOperation(draft);
        forgetAutomaticStudyRequestId(
          automaticRequestIdsRef.current,
          input.operationKey,
        );
        setChatFailure({
          ...draft,
          detail: studyChatPreAdmissionNotice(error),
          operationStatus: "unresolved",
          canQuery: false,
          canResend: false,
          canRefreshSession: true,
        });
        throw error;
      }
      setChatFailure({
        ...draft,
        detail: "未能确认这次自动消息的结果。请查询本次请求，不要重复执行。",
        operationStatus: "unresolved",
        canQuery: true,
        canResend: false,
        canRefreshSession: false,
      });
      throw error;
    }
    if (next.status === "not_committed" && next.safeToRetry) {
      forgetAutomaticStudyRequestId(
        automaticRequestIdsRef.current,
        input.operationKey,
      );
    }
    if (!applyStudyChatOperation(next, draft)) {
      throw new Error(`study_chat_operation_${next.status}`);
    }
    return next;
  };

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

  const handleAsk = async (message: string, attachments: File[] = []) => {
    if (!state.studySession) {
      return false;
    }
    return handleAskForSection(message, state.studySession.studyUnitId, attachments);
  };

  const ensureSessionForSection = async (
    studyUnitId: string,
    options: { clearResponseOnSwitch?: boolean } = {}
  ): Promise<StudySessionRecord | null> => {
    if (!activePlan || !studyUnitId) {
      return null;
    }

    let workingSession = state.studySession;
    if (!workingSession) {
      workingSession = await fetchLatestSessionForPlan();
    }

    const activeSceneProfile = resolveActiveSceneProfile();
    if (!workingSession) {
      workingSession = await createStudySession({
        documentId: activeDocument?.id ?? activePlan.documentId ?? "",
        personaId: activePlan.personaId,
        planId: activePlan.id,
        sceneProfile: activeSceneProfile ?? null,
        studyUnitId,
        studyUnitTitle: resolveStudyUnitTitle(studyUnitId),
        themeHint: resolveThemeHintByStudyUnitId(studyUnitId),
      });
    } else if (workingSession.studyUnitId !== studyUnitId) {
      workingSession = await updateStudySessionStudyUnit({
        sessionId: workingSession.id,
        studyUnitId,
      });
    }

    dispatch({
      type: "study_session_set",
      studySession: workingSession,
      clearResponse: options.clearResponseOnSwitch ?? true,
    });
    studySessionRef.current = workingSession;
    return workingSession;
  };

  const handleAskForSection = async (message: string, studyUnitId: string, attachments: File[] = []) => {
    setChatFailure(null);
    let targetSession: StudySessionRecord | null;
    try {
      targetSession = await ensureSessionForSection(studyUnitId, {
        clearResponseOnSwitch: false,
      });
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: resolveStudySessionErrorNotice(
          error,
          `打开学习会话失败：${String(error)}`,
          "history",
        ),
      });
      logWorkspaceError("workflow:study_session:open_error", error);
      return false;
    }
    if (!targetSession) {
      return false;
    }
    const hiddenMessagePrefix =
      isDialogueInterruptedForSession(targetSession.id)
        ? peekDeferredInteractiveCallbackPrefix(targetSession.id)
        : "";
    const draft: StudyChatDraft = {
      sessionId: targetSession.id,
      clientRequestId: createStudyChatRequestId("learner"),
      expectedSessionRevision: targetSession.revision,
      message,
      studyUnitId,
      attachments,
      messageKind: "learner",
      hiddenMessagePrefix,
    };
    persistPendingStudyOperation(draft);
    try {
      dispatch({ type: "busy_started" });
      logWorkspaceInfo("workflow:study_chat:start", {
        sessionId: targetSession.id,
        messageLength: message.length
      });
      const next = await sendStudyMessage({
        sessionId: draft.sessionId,
        clientRequestId: draft.clientRequestId,
        expectedSessionRevision: draft.expectedSessionRevision,
        message: draft.message,
        messageKind: draft.messageKind,
        hiddenMessagePrefix: draft.hiddenMessagePrefix,
        attachments: draft.attachments,
      });
      const applied = applyStudyChatOperation(next, draft);
      if (!applied) {
        dispatch({
          type: "notice_set",
          notice: presentStudyChatOperation(next).detail,
        });
        return false;
      }
      clearInterruptedDialogueState(targetSession.id);
      logWorkspaceInfo("workflow:study_chat:done", {
        sessionId: targetSession.id,
        citations: next.result?.citations.length ?? 0,
        characterEvents: next.result?.characterEvents.length ?? 0,
      });
      return true;
    } catch (error) {
      if (isDefiniteStudyChatPreAdmissionError(error)) {
        clearPendingStudyOperation(draft);
        setChatFailure({
          ...draft,
          detail: studyChatPreAdmissionNotice(error),
          operationStatus: "unresolved",
          canQuery: false,
          canResend: false,
          canRefreshSession: true,
        });
        dispatch({
          type: "notice_set",
          notice: "消息尚未被服务端接收；请先刷新会话状态。",
        });
        logWorkspaceError("workflow:study_chat:pre_admission_rejected", error);
        return false;
      }
      setChatFailure({
        ...draft,
        detail: "未能确认本次请求结果。请查询本次请求，不要重新发送。",
        operationStatus: "unresolved",
        canQuery: true,
        canResend: false,
        canRefreshSession: false,
      });
      persistPendingStudyOperation(draft);
      dispatch({
        type: "notice_set",
        notice: "未能确认本次请求结果；已保留请求身份，请先查询，不要重复发送。",
      });
      logWorkspaceError("workflow:study_chat:error", error);
      return false;
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

  const handleSwitchSection = async (studyUnitId: string) => {
    try {
      dispatch({ type: "busy_started" });
      const beforeSessionId = state.studySession?.id ?? "";
      const nextSession = await ensureSessionForSection(studyUnitId, {
        clearResponseOnSwitch: true,
      });
      if (!nextSession) {
        return;
      }
      dispatch({
        type: "notice_set",
        notice:
          beforeSessionId === nextSession.id
            ? "已切换章节。"
            : "已切换章节，并打开对应会话。"
      });
      logWorkspaceInfo("workflow:study_session:section_switched", {
        sessionId: nextSession.id,
        studyUnitId: nextSession.studyUnitId
      });
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: resolveStudySessionErrorNotice(
          error,
          `切换章节失败：${String(error)}`,
          "update",
        )
      });
      logWorkspaceError("workflow:study_session:section_switch_error", error);
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

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
    if (preludeInFlightRef.current.has(requestKey)) {
      return false;
    }
    preludeInFlightRef.current.add(requestKey);
    try {
      dispatch({ type: "busy_started" });
      const operationKey = `prelude:${requestKey}:${input.session.revision}`;
      const operationIdentity = getOrCreateAutomaticRequestId(
        automaticRequestIdsRef.current,
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
      const operationIdentity = getOrCreateAutomaticRequestId(
        automaticRequestIdsRef.current,
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
    const currentSession = studySessionRef.current;
    if (!currentSession) {
      return false;
    }
    const attemptKey = `attempt:${currentSession.id}:${input.turnId}`;
    const attemptIdentity = getOrCreateAutomaticRequestId(
      automaticRequestIdsRef.current,
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
      const latestSession = studySessionRef.current;
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
        studySessionRef.current = nextSession;
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
      forgetAutomaticStudyRequestId(
        automaticRequestIdsRef.current,
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
    if (!state.studySession) {
      return false;
    }
    try {
      dispatch({ type: "busy_started" });
      const next = await resolveStudyPlanConfirmation({
        sessionId: state.studySession.id,
        confirmationId: input.confirmationId,
        decision: input.decision,
        note: input.note,
      });
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
    const session = state.studySession;
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
    try {
      dispatch({ type: "busy_started" });
      const nextSession = await cancelStudySessionFollowUps({
        sessionId: session.id,
      });
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
    let active = true;
    const load = async () => {
      try {
        dispatch({ type: "snapshot_refresh_started" });
        const snapshot = await readWorkspaceSnapshot(true);
        if (!active) {
          return;
        }
        applyWorkspaceSnapshot(snapshot, selectedPlanIdRef.current);
        dispatch({
          type: "notice_set",
          notice: CONNECTED_NOTICE
        });
      } catch (error) {
        if (active) {
          dispatch({
            type: "notice_set",
            notice: resolveStudySessionErrorNotice(
              error,
              DISCONNECTED_NOTICE,
              "history",
            ),
          });
        }
        logWorkspaceError("workflow:workspace_snapshot:load_error", error);
      } finally {
        if (active) {
          dispatch({ type: "snapshot_refresh_finished" });
        }
      }
    };
    void load();

    return () => {
      active = false;
    };
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
        preferredPlanId: state.selectedPlanId
      });
      void refreshPersonaLibrary();
      void refreshSceneLibrary();
    };
    window.addEventListener("focus", handleFocus);
    return () => {
      window.removeEventListener("focus", handleFocus);
    };
  }, [state.selectedPlanId]);

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
    let active = true;
    const hydrateSessions = async () => {
      // Goal-only plans intentionally have no bound document, but they still
      // own study sessions that should be restored on desktop app relaunch.
      if (!activePlan) {
        return;
      }
      try {
        const latest = await fetchLatestSessionForPlan();
        if (!active) {
          return;
        }
        dispatch({
          type: "study_session_set",
          studySession: latest,
          clearResponse: true,
        });
      } catch (error) {
        const notice = resolveStudySessionErrorNotice(error, "", "history");
        if (active && notice) {
          dispatch({
            type: "notice_set",
            notice,
          });
        }
        logWorkspaceError("workflow:study_session:hydrate_error", error);
      }
    };
    void hydrateSessions();
    return () => {
      active = false;
    };
  }, [activeDocument?.id, activePlan?.id, activePlan?.personaId]);

  useEffect(() => {
    if (!state.studySession) {
      return;
    }
    const session = state.studySession;
    const studyUnitId = session.studyUnitId;
    if (!studyUnitId || state.isBusy) {
      return;
    }
    void runSessionPrelude({
      session,
      studyUnitId,
      sectionTitle: session.studyUnitTitle ?? session.studyUnitId,
      themeHint: session.themeHint ?? "",
      force: false,
    });
  }, [state.isBusy, state.studySession]);

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
              const operationIdentity = getOrCreateAutomaticRequestId(
                automaticRequestIdsRef.current,
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
  }, [state.isBusy, state.studySession]);

  useEffect(() => {
    return () => {
      const timers = followUpTimerRef.current;
      Array.from(timers.values()).forEach((timer) => window.clearTimeout(timer));
      timers.clear();
    };
  }, []);

  const retryFailedAsk = async () => {
    if (!chatFailure?.canResend) {
      return;
    }
    await handleAskForSection(chatFailure.message, chatFailure.studyUnitId, chatFailure.attachments);
  };

  const refreshStudySessionAfterRejectedAdmission = async () => {
    const failure = chatFailure;
    const currentSession = studySessionRef.current;
    if (!failure?.canRefreshSession || !currentSession) {
      return false;
    }
    try {
      dispatch({ type: "busy_started" });
      const sessions = await listStudySessions({
        documentId: currentSession.planId ? undefined : currentSession.documentId,
        planId: currentSession.planId ?? undefined,
        personaId: currentSession.personaId,
        studyUnitId: currentSession.studyUnitId,
      });
      const refreshed = sessions.find((item) => item.id === currentSession.id) ?? null;
      clearPendingStudyOperation(failure);
      setChatFailure(null);
      if (!refreshed) {
        studySessionRef.current = null;
        dispatch({
          type: "study_session_set",
          studySession: null,
          clearResponse: true,
        });
        dispatch({
          type: "notice_set",
          notice: "原学习会话已不存在。请先创建或选择会话，再重新发送保留的草稿。",
        });
        return false;
      }
      studySessionRef.current = refreshed;
      dispatch({
        type: "study_session_set",
        studySession: refreshed,
        clearResponse: false,
      });
      dispatch({
        type: "notice_set",
        notice: "会话状态已刷新。请确认草稿后重新发送；新发送会使用新的请求身份。",
      });
      return true;
    } catch (error) {
      setChatFailure((current) => current ? {
        ...current,
        detail: "刷新会话状态失败，草稿仍保留。请稍后重试刷新。",
        canQuery: false,
        canResend: false,
        canRefreshSession: true,
      } : current);
      dispatch({ type: "notice_set", notice: "刷新会话状态失败，草稿仍保留。" });
      logWorkspaceError("workflow:study_chat:refresh_after_rejection_error", error);
      return false;
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

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
    isBusy: state.isBusy,
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

function resolveStreamStatus(stage: string) {
  if (stage === "stream_completed") {
    return "completed";
  }
  if (stage === "stream_cancelled") {
    return "cancelled";
  }
  if (stage === "stream_error") {
    return "error";
  }
  return "running";
}

function isAbortLikeError(error: unknown) {
  if (error instanceof DOMException && error.name === "AbortError") {
    return true;
  }
  return String(error).includes("stream_interrupted");
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

function createStudyChatRequestId(scope: string): string {
  const normalizedScope = scope.toLowerCase().replace(/[^a-z0-9-]+/g, "-").slice(0, 20) || "chat";
  const suffix = typeof globalThis.crypto?.randomUUID === "function"
    ? globalThis.crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `study-${normalizedScope}-${suffix}`.slice(0, 80);
}

function getOrCreateAutomaticRequestId(
  requests: Map<string, string>,
  key: string,
  scope: string,
): { clientRequestId: string; queryExisting: boolean } {
  const existing = requests.get(key);
  if (existing) {
    return { clientRequestId: existing, queryExisting: true };
  }
  const persisted = readAutomaticStudyRequestIds();
  const persistedId = persisted[key];
  if (persistedId) {
    requests.set(key, persistedId);
    return { clientRequestId: persistedId, queryExisting: true };
  }
  const created = createStudyChatRequestId(scope);
  requests.set(key, created);
  persistAutomaticStudyRequestId(key, created, persisted);
  return { clientRequestId: created, queryExisting: false };
}

function forgetAutomaticStudyRequestId(requests: Map<string, string>, key: string): void {
  requests.delete(key);
  if (typeof window === "undefined") {
    return;
  }
  try {
    const persisted = readAutomaticStudyRequestIds();
    delete persisted[key];
    window.localStorage.setItem(
      AUTOMATIC_STUDY_REQUEST_STORAGE_KEY,
      JSON.stringify(persisted),
    );
  } catch {
    // A fresh page may rediscover the terminal receipt before creating a new request.
  }
}

function readAutomaticStudyRequestIds(): Record<string, string> {
  if (typeof window === "undefined") {
    return {};
  }
  try {
    const raw = window.localStorage.getItem(AUTOMATIC_STUDY_REQUEST_STORAGE_KEY);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    return Object.fromEntries(
      Object.entries(parsed).filter((entry): entry is [string, string] =>
        Boolean(entry[0] && typeof entry[1] === "string" && entry[1].trim())
      ),
    );
  } catch {
    return {};
  }
}

function persistAutomaticStudyRequestId(
  key: string,
  requestId: string,
  current: Record<string, string>,
): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    const entries = Object.entries({ ...current, [key]: requestId }).slice(-64);
    window.localStorage.setItem(
      AUTOMATIC_STUDY_REQUEST_STORAGE_KEY,
      JSON.stringify(Object.fromEntries(entries)),
    );
  } catch {
    // The mounted controller Map still preserves identity for this page lifetime.
  }
}

function presentStudyChatOperation(receipt: StudyChatOperationResponse): {
  detail: string;
  canQuery: boolean;
  canResend: boolean;
} {
  switch (receipt.status) {
    case "admitted":
      return {
        detail: "本次请求已接收，尚未开始生成。请查询本次请求结果，不要重新发送。",
        canQuery: true,
        canResend: false,
      };
    case "running":
      return {
        detail: "本次回复仍在生成。请稍后查询本次请求结果，不要重新发送。",
        canQuery: true,
        canResend: false,
      };
    case "uncertain":
      return {
        detail: "系统暂时无法确认本次请求是否已产生影响。请继续查询，不要重新发送。",
        canQuery: true,
        canResend: false,
      };
    case "not_committed":
      return {
        detail: receipt.safeToRetry
          ? "已确认本次请求没有写入会话。你可以重新发送，新发送会使用新的请求身份。"
          : "本次请求未写入会话，但当前不允许重新发送。",
        canQuery: false,
        canResend: receipt.safeToRetry,
      };
    case "committed":
      return { detail: "本次回复已完成。", canQuery: false, canResend: false };
  }
}

function persistPendingStudyOperation(operation: PendingStudyOperationIdentity): void {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(
      PENDING_STUDY_OPERATION_STORAGE_KEY,
      JSON.stringify({
        sessionId: operation.sessionId,
        clientRequestId: operation.clientRequestId,
        expectedSessionRevision: operation.expectedSessionRevision,
        messageKind: operation.messageKind,
        studyUnitId: operation.studyUnitId,
      }),
    );
  } catch {
    // Recovery remains available for this mounted page even when storage is unavailable.
  }
}

function readPendingStudyOperation(): PendingStudyOperationIdentity | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    const raw = window.localStorage.getItem(PENDING_STUDY_OPERATION_STORAGE_KEY);
    if (!raw) {
      return null;
    }
    const value = JSON.parse(raw) as Record<string, unknown>;
    if (
      typeof value.sessionId !== "string" ||
      !value.sessionId.trim() ||
      typeof value.clientRequestId !== "string" ||
      !value.clientRequestId.trim() ||
      !Number.isSafeInteger(value.expectedSessionRevision) ||
      Number(value.expectedSessionRevision) < 0
    ) {
      return null;
    }
    return {
      sessionId: value.sessionId,
      clientRequestId: value.clientRequestId,
      expectedSessionRevision: Number(value.expectedSessionRevision),
      messageKind: typeof value.messageKind === "string" ? value.messageKind : undefined,
      studyUnitId: typeof value.studyUnitId === "string" ? value.studyUnitId : undefined,
    };
  } catch {
    return null;
  }
}

function clearPendingStudyOperation(operation: Pick<PendingStudyOperationIdentity, "sessionId" | "clientRequestId">): void {
  if (typeof window === "undefined") {
    return;
  }
  const pending = readPendingStudyOperation();
  if (
    pending?.sessionId !== operation.sessionId ||
    pending.clientRequestId !== operation.clientRequestId
  ) {
    return;
  }
  try {
    window.localStorage.removeItem(PENDING_STUDY_OPERATION_STORAGE_KEY);
  } catch {
    // Ignore storage failures after the in-memory state has already converged.
  }
}
