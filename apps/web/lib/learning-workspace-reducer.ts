import type {
  DocumentRecord,
  LearningPlan,
  PersonaProfile,
  StudyChatResponse,
  StudySessionRecord
} from "@gal-learner/shared";

import { upsertLearningPlan } from "./plan-panel-data";
import {
  type WorkspaceSnapshotResolution,
  upsertDocumentRecord
} from "./learning-workspace-state";
import { INITIAL_NOTICE } from "./learning-workspace-copy";

export interface LearningWorkspaceState {
  personas: PersonaProfile[];
  selectedPersonaId: string;
  documents: DocumentRecord[];
  selectedPlanId: string;
  planHistory: LearningPlan[];
  studySession: StudySessionRecord | null;
  response: StudyChatResponse | null;
  notice: string;
  isBusy: boolean;
  isSnapshotRefreshing: boolean;
}

type LearningWorkspaceAction =
  | { type: "snapshot_refresh_started" }
  | { type: "snapshot_refresh_finished" }
  | { type: "busy_started" }
  | { type: "busy_finished" }
  | { type: "notice_set"; notice: string }
  | {
      type: "snapshot_applied";
      personas?: PersonaProfile[];
      resolution: WorkspaceSnapshotResolution;
    }
  | {
      type: "plan_selected";
      planId: string;
      personaId: string;
      notice?: string;
    }
  | {
      type: "generated_document_applied";
      document: DocumentRecord;
    }
  | {
      type: "generated_plan_applied";
      plan: LearningPlan;
    }
  | {
      type: "study_session_set";
      studySession: StudySessionRecord | null;
      personaId?: string;
      clearResponse?: boolean;
    }
  | {
      type: "response_set";
      response: StudyChatResponse | null;
    }
  | {
      type: "persona_selected";
      personaId: string;
    };

export function createInitialLearningWorkspaceState(input: {
  initialPlan?: LearningPlan;
  initialPersonas: PersonaProfile[];
}): LearningWorkspaceState {
  return {
    personas: input.initialPersonas,
    selectedPersonaId: input.initialPersonas[0]?.id ?? "",
    documents: [],
    selectedPlanId: input.initialPlan?.id ?? "",
    planHistory: input.initialPlan ? [input.initialPlan] : [],
    studySession: null,
    response: null,
    notice: INITIAL_NOTICE,
    isBusy: false,
    isSnapshotRefreshing: false
  };
}

export function learningWorkspaceReducer(
  state: LearningWorkspaceState,
  action: LearningWorkspaceAction
): LearningWorkspaceState {
  switch (action.type) {
    case "snapshot_refresh_started":
      return {
        ...state,
        isSnapshotRefreshing: true
      };
    case "snapshot_refresh_finished":
      return {
        ...state,
        isSnapshotRefreshing: false
      };
    case "busy_started":
      return {
        ...state,
        isBusy: true
      };
    case "busy_finished":
      return {
        ...state,
        isBusy: false
      };
    case "notice_set":
      return {
        ...state,
        notice: action.notice
      };
    case "snapshot_applied":
      return {
        ...state,
        personas: action.personas?.length ? action.personas : state.personas,
        documents: action.resolution.documents,
        planHistory: action.resolution.plans,
        selectedPlanId: action.resolution.selectedPlanId,
        selectedPersonaId: action.resolution.selectedPersonaId,
        studySession: action.resolution.shouldResetStudySession ? null : state.studySession,
        response: action.resolution.shouldResetStudySession ? null : state.response
      };
    case "plan_selected":
      if (action.planId === state.selectedPlanId) {
        return state;
      }
      return {
        ...state,
        selectedPlanId: action.planId,
        selectedPersonaId: action.personaId,
        studySession: null,
        response: null,
        notice: action.notice ?? state.notice
      };
    case "generated_document_applied":
      return {
        ...state,
        documents: upsertDocumentRecord(state.documents, action.document)
      };
    case "generated_plan_applied":
      return {
        ...state,
        planHistory: upsertLearningPlan(state.planHistory, action.plan),
        selectedPlanId: action.plan.id,
        selectedPersonaId: action.plan.personaId,
        studySession: null,
        response: null
      };
    case "study_session_set":
      return {
        ...state,
        selectedPersonaId: action.personaId ?? state.selectedPersonaId,
        studySession: action.studySession,
        response: action.clearResponse ? null : state.response
      };
    case "response_set":
      return {
        ...state,
        response: action.response
      };
    case "persona_selected":
      return {
        ...state,
        selectedPersonaId: action.personaId
      };
    default:
      return state;
  }
}
