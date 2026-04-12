import type {
  DocumentRecord,
  LearningPlan,
  PersonaProfile,
  StudyUnit,
  StudyChatResponse,
  StudySessionRecord
} from "@vibe-learner/shared";

import { findLearningPlan } from "./plan-panel-data";
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
  | { type: "generation_started" }
  | { type: "notice_set"; notice: string }
  | {
      type: "snapshot_applied";
      personas?: PersonaProfile[];
      resolution: WorkspaceSnapshotResolution;
    }
  | {
      type: "plan_selected";
      planId: string;
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
      type: "plan_updated";
      plan: LearningPlan;
    }
  | {
      type: "plan_deleted";
      planId: string;
      preferredPlanId: string;
    }
  | {
      type: "document_and_plans_updated";
      document: DocumentRecord;
      plans: LearningPlan[];
    }
  | {
      type: "study_session_set";
      studySession: StudySessionRecord | null;
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
    case "generation_started":
      return {
        ...state,
        selectedPlanId: "",
        studySession: null,
        response: null
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
      {
        const nextDocuments = state.documents.map((document) => {
          if (document.id !== action.plan.documentId) {
            return document;
          }
          return {
            ...document,
            studyUnits: action.plan.studyUnits,
            studyUnitCount: action.plan.studyUnits.length,
            sections: projectSectionsFromStudyUnits(document, action.plan.studyUnits)
          };
        });
      return {
        ...state,
        documents: nextDocuments,
        planHistory: upsertLearningPlan(state.planHistory, action.plan),
        selectedPlanId: action.plan.id,
        studySession: null,
        response: null
      };
      }
    case "plan_updated":
      return {
        ...state,
        planHistory: upsertLearningPlan(state.planHistory, action.plan),
        selectedPlanId:
          state.selectedPlanId === action.plan.id ? action.plan.id : state.selectedPlanId,
        selectedPersonaId:
          state.selectedPlanId === action.plan.id ? action.plan.personaId : state.selectedPersonaId
      };
    case "plan_deleted":
      {
        const nextPlanHistory = state.planHistory.filter((plan) => plan.id !== action.planId);
        const deletingSelectedPlan = action.planId === state.selectedPlanId;
        const nextSelectedPlan = findLearningPlan(nextPlanHistory, action.preferredPlanId);
        return {
          ...state,
          planHistory: nextPlanHistory,
          selectedPlanId: deletingSelectedPlan ? nextSelectedPlan?.id ?? "" : state.selectedPlanId,
          selectedPersonaId:
            deletingSelectedPlan && nextSelectedPlan
              ? nextSelectedPlan.personaId
              : state.selectedPersonaId,
          studySession: deletingSelectedPlan ? null : state.studySession,
          response: deletingSelectedPlan ? null : state.response
        };
      }
    case "document_and_plans_updated":
      {
        let nextPlanHistory = state.planHistory;
        for (const plan of action.plans) {
          nextPlanHistory = upsertLearningPlan(nextPlanHistory, plan);
        }
        return {
          ...state,
          documents: upsertDocumentRecord(state.documents, action.document),
          planHistory: nextPlanHistory
        };
      }
    case "study_session_set":
      return {
        ...state,
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

function projectSectionsFromStudyUnits(
  document: DocumentRecord,
  studyUnits: StudyUnit[]
) {
  return studyUnits
    .filter((unit) => unit.includeInPlan)
    .map((unit) => ({
      id: unit.id,
      documentId: document.id,
      title: unit.title,
      pageStart: unit.pageStart,
      pageEnd: unit.pageEnd,
      level: 1
    }));
}
