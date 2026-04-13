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
  answerLearningPlanQuestion,
  createLearningPlanStream,
  deleteLearningPlan as deleteLearningPlanRequest,
  createStudySession,
  listStudySessions,
  listSceneLibrary,
  listDocuments,
  listLearningPlans,
  listPersonas,
  processDocumentStream,
  resolveStudyPlanConfirmation,
  sendStudyMessage,
  submitStudyQuestionAttempt,
  type SceneLibraryItemPayload,
  updateDocumentStudyUnitTitle as updateDocumentStudyUnitTitleRequest,
  updateLearningPlanProgress as updateLearningPlanProgressRequest,
  updateLearningPlanStudyChapters as updateLearningPlanStudyChaptersRequest,
  updateLearningPlanTitle as updateLearningPlanTitleRequest,
  updateStudySessionSection,
  uploadDocument
} from "../lib/api";
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
import { readSceneProfileFromLocalStorage } from "../lib/scene-profile";
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
import {
  logWorkspaceError,
  logWorkspaceInfo
} from "../lib/learning-workspace-telemetry";
import { compactPreviewValue } from "../lib/preview";
import { useRuntimeSettings } from "../components/runtime-settings-provider";

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
  sectionId: string;
  detail: string;
  attachments: File[];
};

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
  const [processStreamEvents, setProcessStreamEvents] = useState<StreamEventItem[]>([]);
  const [planStreamEvents, setPlanStreamEvents] = useState<StreamEventItem[]>([]);
  const [processStreamStatus, setProcessStreamStatus] = useState("idle");
  const [planStreamStatus, setPlanStreamStatus] = useState("idle");
  const [processStreamDocumentId, setProcessStreamDocumentId] = useState("");
  const [planStreamDocumentId, setPlanStreamDocumentId] = useState("");
  const [chatFailure, setChatFailure] = useState<ChatFailureState | null>(null);
  const [sceneLibraryItems, setSceneLibraryItems] = useState<SceneLibraryItemPayload[]>([]);
  const [selectedSceneLibraryId, setSelectedSceneLibraryId] = useState("");
  const preludeInFlightRef = useRef<Set<string>>(new Set());
  const followUpTimerRef = useRef<Map<string, number>>(new Map());
  const followUpInFlightRef = useRef<Set<string>>(new Set());

  const selectedPersona =
    state.personas.find((persona) => persona.id === state.selectedPersonaId) ?? state.personas[0];
  const activePlan = findLearningPlan(state.planHistory, state.selectedPlanId);
  const activeDocument = findDocumentForPlan(activePlan, state.documents);
  const planSections = buildPlanDirectorySections(activePlan, activeDocument);
  const planHistoryItems = buildPlanHistoryItems({
    plans: state.planHistory,
    documents: state.documents,
    personas: state.personas
  });
  const activeSection =
    planSections.find((section) => section.id === state.studySession?.sectionId) ??
    planSections[0] ??
    null;
  const selectedSceneProfile = useMemo(
    () => resolveSceneProfileFromLibrary(sceneLibraryItems, selectedSceneLibraryId),
    [sceneLibraryItems, selectedSceneLibraryId]
  );

  const resolveActiveSceneProfile = () => selectedSceneProfile ?? readSceneProfileFromLocalStorage();

  const resolveSectionTitle = (sectionId: string) => {
    const sectionFromPlan = planSections.find((section) => section.id === sectionId);
    if (sectionFromPlan?.title) {
      return sectionFromPlan.title;
    }
    const sectionFromDocument = activeDocument?.sections.find((section) => section.id === sectionId);
    if (sectionFromDocument?.title) {
      return sectionFromDocument.title;
    }
    return sectionId;
  };

  const resolveThemeHintBySectionId = (sectionId: string) => {
    if (!activePlan) {
      return "";
    }
    const chapterProgress = activePlan.chapterProgress.find((item) => item.unitId === sectionId);
    if (chapterProgress?.objectiveFragment?.trim()) {
      return chapterProgress.objectiveFragment.trim();
    }
    const scheduleItem = activePlan.schedule.find((item) => item.unitId === sectionId);
    if (scheduleItem?.focus) {
      return scheduleItem.focus;
    }
    const containingUnit = activePlan.studyUnits.find((unit) =>
      unit.id === sectionId ||
      unit.sourceSectionIds.includes(sectionId) ||
      (
        activeDocument?.sections.some((section) =>
          section.id === sectionId &&
          Math.max(unit.pageStart, section.pageStart) <= Math.min(unit.pageEnd, section.pageEnd)
        ) ?? false
      )
    );
    if (containingUnit) {
      const containingSchedule = activePlan.schedule.find((item) => item.unitId === containingUnit.id);
      if (containingSchedule?.focus) {
        return containingSchedule.focus;
      }
      const containingIndex = (activePlan.studyUnits.filter((unit) => unit.includeInPlan) || []).findIndex(
        (unit) => unit.id === containingUnit.id
      );
      if (containingIndex >= 0 && activePlan.studyChapters[containingIndex]) {
        return activePlan.studyChapters[containingIndex];
      }
    }
    const sectionIndex = planSections.findIndex((section) => section.id === sectionId);
    if (sectionIndex >= 0 && activePlan.studyChapters[sectionIndex]) {
      return activePlan.studyChapters[sectionIndex];
    }
    return activePlan.studyChapters[0] ?? "";
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

  const applyWorkspaceSnapshot = (
    snapshot: WorkspaceSnapshot,
    preferredPlanId: string
  ) => {
    const nextState = resolveWorkspaceSnapshot({
      snapshot,
      preferredPlanId,
      currentSelectedPlanId: state.selectedPlanId,
      currentSelectedPersonaId: state.selectedPersonaId
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
      sectionId: nextSession.sectionId
    });
    return nextSession;
  };

  const generatePlanWorkflow = async (input: GeneratePlanInput) => {
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

        const uploadedDocument = await uploadDocument(input.file);
        setProcessStreamDocumentId(uploadedDocument.id);
        setPlanStreamDocumentId(uploadedDocument.id);
        dispatch({
          type: "notice_set",
          notice: "教材已上传，正在解析内容与章节结构。"
        });
        logWorkspaceInfo("workflow:upload:document_uploaded", {
          documentId: uploadedDocument.id,
          status: uploadedDocument.status
        });

        nextDocument = await processDocumentStream(
          uploadedDocument.id,
          {},
          (event) => {
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
              notice: `教材处理中: ${event.stage}`
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
          notice: "教材解析完成，正在生成学习计划。"
        });
      } else {
        setProcessStreamDocumentId("");
        setPlanStreamDocumentId("");
        dispatch({
          type: "notice_set",
          notice: "正在根据学习目标生成计划骨架。"
        });
        logWorkspaceInfo("workflow:goal_only:start", {
          personaId: selectedPersona.id,
          objectiveLength: input.objective.length
        });
      }

      setPlanStreamStatus("running");
      const nextPlan = await createLearningPlanStream(
        {
          documentId: nextDocument?.id ?? "",
          personaId: selectedPersona.id,
          objective: input.objective,
          sceneProfileSummary: sceneProfile?.summary ?? "",
          sceneProfile,
        },
        (event) => {
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
            notice: `学习计划处理中: ${event.stage}`
          });
          logWorkspaceInfo("workflow:plan_event", {
            documentId: nextDocument?.id ?? "",
            stage: event.stage,
            ...event.payload
          });
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
              ? "目标计划已生成，并已创建首个学习会话。"
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
      setProcessStreamStatus((current) => (current === "running" ? "error" : current));
      setPlanStreamStatus((current) => (current === "running" ? "error" : current));
      dispatch({
        type: "notice_set",
        notice: `${input.mode === "document" ? "教材处理失败" : "目标计划生成失败"}: ${String(error)}`
      });
      logWorkspaceError("workflow:upload:error", error);
    } finally {
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
        notice: `创建学习会话失败: ${String(error)}`
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
        notice: "已更新计划题目。"
      });
      return true;
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: `更新计划题目失败: ${String(error)}`
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
        notice: "已删除学习计划。"
      });
      return true;
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: `删除学习计划失败: ${String(error)}`
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
        notice: "已更新学习单元标题。"
      });
      return true;
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: `更新学习单元标题失败: ${String(error)}`
      });
      logWorkspaceError("workflow:study_unit_title_update:error", error);
      return false;
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

  const updatePlanStudyChapters = async (planId: string, studyChapters: string[]) => {
    const normalizedChapters = studyChapters.map((item) => item.trim()).filter(Boolean);
    if (!planId || !normalizedChapters.length) {
      return false;
    }
    try {
      dispatch({ type: "busy_started" });
      const updatedPlan = await updateLearningPlanStudyChaptersRequest(planId, normalizedChapters);
      dispatch({
        type: "plan_updated",
        plan: updatedPlan
      });
      dispatch({
        type: "notice_set",
        notice: "已更新学习章节。"
      });
      return true;
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: `更新学习章节失败: ${String(error)}`
      });
      logWorkspaceError("workflow:plan_study_chapters_update:error", error);
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
        notice: "已更新计划完成度。"
      });
      return true;
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: `更新计划完成度失败: ${String(error)}`
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
        notice: "已保存规划问题回答，并按最新反馈刷新了学习计划。"
      });
      return true;
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: `保存规划问题回答失败: ${String(error)}`
      });
      logWorkspaceError("workflow:plan_question_answer:error", error);
      return false;
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

  const applyChatExchange = (next: StudyChatResponse & { session: StudySessionRecord }) => {
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

  const sendHiddenSessionMessage = async (input: {
    sessionId: string;
    message: string;
    messageKind: "session_prelude" | "scheduled_follow_up" | "interactive_callback";
    followUpId?: string;
  }) => {
    const next = await sendStudyMessage({
      sessionId: input.sessionId,
      message: input.message,
      messageKind: input.messageKind,
      followUpId: input.followUpId,
    });
    applyChatExchange(next);
    return next;
  };

  const handleAsk = async (message: string, attachments: File[] = []) => {
    if (!state.studySession) {
      return;
    }
    await handleAskForSection(message, state.studySession.sectionId, attachments);
  };

  const ensureSessionForSection = async (
    sectionId: string,
    options: { clearResponseOnSwitch?: boolean } = {}
  ): Promise<StudySessionRecord | null> => {
    if (!activePlan || !sectionId) {
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
        sectionId,
        sectionTitle: resolveSectionTitle(sectionId),
        themeHint: resolveThemeHintBySectionId(sectionId),
      });
    } else if (workingSession.sectionId !== sectionId) {
      workingSession = await updateStudySessionSection({
        sessionId: workingSession.id,
        sectionId,
      });
    }

    dispatch({
      type: "study_session_set",
      studySession: workingSession,
      clearResponse: options.clearResponseOnSwitch ?? true,
    });
    return workingSession;
  };

  const handleAskForSection = async (message: string, sectionId: string, attachments: File[] = []) => {
    setChatFailure(null);
    const targetSession = await ensureSessionForSection(sectionId, {
      clearResponseOnSwitch: false,
    });
    if (!targetSession) {
      return;
    }
    try {
      dispatch({ type: "busy_started" });
      logWorkspaceInfo("workflow:study_chat:start", {
        sessionId: targetSession.id,
        messageLength: message.length
      });
      const next = await sendStudyMessage({
        sessionId: targetSession.id,
        message,
        messageKind: "learner",
        attachments,
      });
      applyChatExchange(next);
      logWorkspaceInfo("workflow:study_chat:done", {
        sessionId: targetSession.id,
        citations: next.citations.length,
        characterEvents: next.characterEvents.length
      });
    } catch (error) {
      const detail = String(error);
      if (detail.includes("session_not_found")) {
        try {
          dispatch({
            type: "notice_set",
            notice: "会话已失效，正在自动重建并重试…"
          });
          if (!activePlan) {
            throw new Error("active_plan_missing");
          }
          const recoveredSession = await createStudySession({
            documentId: activeDocument?.id ?? activePlan.documentId ?? "",
            personaId: activePlan.personaId,
            planId: activePlan.id,
            sceneProfile: resolveActiveSceneProfile(),
            sectionId,
            sectionTitle: resolveSectionTitle(sectionId),
            themeHint: resolveThemeHintBySectionId(sectionId),
          });
          dispatch({
            type: "study_session_set",
            studySession: recoveredSession,
            clearResponse: false,
          });

          const recovered = await sendStudyMessage({
            sessionId: recoveredSession.id,
            message,
            messageKind: "learner",
            attachments,
          });
          applyChatExchange(recovered);
          dispatch({
            type: "notice_set",
            notice: "会话已恢复，已继续当前章节对话。"
          });
          return;
        } catch (recoveryError) {
          dispatch({
            type: "notice_set",
            notice: `会话恢复失败: ${String(recoveryError)}`
          });
          logWorkspaceError("workflow:study_chat:session_recover_error", recoveryError);
          return;
        }
      }
      if (detail.includes("chat_model_invalid_payload")) {
        setChatFailure({
          message,
          sectionId,
          detail,
          attachments,
        });
        dispatch({
          type: "notice_set",
          notice: "模型输出格式异常，请点击“重试发送”再次请求。"
        });
        return;
      }
      setChatFailure({
        message,
        sectionId,
        detail,
        attachments,
      });
      dispatch({
        type: "notice_set",
        notice: `导学请求失败: ${String(error)}`
      });
      logWorkspaceError("workflow:study_chat:error", error);
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

  const handleSwitchSection = async (sectionId: string) => {
    try {
      dispatch({ type: "busy_started" });
      const beforeSessionId = state.studySession?.id ?? "";
      const nextSession = await ensureSessionForSection(sectionId, {
        clearResponseOnSwitch: true,
      });
      if (!nextSession) {
        return;
      }
      dispatch({
        type: "notice_set",
        notice:
          beforeSessionId === nextSession.id
            ? `已切换到章节 ${sectionId}。`
            : `已切换到章节 ${sectionId}，并定位到对应会话。`
      });
      logWorkspaceInfo("workflow:study_session:section_switched", {
        sessionId: nextSession.id,
        sectionId: nextSession.sectionId
      });
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: `切换章节失败: ${String(error)}`
      });
      logWorkspaceError("workflow:study_session:section_switch_error", error);
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

  const handleSubmitQuestionAttempt = async (input: {
    questionType: "multiple_choice" | "fill_blank";
    prompt: string;
    topic: string;
    difficulty: "easy" | "medium" | "hard";
    options: Array<{ key: string; text: string }>;
    callBack?: boolean;
    answerKey?: string;
    acceptedAnswers: string[];
    submittedAnswer: string;
    isCorrect: boolean;
    explanation: string;
  }) => {
    if (!state.studySession) {
      return;
    }
    try {
      const nextSession = await submitStudyQuestionAttempt({
        sessionId: state.studySession.id,
        ...input
      });
      dispatch({
        type: "study_session_set",
        studySession: nextSession,
        clearResponse: false
      });
      if (input.callBack) {
        try {
          dispatch({ type: "busy_started" });
          await sendHiddenSessionMessage({
            sessionId: nextSession.id,
            message: buildInteractiveCallbackMessage(input),
            messageKind: "interactive_callback",
          });
        } catch (callbackError) {
          dispatch({
            type: "notice_set",
            notice: `答案已记录，但自动续问失败: ${String(callbackError)}`
          });
          logWorkspaceError("workflow:study_attempt:callback_error", callbackError);
        } finally {
          dispatch({ type: "busy_finished" });
        }
      }
    } catch (error) {
      const detail = String(error);
      if (detail.includes("session_not_found")) {
        try {
          dispatch({ type: "busy_started" });
          dispatch({
            type: "notice_set",
            notice: "答题会话已失效，正在自动重建…"
          });
          const recoveredSession = await ensureSessionForSection(state.studySession.sectionId, {
            clearResponseOnSwitch: false,
          });
          if (!recoveredSession) {
            throw new Error("session_recovery_unavailable");
          }
          const nextSession = await submitStudyQuestionAttempt({
            sessionId: recoveredSession.id,
            ...input
          });
          dispatch({
            type: "study_session_set",
            studySession: nextSession,
            clearResponse: false
          });
          dispatch({
            type: "notice_set",
            notice: "已恢复答题会话并写入记录。"
          });
          return;
        } catch (recoveryError) {
          dispatch({
            type: "notice_set",
            notice: `答题会话恢复失败: ${String(recoveryError)}`
          });
          logWorkspaceError("workflow:study_attempt:session_recover_error", recoveryError);
          return;
        } finally {
          dispatch({ type: "busy_finished" });
        }
      }
      dispatch({
        type: "notice_set",
        notice: `写入答题记录失败: ${String(error)}`
      });
      logWorkspaceError("workflow:study_attempt:error", error);
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
        notice: input.decision === "approve" ? "已确认并应用计划变更。" : "已拒绝本次计划变更。",
      });
      return true;
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: `处理计划确认失败: ${String(error)}`,
      });
      logWorkspaceError("workflow:study_plan_confirmation:error", error);
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
        applyWorkspaceSnapshot(snapshot, state.selectedPlanId);
        dispatch({
          type: "notice_set",
          notice: CONNECTED_NOTICE
        });
      } catch {
        if (active) {
          dispatch({ type: "notice_set", notice: DISCONNECTED_NOTICE });
        }
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
      void refreshSceneLibrary();
    };
    window.addEventListener("focus", handleFocus);
    return () => {
      window.removeEventListener("focus", handleFocus);
    };
  }, [state.selectedPlanId]);

  useEffect(() => {
    let active = true;
    const hydrateSessions = async () => {
      if (!activePlan || !activeDocument) {
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
    const sectionId = session.sectionId;
    if (!sectionId || session.preparedSectionIds?.includes(sectionId) || state.isBusy) {
      return;
    }
    const requestKey = `${session.id}:${sectionId}`;
    if (preludeInFlightRef.current.has(requestKey)) {
      return;
    }
    preludeInFlightRef.current.add(requestKey);
    void (async () => {
      try {
        dispatch({ type: "busy_started" });
        await sendHiddenSessionMessage({
          sessionId: session.id,
          message: buildSessionPreludeMessage({
            sectionTitle: session.sectionTitle ?? session.sectionId,
            themeHint: session.themeHint ?? "",
          }),
          messageKind: "session_prelude",
        });
      } catch (error) {
        dispatch({
          type: "notice_set",
          notice: `章节预处理失败: ${String(error)}`,
        });
        logWorkspaceError("workflow:study_session:prelude_error", error);
      } finally {
        preludeInFlightRef.current.delete(requestKey);
        dispatch({ type: "busy_finished" });
      }
    })();
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
              await sendHiddenSessionMessage({
                sessionId: session.id,
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
                notice: `自动续接失败: ${String(error)}`,
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
    if (!chatFailure) {
      return;
    }
    await handleAskForSection(chatFailure.message, chatFailure.sectionId, chatFailure.attachments);
  };

  return {
    personas: state.personas,
    selectedPersona,
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
    selectPlan,
    createSessionForActivePlan,
    renamePlanTitle,
    updatePlanStudyChapters,
    updatePlanProgress,
    answerPlanQuestion,
    renameStudyUnitTitle,
    removePlan,
    handleSwitchSection,
    handleAsk,
    handleAskForSection,
    chatFailure,
    retryFailedAsk,
    handleSubmitQuestionAttempt,
    handleResolvePlanConfirmation,
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
  if (stage === "stream_error") {
    return "error";
  }
  return "running";
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
    "正式对话开始前，请先完成一轮隐藏的章节预处理和自然引入。",
    `当前章节：${input.sectionTitle || "未命名章节"}`,
    `当前主题：${input.themeHint || "未额外指定"}`,
    "要求：",
    "1. 如果需要，可先调用计划、场景、教材或时间相关工具，确认当前上下文。",
    "2. 用 2 到 4 句自然地把学习者带入这一章，说明你准备如何陪他学。",
    "3. 如果场景、物体、教材页码或公式焦点有帮助，可以顺手把它们纳入引入。",
    "4. 不要提到这是隐藏消息、预处理消息或内部流程。"
  ].join("\n");
}
