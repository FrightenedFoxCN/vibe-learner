import type {
  DocumentChunkRecord,
  DocumentDebugRecord,
  DocumentPageRecord,
  DocumentRecord,
  DocumentSection,
  OcrStatus,
  ParseWarning,
  StudyUnit,
  HarnessTraceV3,
} from "@vibe-learner/shared";

import { StrictResponseDecoder } from "./strict-response-decode.ts";
import { decodeHarnessTraceV3 } from "./harness-trace-decode.ts";

const DOCUMENT_STATUSES = ["uploaded", "processing", "processed", "failed"] as const;
const OCR_STATUSES = [
  "pending",
  "completed",
  "fallback_used",
  "forced",
  "required",
  "unavailable",
  "failed",
] as const satisfies readonly OcrStatus[];
const STUDY_UNIT_KINDS = [
  "chapter",
  "front_matter",
  "solutions",
  "back_matter",
] as const;
const EXTRACTION_SOURCES = [
  "text",
  "ocr",
  "ocr_attempted",
  "ocr_unavailable",
  "ocr_failed",
] as const;

export class DocumentDecodeError extends Error {
  readonly code = "document_response_decode_error";
  readonly path: string;
  readonly reason: string;

  constructor(path: string, reason: string) {
    super(`${reason} at ${path}`);
    this.name = "DocumentDecodeError";
    this.path = path;
    this.reason = reason;
  }
}

const decoder = new StrictResponseDecoder((path, reason) => {
  throw new DocumentDecodeError(path, reason);
});

interface DocumentScope {
  documentId: string;
  pageCount: number;
}

function decodeSection(
  raw: unknown,
  path: string,
  scope: DocumentScope,
): DocumentSection {
  const value = decoder.record(raw, path);
  const section: DocumentSection = {
    id: decoder.string(decoder.field(value, "id", path), `${path}.id`),
    documentId: decoder.string(
      decoder.field(value, "document_id", path),
      `${path}.document_id`,
    ),
    title: decoder.string(decoder.field(value, "title", path), `${path}.title`, true),
    pageStart: decoder.integer(
      decoder.field(value, "page_start", path),
      `${path}.page_start`,
      1,
    ),
    pageEnd: decoder.integer(
      decoder.field(value, "page_end", path),
      `${path}.page_end`,
      1,
    ),
    level: decoder.integer(decoder.field(value, "level", path), `${path}.level`, 1),
  };
  decoder.equal(section.documentId, scope.documentId, `${path}.document_id`);
  decoder.range(section.pageStart, section.pageEnd, `${path}.page_range`, scope.pageCount);
  return section;
}

function decodeSections(
  raw: unknown,
  path: string,
  scope: DocumentScope,
): DocumentSection[] {
  const sections = decoder.array(raw, path, (item, itemPath) =>
    decodeSection(item, itemPath, scope)
  );
  decoder.unique(sections.map((section) => section.id), `${path}.id`);
  decoder.nonDecreasing(sections.map((section) => section.pageStart), `${path}.page_start`);
  return sections;
}

function decodeStudyUnit(
  raw: unknown,
  path: string,
  scope: DocumentScope,
  allowedSourceSectionIds: ReadonlySet<string> | null,
): StudyUnit {
  const value = decoder.record(raw, path);
  const sourceSectionIds = decoder.stringArray(
    decoder.field(value, "source_section_ids", path),
    `${path}.source_section_ids`,
  );
  decoder.unique(sourceSectionIds, `${path}.source_section_ids`);
  for (const [index, sectionId] of sourceSectionIds.entries()) {
    if (allowedSourceSectionIds !== null && !allowedSourceSectionIds.has(sectionId)) {
      throw new DocumentDecodeError(
        `${path}.source_section_ids[${index}]`,
        "unknown_section_reference",
      );
    }
  }
  const unit: StudyUnit = {
    id: decoder.string(decoder.field(value, "id", path), `${path}.id`),
    documentId: decoder.string(
      decoder.field(value, "document_id", path),
      `${path}.document_id`,
    ),
    title: decoder.string(decoder.field(value, "title", path), `${path}.title`, true),
    pageStart: decoder.integer(
      decoder.field(value, "page_start", path),
      `${path}.page_start`,
      1,
    ),
    pageEnd: decoder.integer(
      decoder.field(value, "page_end", path),
      `${path}.page_end`,
      1,
    ),
    unitKind: decoder.enumeration(
      decoder.field(value, "unit_kind", path),
      STUDY_UNIT_KINDS,
      `${path}.unit_kind`,
    ),
    includeInPlan: decoder.boolean(
      decoder.field(value, "include_in_plan", path),
      `${path}.include_in_plan`,
    ),
    sourceSectionIds,
    summary: decoder.string(decoder.field(value, "summary", path), `${path}.summary`, true),
    confidence: decoder.finiteNumber(
      decoder.field(value, "confidence", path),
      `${path}.confidence`,
      0,
      1,
    ),
  };
  decoder.equal(unit.documentId, scope.documentId, `${path}.document_id`);
  decoder.range(unit.pageStart, unit.pageEnd, `${path}.page_range`, scope.pageCount);
  return unit;
}

function decodeStudyUnits(
  raw: unknown,
  path: string,
  scope: DocumentScope,
  sourceSections: DocumentSection[] | null,
): StudyUnit[] {
  const sourceSectionIds = sourceSections === null
    ? null
    : new Set(sourceSections.map((section) => section.id));
  const units = decoder.array(raw, path, (item, itemPath) =>
    decodeStudyUnit(item, itemPath, scope, sourceSectionIds)
  );
  decoder.unique(units.map((unit) => unit.id), `${path}.id`);
  decoder.nonDecreasing(units.map((unit) => unit.pageStart), `${path}.page_start`);
  return units;
}

function validateDocumentSectionProjection(
  sections: DocumentSection[],
  studyUnits: StudyUnit[],
  path: string,
): void {
  const projectedUnits = studyUnits.filter((unit) => unit.includeInPlan);
  decoder.equal(sections.length, projectedUnits.length, `${path}.sections`);
  for (const [index, section] of sections.entries()) {
    const unit = projectedUnits[index];
    if (
      unit === undefined ||
      section.id !== unit.id ||
      section.documentId !== unit.documentId ||
      section.title !== unit.title ||
      section.pageStart !== unit.pageStart ||
      section.pageEnd !== unit.pageEnd ||
      section.level !== 1
    ) {
      throw new DocumentDecodeError(
        `${path}.sections[${index}]`,
        "study_unit_section_projection_mismatch",
      );
    }
  }
}

export function decodeDocumentRecord(
  raw: unknown,
  expectedDocumentId?: string,
  path = "document",
  requireHarnessTrace = false,
): DocumentRecord {
  const value = decoder.record(raw, path);
  const id = decoder.string(decoder.field(value, "id", path), `${path}.id`);
  if (expectedDocumentId !== undefined) {
    decoder.equal(id, expectedDocumentId, `${path}.id`);
  }
  const pageCount = decoder.integer(
    decoder.field(value, "page_count", path),
    `${path}.page_count`,
  );
  const scope = { documentId: id, pageCount };
  const sections = decodeSections(decoder.field(value, "sections", path), `${path}.sections`, scope);
  const studyUnits = decodeStudyUnits(
    decoder.field(value, "study_units", path),
    `${path}.study_units`,
    scope,
    null,
  );
  validateDocumentSectionProjection(sections, studyUnits, path);
  const studyUnitCount = decoder.integer(
    decoder.field(value, "study_unit_count", path),
    `${path}.study_unit_count`,
  );
  decoder.equal(studyUnitCount, studyUnits.length, `${path}.study_unit_count`);

  let harnessTrace: HarnessTraceV3 | undefined;
  const rawTrace = value.harness_trace;
  if (requireHarnessTrace || (rawTrace !== undefined && rawTrace !== null)) {
    const decodedTrace = decodeHarnessTraceV3(
      decoder.field(value, "harness_trace", path),
      `${path}.harness_trace`,
      (tracePath, reason) => { throw new DocumentDecodeError(tracePath, reason); },
    );
    if (decodedTrace.workflow !== "document_parse" || decodedTrace.stage !== "document_parse" || !["passed", "repaired"].includes(decodedTrace.status) || decodedTrace.commitEvidence.status !== "committed") {
      throw new DocumentDecodeError(
        `${path}.harness_trace`,
        "document_process_harness_trace_invalid",
      );
    }
    harnessTrace = decodedTrace;
  }

  return {
    id,
    title: decoder.string(decoder.field(value, "title", path), `${path}.title`, true),
    originalFilename: decoder.string(
      decoder.field(value, "original_filename", path),
      `${path}.original_filename`,
    ),
    storedPath: decoder.string(
      decoder.field(value, "stored_path", path),
      `${path}.stored_path`,
    ),
    status: decoder.enumeration(
      decoder.field(value, "status", path),
      DOCUMENT_STATUSES,
      `${path}.status`,
    ),
    ocrStatus: decoder.enumeration(
      decoder.field(value, "ocr_status", path),
      OCR_STATUSES,
      `${path}.ocr_status`,
    ),
    createdAt: decoder.string(
      decoder.field(value, "created_at", path),
      `${path}.created_at`,
    ),
    updatedAt: decoder.string(
      decoder.field(value, "updated_at", path),
      `${path}.updated_at`,
    ),
    sections,
    studyUnits,
    studyUnitCount,
    pageCount,
    chunkCount: decoder.integer(
      decoder.field(value, "chunk_count", path),
      `${path}.chunk_count`,
    ),
    previewExcerpt: decoder.string(
      decoder.field(value, "preview_excerpt", path),
      `${path}.preview_excerpt`,
      true,
    ),
    debugReady: decoder.boolean(
      decoder.field(value, "debug_ready", path),
      `${path}.debug_ready`,
    ),
    ...(harnessTrace ? { harnessTrace } : {}),
  };
}

export function decodeDocumentList(raw: unknown): DocumentRecord[] {
  const path = "documents";
  const value = decoder.record(raw, path);
  const documents = decoder.array(
    decoder.field(value, "items", path),
    `${path}.items`,
    (item, itemPath) => decodeDocumentRecord(item, undefined, itemPath),
  );
  decoder.unique(documents.map((document) => document.id), `${path}.items.id`);
  return documents;
}

function decodeHeadingCandidate(
  raw: unknown,
  path: string,
  pageNumber: number,
) {
  const value = decoder.record(raw, path);
  const candidatePageNumber = decoder.integer(
    decoder.field(value, "page_number", path),
    `${path}.page_number`,
    1,
  );
  decoder.equal(candidatePageNumber, pageNumber, `${path}.page_number`);
  return {
    pageNumber: candidatePageNumber,
    text: decoder.string(decoder.field(value, "text", path), `${path}.text`, true),
    fontSize: decoder.finiteNumber(
      decoder.field(value, "font_size", path),
      `${path}.font_size`,
      0,
    ),
    confidence: decoder.finiteNumber(
      decoder.field(value, "confidence", path),
      `${path}.confidence`,
      0,
      1,
    ),
  };
}

function decodePage(raw: unknown, path: string, expectedPageNumber: number): DocumentPageRecord {
  const value = decoder.record(raw, path);
  const pageNumber = decoder.integer(
    decoder.field(value, "page_number", path),
    `${path}.page_number`,
    1,
  );
  decoder.equal(pageNumber, expectedPageNumber, `${path}.page_number`);
  return {
    pageNumber,
    charCount: decoder.integer(
      decoder.field(value, "char_count", path),
      `${path}.char_count`,
    ),
    wordCount: decoder.integer(
      decoder.field(value, "word_count", path),
      `${path}.word_count`,
    ),
    textPreview: decoder.string(
      decoder.field(value, "text_preview", path),
      `${path}.text_preview`,
      true,
    ),
    dominantFontSize: decoder.finiteNumber(
      decoder.field(value, "dominant_font_size", path),
      `${path}.dominant_font_size`,
      0,
    ),
    extractionSource: decoder.enumeration(
      decoder.field(value, "extraction_source", path),
      EXTRACTION_SOURCES,
      `${path}.extraction_source`,
    ),
    headingCandidates: decoder.array(
      decoder.field(value, "heading_candidates", path),
      `${path}.heading_candidates`,
      (item, itemPath) => decodeHeadingCandidate(item, itemPath, pageNumber),
    ),
  };
}

function decodeChunk(
  raw: unknown,
  path: string,
  scope: DocumentScope,
  sectionIds: ReadonlySet<string>,
): DocumentChunkRecord {
  const value = decoder.record(raw, path);
  const sectionId = decoder.string(
    decoder.field(value, "section_id", path),
    `${path}.section_id`,
  );
  if (!sectionIds.has(sectionId)) {
    throw new DocumentDecodeError(`${path}.section_id`, "unknown_section_reference");
  }
  const chunk: DocumentChunkRecord = {
    id: decoder.string(decoder.field(value, "id", path), `${path}.id`),
    documentId: decoder.string(
      decoder.field(value, "document_id", path),
      `${path}.document_id`,
    ),
    sectionId,
    pageStart: decoder.integer(
      decoder.field(value, "page_start", path),
      `${path}.page_start`,
      1,
    ),
    pageEnd: decoder.integer(
      decoder.field(value, "page_end", path),
      `${path}.page_end`,
      1,
    ),
    charCount: decoder.integer(
      decoder.field(value, "char_count", path),
      `${path}.char_count`,
    ),
    textPreview: decoder.string(
      decoder.field(value, "text_preview", path),
      `${path}.text_preview`,
      true,
    ),
    content: decoder.string(decoder.field(value, "content", path), `${path}.content`, true),
  };
  decoder.equal(chunk.documentId, scope.documentId, `${path}.document_id`);
  decoder.range(chunk.pageStart, chunk.pageEnd, `${path}.page_range`, scope.pageCount);
  return chunk;
}

function decodeWarning(
  raw: unknown,
  path: string,
  pageCount: number,
): ParseWarning {
  const value = decoder.record(raw, path);
  const rawPageNumber = decoder.field(value, "page_number", path);
  const pageNumber = decoder.nullable(rawPageNumber, `${path}.page_number`, (item, itemPath) =>
    decoder.integer(item, itemPath, 1, pageCount)
  );
  return {
    code: decoder.string(decoder.field(value, "code", path), `${path}.code`),
    message: decoder.string(decoder.field(value, "message", path), `${path}.message`, true),
    pageNumber,
  };
}

function decodeNullableStringField(
  value: Record<string, unknown>,
  key: string,
  path: string,
): string | null {
  const fieldPath = `${path}.${key}`;
  return decoder.nullable(decoder.field(value, key, path), fieldPath, (item, itemPath) =>
    decoder.string(item, itemPath, true)
  );
}

export function decodeDocumentDebugRecord(
  raw: unknown,
  expectedDocumentId?: string,
  path = "document_debug",
): DocumentDebugRecord {
  const value = decoder.record(raw, path);
  const documentId = decoder.string(
    decoder.field(value, "document_id", path),
    `${path}.document_id`,
  );
  if (expectedDocumentId !== undefined) {
    decoder.equal(documentId, expectedDocumentId, `${path}.document_id`);
  }
  const pageCount = decoder.integer(
    decoder.field(value, "page_count", path),
    `${path}.page_count`,
  );
  const scope = { documentId, pageCount };
  const pages = decoder.array(
    decoder.field(value, "pages", path),
    `${path}.pages`,
    (item, itemPath, index) => decodePage(item, itemPath, index + 1),
  );
  decoder.equal(pages.length, pageCount, `${path}.pages`);
  const sections = decodeSections(decoder.field(value, "sections", path), `${path}.sections`, scope);
  const studyUnits = decodeStudyUnits(
    decoder.field(value, "study_units", path),
    `${path}.study_units`,
    scope,
    sections,
  );
  const sectionIds = new Set(sections.map((section) => section.id));
  const chunks = decoder.array(
    decoder.field(value, "chunks", path),
    `${path}.chunks`,
    (item, itemPath) => decodeChunk(item, itemPath, scope, sectionIds),
  );
  decoder.unique(chunks.map((chunk) => chunk.id), `${path}.chunks.id`);
  decoder.nonDecreasing(chunks.map((chunk) => chunk.pageStart), `${path}.chunks.page_start`);
  const ocrAppliedPageCount = decoder.integer(
    decoder.field(value, "ocr_applied_page_count", path),
    `${path}.ocr_applied_page_count`,
    0,
    pageCount,
  );

  return {
    documentId,
    parserName: decoder.string(
      decoder.field(value, "parser_name", path),
      `${path}.parser_name`,
    ),
    processedAt: decoder.string(
      decoder.field(value, "processed_at", path),
      `${path}.processed_at`,
    ),
    pageCount,
    totalCharacters: decoder.integer(
      decoder.field(value, "total_characters", path),
      `${path}.total_characters`,
    ),
    extractionMethod: decoder.string(
      decoder.field(value, "extraction_method", path),
      `${path}.extraction_method`,
    ),
    ocrStatus: decoder.enumeration(
      decoder.field(value, "ocr_status", path),
      OCR_STATUSES,
      `${path}.ocr_status`,
    ),
    ocrApplied: decoder.boolean(
      decoder.field(value, "ocr_applied", path),
      `${path}.ocr_applied`,
    ),
    ocrLanguage: decodeNullableStringField(value, "ocr_language", path),
    ocrEngine: decodeNullableStringField(value, "ocr_engine", path),
    ocrModelId: decodeNullableStringField(value, "ocr_model_id", path),
    ocrAppliedPageCount,
    ocrWarnings: decoder.stringArray(
      decoder.field(value, "ocr_warnings", path),
      `${path}.ocr_warnings`,
      true,
    ),
    pages,
    sections,
    studyUnits,
    chunks,
    warnings: decoder.array(
      decoder.field(value, "warnings", path),
      `${path}.warnings`,
      (item, itemPath) => decodeWarning(item, itemPath, pageCount),
    ),
    dominantLanguageHint: decoder.string(
      decoder.field(value, "dominant_language_hint", path),
      `${path}.dominant_language_hint`,
      true,
    ),
  };
}
