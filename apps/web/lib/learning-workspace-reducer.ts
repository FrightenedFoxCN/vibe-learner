import type {
  DocumentRecord,
  LearningPlan,
  PersonaProfile,
  StudyUnit,
  StudyChatResponse,
  StudySessionRecord,
} from "@vibe-learner/shared";

import {
  type PlanSelection,
  type PlanSelectionTransition,
  type WorkspaceSnapshot,
  upsertDocumentRecord,
} from "./learning-workspace-state.ts";
import { INITIAL_NOTICE } from "./learning-workspace-copy.ts";

export interface LearningWorkspaceState extends PlanSelection {
  personas: PersonaProfile[];
  selectedPersonaId: string;
  documents: DocumentRecord[];
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
      type: "plan_transition";
      transition: PlanSelectionTransition;
      snapshot?: WorkspaceSnapshot & { selectedPersonaId: string };
      document?: DocumentRecord;
      generatedPlan?: LearningPlan;
      notice?: string;
    }
  | { type: "generated_document_applied"; document: DocumentRecord }
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
    }
  | {
      type: "personas_refreshed";
      personas: PersonaProfile[];
    };

export function createInitialLearningWorkspaceState(input: {
  initialPlan?: LearningPlan;
  initialSelection?: { planId: string; personaId: string };
  initialPersonas: PersonaProfile[];
}): LearningWorkspaceState {
  return {
    personas: input.initialPersonas,
    selectedPersonaId:
      input.initialSelection?.personaId || input.initialPersonas[0]?.id || "",
    documents: [],
    selectedPlanId: input.initialSelection?.planId || input.initialPlan?.id || "",
    planHistory: input.initialPlan ? [input.initialPlan] : [],
    studySession: null,
    response: null,
    notice: INITIAL_NOTICE,
    isBusy: false,
    isSnapshotRefreshing: false,
  };
}

export function learningWorkspaceReducer(
  state: LearningWorkspaceState,
  action: LearningWorkspaceAction,
): LearningWorkspaceState {
  switch (action.type) {
    case "snapshot_refresh_started":
      return {
        ...state,
        isSnapshotRefreshing: true,
      };
    case "snapshot_refresh_finished":
      return {
        ...state,
        isSnapshotRefreshing: false,
      };
    case "busy_started":
      return {
        ...state,
        isBusy: true,
      };
    case "busy_finished":
      return {
        ...state,
        isBusy: false,
      };
    case "notice_set":
      return {
        ...state,
        notice: action.notice,
      };
    case "plan_transition": {
      const { selection, studyTarget } = action.transition;
      const snapshot = action.snapshot;
      let documents = snapshot?.documents ?? state.documents;
      if (action.document) documents = upsertDocumentRecord(documents, action.document);
      const plan = action.generatedPlan;
      if (plan?.documentId) {
        documents = documents.map((document) =>
          document.id === plan.documentId
            ? {
                ...document,
                studyUnits: plan.studyUnits,
                studyUnitCount: plan.studyUnits.length,
                sections: projectSectionsFromStudyUnits(document, plan.studyUnits),
              }
            : document,
        );
      }
      return {
        ...state,
        ...selection,
        documents,
        personas: snapshot?.personas?.length ? snapshot.personas : state.personas,
        selectedPersonaId: snapshot?.selectedPersonaId ?? state.selectedPersonaId,
        studySession: studyTarget === null ? state.studySession : null,
        response: studyTarget === null ? state.response : null,
        notice: action.notice ?? state.notice,
      };
    }
    case "generated_document_applied":
      return {
        ...state,
        documents: upsertDocumentRecord(state.documents, action.document),
      };
    case "study_session_set":
      return {
        ...state,
        studySession: action.studySession,
        response: action.clearResponse ? null : state.response,
      };
    case "response_set":
      return {
        ...state,
        response: action.response,
      };
    case "persona_selected":
      return {
        ...state,
        selectedPersonaId: action.personaId,
      };
    case "personas_refreshed":
      return {
        ...state,
        personas: action.personas,
        selectedPersonaId: action.personas.some(
          (persona) => persona.id === state.selectedPersonaId,
        )
          ? state.selectedPersonaId
          : (action.personas[0]?.id ?? ""),
      };
    default:
      return state;
  }
}

function projectSectionsFromStudyUnits(
  document: DocumentRecord,
  studyUnits: StudyUnit[],
) {
  return studyUnits
    .filter((unit) => unit.includeInPlan)
    .map((unit) => ({
      id: unit.id,
      documentId: document.id,
      title: unit.title,
      pageStart: unit.pageStart,
      pageEnd: unit.pageEnd,
      level: 1,
    }));
}
