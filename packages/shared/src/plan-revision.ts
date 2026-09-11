import type { LearningPlan } from "./learning";

export interface PlanRevisionProposal {
  explanation: string;
  courseTitle: string;
  overview: string;
  todayTasks: string[];
  schedule: { scheduleRef: string; title: string; focus: string }[];
}
export interface PlanRevision {
  operationId: string;
  clientRequestId: string;
  planId: string;
  baseRevision: number;
  status: "generating" | "ready" | "applying" | "accepted" | "rejected" | "failed" | "uncertain" | "conflict";
  instruction: string;
  rollbackRevision: number | null;
  proposal: PlanRevisionProposal | null;
  basePlan: LearningPlan;
  result: LearningPlan | null;
  errorCode: string;
}
