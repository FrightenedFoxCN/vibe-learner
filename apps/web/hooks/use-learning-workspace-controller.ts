"use client";

import { useState } from "react";
import { useEffect, useReducer } from "react";
import type {
  DocumentRecord,
  DocumentSection,
  LearningPlan,
  PersonaProfile,
  StudyChatResponse,
  StudySessionRecord
} from "@gal-learner/shared";

import {
  createLearningPlanStream,
  createStudySession,
  listStudySessions,
  listDocuments,
  listLearningPlans,
  listPersonas,
  processDocumentStream,
  sendStudyMessage,
  submitStudyQuestionAttempt,
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

export interface GeneratePlanInput {
  file: File;
  objective: string;
}

type StreamEventItem = {
  stage: string;
  payload: Record<string, unknown>;
};

interface UseLearningWorkspaceControllerOptions {
  initialPlan?: LearningPlan;
  initialPersonas?: PersonaProfile[];
}

export function useLearningWorkspaceController({
  initialPlan,
  initialPersonas = mockPersonas
}: UseLearningWorkspaceControllerOptions) {
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
  const [sessionRegistry, setSessionRegistry] = useState<Record<string, StudySessionRecord>>({});

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
    const scheduleItem = activePlan.schedule.find((item) => item.unitId === sectionId);
    if (scheduleItem?.focus) {
      return scheduleItem.focus;
    }
    const sectionIndex = planSections.findIndex((section) => section.id === sectionId);
    if (sectionIndex >= 0 && activePlan.weeklyFocus[sectionIndex]) {
      return activePlan.weeklyFocus[sectionIndex];
    }
    return activePlan.weeklyFocus[0] ?? "";
  };

  const buildSessionRegistryKey = (planId: string, sectionId: string) => `${planId || "no-plan"}:${sectionId}`;

  const registerSession = (session: StudySessionRecord, planIdOverride?: string) => {
    const key = buildSessionRegistryKey(planIdOverride ?? state.selectedPlanId, session.sectionId);
    setSessionRegistry((current) => ({
      ...current,
      [key]: session,
    }));
  };

  const registerSessions = (sessions: StudySessionRecord[], planIdOverride?: string) => {
    if (!sessions.length) {
      return;
    }
    setSessionRegistry((current) => {
      const next = { ...current };
      for (const session of sessions) {
        const key = buildSessionRegistryKey(planIdOverride ?? state.selectedPlanId, session.sectionId);
        const existing = next[key];
        if (!existing || existing.updatedAt < session.updatedAt) {
          next[key] = session;
        }
      }
      return next;
    });
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
      personaId: nextPlan.personaId,
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
    document: DocumentRecord;
    personaId: string;
  }): Promise<StudySessionRecord> => {
    const nextSession = await createStudySession(
      buildInitialStudySessionInput(input)
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
    setProcessStreamStatus("running");
    setPlanStreamStatus("idle");
    try {
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

      const nextDocument = await processDocumentStream(
        uploadedDocument.id,
        {},
        (event) => {
          setProcessStreamEvents((current) => [...current.slice(-79), event]);
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
      setPlanStreamStatus("running");
      const nextPlan = await createLearningPlanStream(
        {
          documentId: nextDocument.id,
          personaId: selectedPersona.id,
          objective: input.objective
        },
        (event) => {
          setPlanStreamEvents((current) => [...current.slice(-119), event]);
          setPlanStreamStatus(resolveStreamStatus(event.stage));
          dispatch({
            type: "notice_set",
            notice: `学习计划处理中: ${event.stage}`
          });
          logWorkspaceInfo("workflow:upload:plan_event", {
            documentId: nextDocument.id,
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
          document: nextDocument,
          personaId: selectedPersona.id
        });
        dispatch({
          type: "study_session_set",
          studySession: nextSession,
          clearResponse: true
        });
        registerSession(nextSession, nextPlan.id);
        dispatch({
          type: "notice_set",
          notice: PLAN_GENERATED_NOTICE
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
        notice: `教材处理失败: ${String(error)}`
      });
      logWorkspaceError("workflow:upload:error", error);
    } finally {
      dispatch({ type: "busy_finished" });
      setIsGeneratingPlan(false);
    }
  };

  const createSessionForActivePlan = async () => {
    if (!activePlan || !activeDocument) {
      return;
    }
    try {
      dispatch({ type: "busy_started" });
      const nextSession = await createStudySession(
        {
          ...buildInitialStudySessionInput({
            document: activeDocument,
            personaId: activePlan.personaId
          }),
          sectionTitle: resolveSectionTitle(
            planSections[0]?.id ??
              activeDocument.sections[0]?.id ??
              `${activeDocument.id}:intro`
          ),
          themeHint: activePlan.weeklyFocus[0] ?? "",
          sectionId:
            planSections[0]?.id ??
            activeDocument.sections[0]?.id ??
            `${activeDocument.id}:intro`
        }
      );
      dispatch({
        type: "study_session_set",
        studySession: nextSession,
        personaId: activePlan.personaId,
        clearResponse: true
      });
      registerSession(nextSession, activePlan.id);
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

  const handleAsk = async (message: string) => {
    if (!state.studySession) {
      return;
    }
    await handleAskForSection(message, state.studySession.sectionId);
  };

  const ensureSessionForSection = async (
    sectionId: string,
    options: { clearResponseOnSwitch?: boolean } = {}
  ): Promise<StudySessionRecord | null> => {
    if (!activePlan || !activeDocument || !sectionId) {
      return null;
    }

    if (state.studySession?.sectionId === sectionId) {
      return state.studySession;
    }

    const registryKey = buildSessionRegistryKey(activePlan.id, sectionId);
    const existingSession = sessionRegistry[registryKey];
    if (existingSession) {
      dispatch({
        type: "study_session_set",
        studySession: existingSession,
        personaId: existingSession.personaId,
        clearResponse: options.clearResponseOnSwitch ?? true,
      });
      return existingSession;
    }

    const createdSession = await createStudySession({
      documentId: activeDocument.id,
      personaId: activePlan.personaId,
      sectionId,
      sectionTitle: resolveSectionTitle(sectionId),
      themeHint: resolveThemeHintBySectionId(sectionId),
    });
    dispatch({
      type: "study_session_set",
      studySession: createdSession,
      personaId: createdSession.personaId,
      clearResponse: options.clearResponseOnSwitch ?? true,
    });
    registerSession(createdSession, activePlan.id);
    return createdSession;
  };

  const handleAskForSection = async (message: string, sectionId: string) => {
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
        message
      });
      dispatch({
        type: "study_session_set",
        studySession: next.session,
        personaId: next.session.personaId,
        clearResponse: false
      });
      registerSession(next.session);
      dispatch({
        type: "response_set",
        response: next
      });
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
          if (!activePlan || !activeDocument) {
            throw new Error("active_plan_or_document_missing");
          }
          const recoveredSession = await createStudySession({
            documentId: activeDocument.id,
            personaId: activePlan.personaId,
            sectionId,
            sectionTitle: resolveSectionTitle(sectionId),
            themeHint: resolveThemeHintBySectionId(sectionId),
          });
          dispatch({
            type: "study_session_set",
            studySession: recoveredSession,
            personaId: recoveredSession.personaId,
            clearResponse: false,
          });
          registerSession(recoveredSession, activePlan.id);

          const recovered = await sendStudyMessage({
            sessionId: recoveredSession.id,
            message,
          });
          dispatch({
            type: "study_session_set",
            studySession: recovered.session,
            personaId: recovered.session.personaId,
            clearResponse: false,
          });
          registerSession(recovered.session, activePlan.id);
          dispatch({
            type: "response_set",
            response: recovered,
          });
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
        try {
          dispatch({
            type: "notice_set",
            notice: "模型输出格式异常，正在自动恢复重试…"
          });
          const recovered = await sendStudyMessage({
            sessionId: targetSession.id,
            message
          });
          dispatch({
            type: "study_session_set",
            studySession: recovered.session,
            personaId: recovered.session.personaId,
            clearResponse: false
          });
          registerSession(recovered.session);
          dispatch({
            type: "response_set",
            response: recovered
          });
          dispatch({
            type: "notice_set",
            notice: "已自动恢复本次对话。"
          });
          return;
        } catch (retryError) {
          dispatch({
            type: "notice_set",
            notice: `自动恢复失败: ${String(retryError)}`
          });
          logWorkspaceError("workflow:study_chat:retry_error", retryError);
          return;
        }
      }
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
        personaId: nextSession.personaId,
        clearResponse: false
      });
      registerSession(nextSession);
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
            personaId: nextSession.personaId,
            clearResponse: false
          });
          registerSession(nextSession);
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
    const handleFocus = () => {
      void syncWorkspaceSnapshot({
        includePersonas: false,
        preferredPlanId: state.selectedPlanId
      });
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
        const sessions = await listStudySessions({
          documentId: activeDocument.id,
          personaId: activePlan.personaId,
        });
        if (!active) {
          return;
        }
        registerSessions(sessions, activePlan.id);
      } catch (error) {
        logWorkspaceError("workflow:study_session:hydrate_error", error);
      }
    };
    void hydrateSessions();
    return () => {
      active = false;
    };
  }, [activeDocument?.id, activePlan?.id, activePlan?.personaId]);

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
    isGeneratingPlan,
    processStreamDocumentId,
    planStreamDocumentId,
    processStreamEvents,
    planStreamEvents,
    processStreamStatus,
    planStreamStatus,
    isSnapshotRefreshing: state.isSnapshotRefreshing,
    generatePlanWorkflow,
    selectPlan,
    createSessionForActivePlan,
    handleSwitchSection,
    handleAsk,
    handleAskForSection,
    handleSubmitQuestionAttempt,
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

function buildPlanDirectorySections(
  plan: LearningPlan | null,
  document: DocumentRecord | null
): DocumentSection[] {
  if (!plan || !document) {
    return [];
  }

  const studyUnitById = new Map(document.studyUnits.map((unit) => [unit.id, unit]));
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
    return document.sections;
  }

  return sections.filter(
    (section, index) => sections.findIndex((candidate) => candidate.id === section.id) === index
  );
}
