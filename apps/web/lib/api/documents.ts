import { documentUploadError } from "../document-upload-validation";
import { decodeDocumentCheckpoint } from "../document-checkpoint-decode";
import { decodeDocumentPageNumbering } from "../document-page-numbering-decode";
import {
  createDiagnosticId,
  diagnosticContext,
  diagnosticDecode,
  DiagnosticContext as DiagnosticContext,
} from "../diagnostics";
import type {
  DocumentPlanningContext,
  DocumentPlanningTraceResponse,
  DocumentDebugRecord,
  DocumentRecord,
  LearningPlan,
  StreamEvent,
  StreamReport,
} from "@vibe-learner/shared";
import { compactPreviewString } from "../preview";
import {
  decodeDocumentList,
  decodeDocumentRecord,
  DocumentDecodeError,
} from "../document-decode";
import { decodeDocumentStudyUnitUpdate } from "../planning-decode";
import { StrictStreamStateMachine } from "../stream-decode";

import {
  AI_BASE_URL,
  request,
  readJson,
  consumeDiagnosticStream,
  formatStreamErrorPayload,
  normalizeDocument,
  normalizeDebugRecord,
  normalizePlanningContext,
  normalizePlanningTraceResponse,
  normalizeStreamReport,
} from "./_shared";

export interface DocumentStudyUnitUpdatePayload {
  document: DocumentRecord;
  plans: LearningPlan[];
}

export async function listDocuments(): Promise<DocumentRecord[]> {
  const diagnosticResponse = await request(`${AI_BASE_URL()}/documents`);
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () => decodeDocumentList(payload)).map(
    (document) => ({
      ...document,
      previewExcerpt: compactPreviewString(document.previewExcerpt, 240),
    }),
  );
}

export async function getDocumentDebug(
  documentId: string,
): Promise<DocumentDebugRecord> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/documents/${documentId}/debug`,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    normalizeDebugRecord(payload, documentId),
  );
}

export async function getDocumentPlanningContext(
  documentId: string,
): Promise<DocumentPlanningContext> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/documents/${documentId}/planning-context`,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    normalizePlanningContext(payload, documentId),
  );
}

export async function getDocumentPlanningTrace(
  documentId: string,
): Promise<DocumentPlanningTraceResponse> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/documents/${documentId}/planning-trace`,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    normalizePlanningTraceResponse(payload, documentId),
  );
}

export async function getDocumentProcessEvents(
  documentId: string,
): Promise<StreamReport> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/documents/${documentId}/process-events`,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    normalizeStreamReport(payload, documentId, "document_process"),
  );
}

export async function getDocumentPlanEvents(documentId: string): Promise<StreamReport> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/documents/${documentId}/plan-events`,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () =>
    normalizeStreamReport(payload, documentId, "learning_plan"),
  );
}

export async function uploadDocument(
  file: File,
  options?: { signal?: AbortSignal; diagnostic?: DiagnosticContext },
): Promise<DocumentRecord> {
  const validation = documentUploadError(file);
  if (validation) throw new Error(validation);
  const form = new FormData();
  form.append("file", file);
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/documents`,
    {
      method: "POST",
      body: form,
      signal: options?.signal,
    },
    options?.diagnostic,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  return diagnosticDecode(diagnosticResponse, () => normalizeDocument(payload));
}

export async function uploadAndProcessDocument(file: File): Promise<DocumentRecord> {
  const diagnostic = diagnosticContext(createDiagnosticId());
  const uploaded = await uploadDocument(file, { diagnostic });
  return processDocument(uploaded.id, { diagnostic });
}

export async function processDocument(
  documentId: string,
  options?: {
    diagnostic?: DiagnosticContext;
    forceOcr?: boolean;
    resumeFromOperationId?: string;
  },
): Promise<DocumentRecord> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/documents/${documentId}/process`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        force_ocr: Boolean(options?.forceOcr),
        resume_from_operation_id: options?.resumeFromOperationId,
      }),
    },
    options?.diagnostic,
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  const decoded = diagnosticDecode(diagnosticResponse, () =>
    decodeDocumentRecord(payload, documentId, "document", true),
  );
  return {
    ...decoded,
    previewExcerpt: compactPreviewString(decoded.previewExcerpt, 240),
  };
}

export async function processDocumentStream(
  documentId: string,
  options: {
    diagnostic?: DiagnosticContext;
    forceOcr?: boolean;
    resumeFromOperationId?: string;
    signal?: AbortSignal;
  },
  onEvent: (event: StreamEvent) => void,
): Promise<DocumentRecord> {
  const response = await request(
    `${AI_BASE_URL()}/documents/${documentId}/process/stream`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      signal: options.signal,
      body: JSON.stringify({
        force_ocr: Boolean(options.forceOcr),
        resume_from_operation_id: options.resumeFromOperationId,
      }),
    },
    options?.diagnostic,
  );
  if (!response.ok || !response.body) {
    const text = await response.text();
    throw new Error(text || `HTTP ${response.status}`);
  }

  let finalDocument: DocumentRecord | null = null;
  const machine = new StrictStreamStateMachine({
    streamKind: "document_process",
    subject: { subjectType: "document", subjectId: documentId },
  });
  const terminal = await consumeDiagnosticStream(
    response,
    response.body,
    machine,
    (event) => {
      if (event.stage === "stream_completed") {
        const decoded = decodeDocumentRecord(
          event.committedProjection,
          documentId,
          "stream.document",
          true,
        );
        finalDocument = {
          ...decoded,
          previewExcerpt: compactPreviewString(decoded.previewExcerpt, 240),
        };
      }
      onEvent(event);
    },
  );
  if (terminal.stage === "stream_cancelled") {
    throw new DOMException("stream_interrupted", "AbortError");
  }
  if (terminal.stage === "stream_error") {
    throw new Error(
      formatStreamErrorPayload(terminal.payload, "processing_stream_error"),
    );
  }
  if (!finalDocument) {
    throw new Error("processing_stream_committed_terminal_without_document");
  }
  return finalDocument;
}

export async function updateDocumentStudyUnitTitle(
  documentId: string,
  studyUnitId: string,
  title: string,
  expectedRevision: number,
): Promise<DocumentStudyUnitUpdatePayload> {
  const diagnosticResponse = await request(
    `${AI_BASE_URL()}/documents/${documentId}/study-units/${studyUnitId}`,
    {
      method: "PATCH",
      headers: {
        "Content-Type": "application/json",
      },
      body: JSON.stringify({
        title,
        expected_revision: expectedRevision,
      }),
    },
  );
  const payload = await readJson<unknown>(diagnosticResponse);
  const decoded = diagnosticDecode(diagnosticResponse, () =>
    decodeDocumentStudyUnitUpdate(payload, documentId),
  );
  if (decoded.document.revision !== expectedRevision + 1) {
    throw new DocumentDecodeError(
      "document_study_unit_update.document.revision",
      "unexpected_committed_revision",
    );
  }
  if (!decoded.document.studyUnits.some((unit) => unit.id === studyUnitId)) {
    throw new DocumentDecodeError(
      "document_study_unit_update.document.study_units",
      `missing_updated_study_unit_${studyUnitId}`,
    );
  }
  return decoded;
}

export async function getDocumentPageNumbering(documentId: string, pages: number[]) {
  if (
    !pages.length ||
    pages.length > 64 ||
    pages.some((page) => !Number.isSafeInteger(page) || page < 1) ||
    new Set(pages).size !== pages.length
  )
    throw new Error("invalid_physical_page_request");
  const params = new URLSearchParams();
  pages.forEach((page) => params.append("page_numbers", String(page)));
  const response = await request(
    `${AI_BASE_URL()}/documents/${documentId}/page-numbering?${params}`,
  );
  const raw = await readJson<unknown>(response);
  return diagnosticDecode(
    response,
    () => decodeDocumentPageNumbering(raw, documentId, pages),
    "document-page-numbering-v1",
  );
}

export async function getDocumentCheckpoint(documentId: string, operationId?: string) {
  const path = operationId
    ? `checkpoints/${encodeURIComponent(operationId)}`
    : "checkpoint";
  const response = await request(`${AI_BASE_URL()}/documents/${documentId}/${path}`);
  const raw = await readJson<unknown>(response);
  return diagnosticDecode(
    response,
    () => decodeDocumentCheckpoint(raw, documentId, operationId),
    "document-checkpoint-response-v1",
  );
}
