import type { DocumentCheckpoint } from "@vibe-learner/shared";
import { StrictResponseDecoder } from "./strict-response-decode.ts";
import { DocumentDecodeError, decodeDocumentRecord } from "./document-decode.ts";
const d = new StrictResponseDecoder((path, reason) => {
  throw new DocumentDecodeError(path, reason);
});
export function decodeDocumentCheckpoint(
  raw: unknown,
  documentId: string,
  operationId?: string,
): DocumentCheckpoint {
  const p = "document_checkpoint",
    v = d.record(raw, p);
  d.equal(
    v.contract_version,
    "document-checkpoint-response-v1",
    `${p}.contract_version`,
  );
  d.equal(v.document_id, documentId, `${p}.document_id`);
  const id = d.string(d.field(v, "operation_id", p), `${p}.operation_id`);
  if (operationId) d.equal(id, operationId, `${p}.operation_id`);
  const operationStatus = d.enumeration(
    d.field(v, "operation_status", p),
    ["running", "failed", "interrupted", "committed"] as const,
    `${p}.operation_status`,
  );
  const pageCount = d.integer(d.field(v, "page_count", p), `${p}.page_count`);
  const completedPageCount = d.integer(
    d.field(v, "completed_page_count", p),
    `${p}.completed_page_count`,
    0,
    pageCount,
  );
  const pages = d.array(d.field(v, "pages", p), `${p}.pages`, (raw, path) => {
    const value = d.record(raw, path);
    return {
      pageNumber: d.integer(
        d.field(value, "page_number", path),
        `${path}.page_number`,
        1,
        pageCount,
      ),
      textPreview: d.string(
        d.field(value, "text_preview", path),
        `${path}.text_preview`,
        true,
      ),
      extractionSource: d.enumeration(
        d.field(value, "extraction_source", path),
        ["text", "ocr", "ocr_attempted", "ocr_unavailable", "ocr_failed"] as const,
        `${path}.extraction_source`,
      ),
    };
  });
  d.unique(
    pages.map((page) => page.pageNumber),
    `${p}.pages`,
  );
  d.nonDecreasing(
    pages.map((page) => page.pageNumber),
    `${p}.pages`,
  );
  if (pages.length > 64 || pages.length > completedPageCount)
    throw new DocumentDecodeError(p, "checkpoint_page_count_mismatch");
  const stage = d.enumeration(
    d.field(v, "stage", p),
    ["pages", "parsed", "study_units"] as const,
    `${p}.stage`,
  );
  const studyUnits = d.array(
    d.field(v, "study_units", p),
    `${p}.study_units`,
    (raw, path) => {
      const unit = d.record(raw, path);
      const result = {
        id: d.string(d.field(unit, "id", path), `${path}.id`),
        documentId: d.string(d.field(unit, "document_id", path), `${path}.document_id`),
        title: d.string(d.field(unit, "title", path), `${path}.title`, true),
        pageStart: d.integer(
          d.field(unit, "page_start", path),
          `${path}.page_start`,
          1,
        ),
        pageEnd: d.integer(d.field(unit, "page_end", path), `${path}.page_end`, 1),
      };
      d.equal(result.documentId, documentId, `${path}.document_id`);
      d.range(result.pageStart, result.pageEnd, path, pageCount);
      return result;
    },
  );
  d.unique(
    studyUnits.map((unit) => unit.id),
    `${p}.study_units`,
  );
  if (stage !== "study_units" && studyUnits.length)
    throw new DocumentDecodeError(p, "checkpoint_stage_mismatch");
  const projectionState = d.enumeration(
    d.field(v, "projection_state", p),
    ["committed", "checkpoint_only"] as const,
    `${p}.projection_state`,
  );
  if ((operationStatus === "committed") !== (projectionState === "committed"))
    throw new DocumentDecodeError(p, "checkpoint_commit_mismatch");
  const result = d.nullable(d.field(v, "result", p), `${p}.result`, (raw) =>
    decodeDocumentRecord(raw, documentId),
  );
  if ((operationStatus === "committed") !== (result !== null))
    throw new DocumentDecodeError(p, "checkpoint_result_status_mismatch");
  if (result && (result.status !== "processed" || result.pageCount !== pageCount))
    throw new DocumentDecodeError(p, "checkpoint_result_projection_mismatch");
  return {
    contractVersion: "document-checkpoint-response-v1",
    operationId: id,
    documentId,
    operationStatus,
    pageCount,
    completedPageCount,
    stage,
    forceOcr: d.boolean(d.field(v, "force_ocr", p), `${p}.force_ocr`),
    storageLimited: d.boolean(d.field(v, "storage_limited", p), `${p}.storage_limited`),
    childOperationId: d.nullable(
      d.field(v, "child_operation_id", p),
      `${p}.child_operation_id`,
      (raw, path) => d.string(raw, path),
    ),
    pages,
    studyUnits,
    result,
    projectionState,
  };
}
