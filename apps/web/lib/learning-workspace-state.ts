import type { DocumentRecord, LearningPlan, PersonaProfile } from "@vibe-learner/shared";

import { findLearningPlan, resolveSelectedPlanId, sortLearningPlans } from "./plan-panel-data";

export interface WorkspaceSnapshot {
  personas?: PersonaProfile[];
  documents: DocumentRecord[];
  plans: LearningPlan[];
}

export interface WorkspaceSnapshotResolution {
  documents: DocumentRecord[];
  plans: LearningPlan[];
  selectedPlanId: string;
  selectedPersonaId: string;
  shouldResetStudySession: boolean;
}

export function resolveWorkspaceSnapshot(input: {
  snapshot: WorkspaceSnapshot;
  preferredPlanId: string;
  currentSelectedPlanId: string;
  currentSelectedPersonaId: string;
}): WorkspaceSnapshotResolution {
  const sortedPlans = sortLearningPlans(input.snapshot.plans);
  const nextSelectedPlanId = resolveSelectedPlanId(sortedPlans, input.preferredPlanId);
  const hasCurrentPersonaInSnapshot = input.snapshot.personas?.some(
    (persona) => persona.id === input.currentSelectedPersonaId
  );
  const nextSelectedPersonaId = input.currentSelectedPersonaId
    ? (input.snapshot.personas && !hasCurrentPersonaInSnapshot
      ? input.snapshot.personas[0]?.id ?? ""
      : input.currentSelectedPersonaId)
    : input.snapshot.personas?.[0]?.id ?? "";

  return {
    documents: input.snapshot.documents,
    plans: sortedPlans,
    selectedPlanId: nextSelectedPlanId,
    selectedPersonaId: nextSelectedPersonaId,
    shouldResetStudySession: nextSelectedPlanId !== input.currentSelectedPlanId
  };
}

export function upsertDocumentRecord(
  documents: DocumentRecord[],
  nextDocument: DocumentRecord
): DocumentRecord[] {
  const filtered = documents.filter((document) => document.id !== nextDocument.id);
  return [nextDocument, ...filtered];
}

export function buildInitialStudySessionInput(input: {
  document: DocumentRecord;
  personaId: string;
}) {
  return {
    documentId: input.document.id,
    personaId: input.personaId,
    sectionId: input.document.sections[0]?.id ?? `${input.document.id}:intro`
  };
}
