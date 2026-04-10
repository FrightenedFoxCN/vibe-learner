import type { DocumentRecord, LearningPlan, PersonaProfile } from "@gal-learner/shared";

export interface PlanHistoryItem {
  id: string;
  courseTitle: string;
  documentTitle: string;
  personaName: string;
  deadline: string;
  createdAt: string;
  overview: string;
}

export function sortLearningPlans(plans: LearningPlan[]): LearningPlan[] {
  return [...plans].sort((left, right) =>
    (right.createdAt || "").localeCompare(left.createdAt || "")
  );
}

export function upsertLearningPlan(
  plans: LearningPlan[],
  nextPlan: LearningPlan
): LearningPlan[] {
  return sortLearningPlans([
    nextPlan,
    ...plans.filter((plan) => plan.id !== nextPlan.id)
  ]);
}

export function resolveSelectedPlanId(
  plans: LearningPlan[],
  selectedPlanId: string
): string {
  if (selectedPlanId && plans.some((plan) => plan.id === selectedPlanId)) {
    return selectedPlanId;
  }
  return plans[0]?.id ?? "";
}

export function findLearningPlan(
  plans: LearningPlan[],
  planId: string
): LearningPlan | null {
  return plans.find((plan) => plan.id === planId) ?? null;
}

export function findDocumentForPlan(
  plan: LearningPlan | null,
  documents: DocumentRecord[]
): DocumentRecord | null {
  if (!plan) {
    return null;
  }
  return documents.find((document) => document.id === plan.documentId) ?? null;
}

export function buildPlanHistoryItems(input: {
  plans: LearningPlan[];
  documents: DocumentRecord[];
  personas: PersonaProfile[];
}): PlanHistoryItem[] {
  const documentTitleById = new Map(
    input.documents.map((document) => [document.id, document.title])
  );
  const personaNameById = new Map(
    input.personas.map((persona) => [persona.id, persona.name])
  );

  return input.plans.map((plan) => ({
    id: plan.id,
    courseTitle: plan.courseTitle,
    documentTitle: documentTitleById.get(plan.documentId) ?? plan.documentId,
    personaName: personaNameById.get(plan.personaId) ?? plan.personaId,
    deadline: plan.deadline,
    createdAt: plan.createdAt,
    overview: plan.overview
  }));
}
