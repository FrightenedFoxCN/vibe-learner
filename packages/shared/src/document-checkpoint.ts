import type { StudyUnit, DocumentRecord } from "./learning";

export interface DocumentCheckpoint {
  contractVersion: "document-checkpoint-response-v1";
  operationId: string;
  documentId: string;
  operationStatus: "running" | "failed" | "interrupted" | "committed";
  pageCount: number;
  completedPageCount: number;
  stage: "pages" | "parsed" | "study_units";
  forceOcr: boolean;
  storageLimited: boolean;
  childOperationId: string | null;
  pages: { pageNumber: number; textPreview: string; extractionSource: string }[];
  studyUnits: Pick<
    StudyUnit,
    "id" | "documentId" | "title" | "pageStart" | "pageEnd"
  >[];
  result: DocumentRecord | null;
  projectionState: "committed" | "checkpoint_only";
}
