import assert from "node:assert/strict";
import test from "node:test";

import {
  decodeDocumentDebugRecord,
  decodeDocumentList,
  decodeDocumentRecord,
  DocumentDecodeError,
} from "../lib/document-decode.ts";

function wireSection(id = "section-1", pageStart = 1, pageEnd = 2) {
  return {
    id,
    document_id: "document-1",
    title: `Section ${id}`,
    page_start: pageStart,
    page_end: pageEnd,
    level: 1,
  };
}

function wireStudyUnit(id = "unit-1", pageStart = 1, pageEnd = 2) {
  return {
    id,
    document_id: "document-1",
    title: `Unit ${id}`,
    page_start: pageStart,
    page_end: pageEnd,
    unit_kind: "chapter",
    include_in_plan: true,
    source_section_ids: ["section-1"],
    summary: "Summary",
    confidence: 0.9,
  };
}

function wireProjectedSection(unit = wireStudyUnit()) {
  return {
    id: unit.id,
    document_id: unit.document_id,
    title: unit.title,
    page_start: unit.page_start,
    page_end: unit.page_end,
    level: 1,
  };
}

function wireDocument() {
  return {
    id: "document-1",
    title: "Document",
    original_filename: "document.pdf",
    stored_path: "/protected/document.pdf",
    status: "processed",
    ocr_status: "completed",
    created_at: "2026-08-24T00:00:00Z",
    updated_at: "2026-08-24T00:01:00Z",
    sections: [wireProjectedSection()],
    study_units: [wireStudyUnit()],
    study_unit_count: 1,
    page_count: 2,
    chunk_count: 1,
    preview_excerpt: "Preview",
    debug_ready: true,
  };
}

function wireDebug() {
  return {
    document_id: "document-1",
    parser_name: "pymupdf",
    processed_at: "2026-08-24T00:01:00Z",
    page_count: 2,
    total_characters: 20,
    extraction_method: "text",
    ocr_status: "completed",
    ocr_applied: false,
    ocr_language: null,
    ocr_engine: null,
    ocr_model_id: null,
    ocr_applied_page_count: 0,
    ocr_warnings: [],
    pages: [
      {
        page_number: 1,
        char_count: 10,
        word_count: 2,
        text_preview: "Page 1",
        dominant_font_size: 12,
        extraction_source: "text",
        heading_candidates: [
          { page_number: 1, text: "Heading", font_size: 16, confidence: 0.8 },
        ],
      },
      {
        page_number: 2,
        char_count: 10,
        word_count: 2,
        text_preview: "Page 2",
        dominant_font_size: 12,
        extraction_source: "text",
        heading_candidates: [],
      },
    ],
    sections: [wireSection()],
    study_units: [wireStudyUnit()],
    chunks: [
      {
        id: "chunk-1",
        document_id: "document-1",
        section_id: "section-1",
        page_start: 1,
        page_end: 2,
        char_count: 20,
        text_preview: "Chunk",
        content: "Chunk content",
      },
    ],
    warnings: [{ code: "notice", message: "Notice", page_number: null }],
    dominant_language_hint: "zh",
  };
}

test("Document decoder accepts a coherent committed projection and list envelope", () => {
  const document = decodeDocumentRecord(wireDocument(), "document-1");
  assert.equal(document.sections[0]?.documentId, "document-1");
  assert.equal(document.studyUnits[0]?.sourceSectionIds[0], "section-1");
  assert.deepEqual(decodeDocumentList({ items: [wireDocument()] }), [document]);
});

test("Document decoder rejects wrong identity, status, count, and scalar coercion", () => {
  assert.throws(
    () => decodeDocumentRecord(wireDocument(), "document-other"),
    (error: unknown) =>
      error instanceof DocumentDecodeError && error.path === "document.id",
  );
  for (const mutation of [
    { status: "done" },
    { page_count: "2" },
    { debug_ready: 1 },
    { study_unit_count: 2 },
  ]) {
    assert.throws(
      () => decodeDocumentRecord({ ...wireDocument(), ...mutation }),
      DocumentDecodeError,
    );
  }
});

test("Document decoder rejects unordered, duplicate, reversed, and drifted projected sections", () => {
  const secondUnit = {
    ...wireStudyUnit("unit-2", 2, 2),
    source_section_ids: ["section-2"],
  };
  const firstProjectedSection = wireProjectedSection();
  const secondProjectedSection = wireProjectedSection(secondUnit);
  const base = {
    ...wireDocument(),
    sections: [firstProjectedSection, secondProjectedSection],
    study_units: [wireStudyUnit(), secondUnit],
    study_unit_count: 2,
  };
  assert.throws(
    () => decodeDocumentRecord({
      ...base,
      sections: [secondProjectedSection, firstProjectedSection],
    }),
    (error: unknown) =>
      error instanceof DocumentDecodeError &&
      error.reason === "expected_non_decreasing_order",
  );
  assert.throws(
    () => decodeDocumentRecord({
      ...base,
      sections: [firstProjectedSection, firstProjectedSection],
    }),
    DocumentDecodeError,
  );
  assert.throws(
    () => decodeDocumentRecord({
      ...wireDocument(),
      study_units: [{ ...wireStudyUnit(), page_start: 2, page_end: 1 }],
    }),
    DocumentDecodeError,
  );
  assert.throws(
    () => decodeDocumentRecord({
      ...wireDocument(),
      sections: [{ ...wireProjectedSection(), title: "Forged" }],
    }),
    (error: unknown) =>
      error instanceof DocumentDecodeError &&
      error.reason === "study_unit_section_projection_mismatch",
  );
  assert.doesNotThrow(() => decodeDocumentRecord({
    ...wireDocument(),
    study_units: [{ ...wireStudyUnit(), source_section_ids: ["raw-section-not-projected"] }],
  }));
});

test("Document decoder rejects non-finite confidence", () => {
  assert.throws(
    () => decodeDocumentRecord({
      ...wireDocument(),
      study_units: [{ ...wireStudyUnit(), confidence: Number.NaN }],
    }),
    (error: unknown) =>
      error instanceof DocumentDecodeError &&
      error.path === "document.study_units[0].confidence",
  );
});

test("Document Debug decoder validates page order, ranges, chunk refs, and nullability", () => {
  const debug = decodeDocumentDebugRecord(wireDebug(), "document-1");
  assert.equal(debug.pages[1]?.pageNumber, 2);
  assert.equal(debug.warnings[0]?.pageNumber, null);

  const attacks = [
    {
      ...wireDebug(),
      pages: [wireDebug().pages[1], wireDebug().pages[0]],
    },
    {
      ...wireDebug(),
      chunks: [{ ...wireDebug().chunks[0], section_id: "missing" }],
    },
    {
      ...wireDebug(),
      chunks: [{ ...wireDebug().chunks[0], page_end: 3 }],
    },
    {
      ...wireDebug(),
      study_units: [{ ...wireStudyUnit(), source_section_ids: ["missing"] }],
    },
    { ...wireDebug(), ocr_engine: 7 },
    { ...wireDebug(), warnings: [{ code: "notice", message: "Notice", page_number: "1" }] },
    { ...wireDebug(), ocr_applied_page_count: 3 },
  ];
  for (const attack of attacks) {
    assert.throws(
      () => decodeDocumentDebugRecord(attack, "document-1"),
      DocumentDecodeError,
    );
  }
});

test("Document Debug decoder rejects duplicate and unordered chunks", () => {
  const laterChunk = {
    ...wireDebug().chunks[0],
    id: "chunk-2",
    page_start: 2,
    page_end: 2,
  };
  assert.throws(
    () => decodeDocumentDebugRecord({
      ...wireDebug(),
      chunks: [wireDebug().chunks[0], { ...wireDebug().chunks[0] }],
    }),
    DocumentDecodeError,
  );
  assert.throws(
    () => decodeDocumentDebugRecord({
      ...wireDebug(),
      chunks: [laterChunk, wireDebug().chunks[0]],
    }),
    (error: unknown) =>
      error instanceof DocumentDecodeError &&
      error.reason === "expected_non_decreasing_order",
  );
});
