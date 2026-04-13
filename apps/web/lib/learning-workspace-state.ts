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
  plan: LearningPlan;
  document?: DocumentRecord | null;
  planId: string;
  personaId: string;
}) {
  const firstUnit = input.plan.studyUnits.find((unit) => unit.includeInPlan) ?? input.plan.studyUnits[0];
  return {
    documentId: input.document?.id ?? input.plan.documentId ?? "",
    personaId: input.personaId,
    planId: input.planId,
    sectionId:
      firstUnit?.id ??
      input.document?.sections[0]?.id ??
      `${input.plan.id}:intro`,
    sectionTitle:
      firstUnit?.title ??
      input.document?.sections[0]?.title ??
      input.plan.studyChapters[0] ??
      `${input.plan.id}:intro`,
    themeHint:
      input.plan.chapterProgress.find((item) => item.unitId === firstUnit?.id)?.objectiveFragment ??
      input.plan.studyChapters[0] ??
      input.plan.objective
  };
}
