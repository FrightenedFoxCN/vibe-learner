"use client";

import { useEffect, useReducer } from "react";
import type {
  DocumentRecord,
  LearningPlan,
  PersonaProfile,
  StudyChatResponse,
  StudySessionRecord
} from "@gal-learner/shared";

import {
  createLearningPlan,
  createStudySession,
  listDocuments,
  listLearningPlans,
  listPersonas,
  sendStudyMessage,
  uploadAndProcessDocument
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
  deadline: string;
  studyDaysPerWeek: number;
  sessionMinutes: number;
}

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

  const selectedPersona =
    state.personas.find((persona) => persona.id === state.selectedPersonaId) ?? state.personas[0];
  const activePlan = findLearningPlan(state.planHistory, state.selectedPlanId);
  const activeDocument = findDocumentForPlan(activePlan, state.documents);
  const planHistoryItems = buildPlanHistoryItems({
    plans: state.planHistory,
    documents: state.documents,
    personas: state.personas
  });
  const activeSection =
    activeDocument?.sections.find((section) => section.id === state.studySession?.sectionId) ??
    activeDocument?.sections[0] ??
    null;

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
    dispatch({ type: "busy_started" });
    try {
      logWorkspaceInfo("workflow:upload:start", {
        filename: input.file.name,
        sizeBytes: input.file.size,
        personaId: selectedPersona.id
      });

      const nextDocument = await uploadAndProcessDocument(input.file);
      logWorkspaceInfo("workflow:upload:document_ready", {
        documentId: nextDocument.id,
        pageCount: nextDocument.pageCount,
        chunkCount: nextDocument.chunkCount,
        ocrStatus: nextDocument.ocrStatus
      });
      applyGeneratedDocument(nextDocument);

      const nextPlan = await createLearningPlan({
        documentId: nextDocument.id,
        personaId: selectedPersona.id,
        objective: input.objective,
        deadline: input.deadline,
        studyDaysPerWeek: input.studyDaysPerWeek,
        sessionMinutes: input.sessionMinutes
      });
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
      dispatch({
        type: "notice_set",
        notice: `教材处理失败: ${String(error)}`
      });
      logWorkspaceError("workflow:upload:error", error);
    } finally {
      dispatch({ type: "busy_finished" });
    }
  };

  const createSessionForActivePlan = async () => {
    if (!activePlan || !activeDocument) {
      return;
    }
    try {
      dispatch({ type: "busy_started" });
      const nextSession = await createStudySession(
        buildInitialStudySessionInput({
          document: activeDocument,
          personaId: activePlan.personaId
        })
      );
      dispatch({
        type: "study_session_set",
        studySession: nextSession,
        personaId: activePlan.personaId,
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

  const handleAsk = async (message: string) => {
    if (!state.studySession) {
      return;
    }
    try {
      dispatch({ type: "busy_started" });
      logWorkspaceInfo("workflow:study_chat:start", {
        sessionId: state.studySession.id,
        messageLength: message.length
      });
      const next = await sendStudyMessage({
        sessionId: state.studySession.id,
        message
      });
      dispatch({
        type: "response_set",
        response: next
      });
      logWorkspaceInfo("workflow:study_chat:done", {
        sessionId: state.studySession.id,
        citations: next.citations.length,
        characterEvents: next.characterEvents.length
      });
    } catch (error) {
      dispatch({
        type: "notice_set",
        notice: `导学请求失败: ${String(error)}`
      });
      logWorkspaceError("workflow:study_chat:error", error);
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

  return {
    personas: state.personas,
    selectedPersona,
    selectedPersonaId: state.selectedPersonaId,
    setSelectedPersonaId: (personaId: string) =>
      dispatch({ type: "persona_selected", personaId }),
    selectedPlanId: state.selectedPlanId,
    activePlan,
    activeDocument,
    activeSection,
    planHistory: state.planHistory,
    planHistoryItems,
    studySession: state.studySession,
    response: state.response,
    notice: state.notice,
    isBusy: state.isBusy,
    isSnapshotRefreshing: state.isSnapshotRefreshing,
    generatePlanWorkflow,
    selectPlan,
    createSessionForActivePlan,
    handleAsk,
    refreshPlanSnapshot: () =>
      syncWorkspaceSnapshot({
        includePersonas: false,
        preferredPlanId: state.selectedPlanId,
        successNotice: SNAPSHOT_REFRESHED_NOTICE
      })
  };
}
