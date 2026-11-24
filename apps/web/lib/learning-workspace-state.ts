import type {
  DocumentRecord,
  LearningPlan,
  PersonaProfile,
} from "@vibe-learner/shared";

import {
  resolveSelectedPlanId,
  sortLearningPlans,
  upsertLearningPlan,
} from "./plan-panel-data.ts";

export interface WorkspaceSnapshot {
  personas?: PersonaProfile[];
  documents: DocumentRecord[];
  plans: LearningPlan[];
}

export interface PlanSelection {
  selectedPlanId: string;
  planHistory: LearningPlan[];
}

export type PlanSelectionIntent =
  | { type: "snapshot"; plans: LearningPlan[]; preferredPlanId: string }
  | { type: "select"; planId: string }
  | { type: "delete"; planId: string }
  | { type: "generate" }
  | { type: "generated"; plan: LearningPlan }
  | { type: "update"; plans: LearningPlan[] };

export interface PlanSelectionTransition {
  selection: PlanSelection;
  studyTarget: string | null;
}

export function resolvePlanSelection(
  current: PlanSelection,
  intent: PlanSelectionIntent,
): PlanSelectionTransition | null {
  let { selectedPlanId, planHistory } = current;
  switch (intent.type) {
    case "snapshot":
      planHistory = sortLearningPlans(intent.plans);
      selectedPlanId = resolveSelectedPlanId(
        planHistory,
        selectedPlanId || intent.preferredPlanId,
      );
      break;
    case "select":
      if (
        intent.planId === selectedPlanId ||
        !planHistory.some((plan) => plan.id === intent.planId)
      )
        return null;
      selectedPlanId = intent.planId;
      break;
    case "delete":
      planHistory = planHistory.filter((plan) => plan.id !== intent.planId);
      if (selectedPlanId === intent.planId) selectedPlanId = planHistory[0]?.id ?? "";
      break;
    case "generate":
      selectedPlanId = "";
      break;
    case "generated":
      planHistory = upsertLearningPlan(planHistory, intent.plan);
      selectedPlanId = intent.plan.id;
      break;
    case "update":
      for (const plan of intent.plans)
        planHistory = upsertLearningPlan(planHistory, plan);
      break;
  }
  const studyTarget =
    intent.type === "generate"
      ? "study-plan:generating"
      : intent.type === "generated" || selectedPlanId !== current.selectedPlanId
        ? `study-plan:${selectedPlanId || "none"}`
        : null;
  return { selection: { selectedPlanId, planHistory }, studyTarget };
}

export function resolveSnapshotPersonaId(
  personas: PersonaProfile[] | undefined,
  current: string,
): string {
  if (!personas || personas.some((persona) => persona.id === current)) return current;
  return personas[0]?.id ?? "";
}

export function upsertDocumentRecord(
  documents: DocumentRecord[],
  nextDocument: DocumentRecord,
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
  const firstUnit =
    input.plan.studyUnits.find((unit) => unit.includeInPlan) ??
    input.plan.studyUnits[0];
  return {
    documentId: input.document?.id ?? input.plan.documentId ?? "",
    personaId: input.personaId,
    planId: input.planId,
    studyUnitId:
      firstUnit?.id ?? input.document?.studyUnits[0]?.id ?? `${input.plan.id}:intro`,
    studyUnitTitle:
      firstUnit?.title ??
      input.document?.studyUnits[0]?.title ??
      `${input.plan.id}:intro`,
    themeHint:
      input.plan.studyUnitProgress.find((item) => item.unitId === firstUnit?.id)
        ?.objectiveFragment ??
      input.plan.schedule.find((item) => item.unitId === firstUnit?.id)
        ?.scheduleChapters[0]?.title ??
      input.plan.objective,
  };
}
