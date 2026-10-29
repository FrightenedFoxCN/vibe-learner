import type { DocumentRecord } from "./learning";

export interface StudyUnitSuggestion {
  title: string;
  pageStart: number;
  pageEnd: number;
  unitKind: "chapter" | "front_matter" | "solutions" | "back_matter";
  includeInPlan: boolean;
  summary: string;
}

export interface StudyUnitRevision {
  preview: {
    operationId: string;
    planId: string;
    parentOperationId: string;
    baseDocument: DocumentRecord;
    baseDebugDigest: string;
    suggestions: { studyUnits: StudyUnitSuggestion[]; rationale: string };
  };
  status: "ready" | "applying" | "accepted" | "rejected" | "conflict" | "failed";
  result: DocumentRecord | null;
  planningContextRevision: number | null;
  errorCode: string;
}
