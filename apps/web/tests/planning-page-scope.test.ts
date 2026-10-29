import assert from "node:assert/strict";
import test from "node:test";
import {
  parsePhysicalPdfRanges,
  physicalPageIntent,
} from "../lib/planning-page-scope.ts";
import { decodeDocumentPageNumbering } from "../lib/document-page-numbering-decode.ts";

test("physical range input is explicit and never infers printed-page offsets", () => {
  assert.deepEqual(parsePhysicalPdfRanges("100–103, 110"), [
    { pageStart: 100, pageEnd: 103 },
    { pageStart: 110, pageEnd: 110 },
  ]);
  assert.equal(
    physicalPageIntent(parsePhysicalPdfRanges("100-103"))?.pdfPageRanges.status,
    "user_explicit",
  );
  assert.equal(physicalPageIntent([]), undefined);
  for (const invalid of [
    "0-3",
    "103-100",
    "100-103,102-105",
    "iv-viii",
    "印刷 70-73",
    "100,",
    "1.5",
    String(Number.MAX_SAFE_INTEGER + 1),
  ])
    assert.throws(() => parsePhysicalPdfRanges(invalid));
});

test("numbering DTO binds physical pages and keeps missing printed labels null", () => {
  const raw = {
    contract_version: "document-page-numbering-v1",
    coordinate_system: "pdf_physical_1_based",
    document_id: "doc",
    document_revision: 2,
    physical_page_count: 104,
    pages: [
      { physical_pdf_page: 100, printed_page: { label: "70", source: "pdf_metadata" } },
      { physical_pdf_page: 103, printed_page: null },
    ],
  };
  const decoded = decodeDocumentPageNumbering(raw, "doc", [100, 103]);
  assert.equal(decoded.pages[0].physicalPdfPage, 100);
  assert.equal(decoded.pages[0].printedPage?.label, "70");
  assert.equal(decoded.pages[1].printedPage, null);
  for (const mutation of [
    { ...raw, coordinate_system: "printed" },
    { ...raw, pages: [{ physical_pdf_page: 70, printed_page: null }] },
    { ...raw, document_revision: "2" },
  ])
    assert.throws(() => decodeDocumentPageNumbering(mutation, "doc", [100, 103]));
});

test("public Plan decoder rejects anchors or slices outside a saved physical scope", async () => {
  const { wirePlan } = await import("./support/learning-wire.ts");
  const { decodeLearningPlan } = await import("../lib/planning-decode.ts");
  const raw = wirePlan();
  raw.study_units[0].page_end = 104;
  const chapter = raw.schedule[0].schedule_chapters[0];
  chapter.anchor_page_start = 100;
  chapter.anchor_page_end = 103;
  chapter.content_slices = [
    { page_start: 100, page_end: 103, source_section_ids: ["section-1"] },
  ];
  Object.assign(raw, {
    planning_intent: {
      schema_version: "planning-intent-v1",
      pdf_page_ranges: {
        status: "user_explicit",
        value: [{ page_start: 100, page_end: 103 }],
      },
      outline_targets: { status: "unknown", value: null },
      session_count: { status: "unknown", value: null },
      minutes_per_session: { status: "unknown", value: null },
      output_language: { status: "unknown", value: null },
    },
  });
  assert.equal(
    decodeLearningPlan(raw).schedule[0].scheduleChapters[0].anchorPageStart,
    100,
  );
  chapter.anchor_page_start = 70;
  assert.throws(() => decodeLearningPlan(raw));
});
