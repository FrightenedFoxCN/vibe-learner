import { wireUnit } from "./learning-wire.ts";

export function wireUnitRevision(accepted = false) {
  const unit = wireUnit();
  const section = { id: unit.id, document_id: unit.document_id, title: unit.title,
    page_start: unit.page_start, page_end: unit.page_end, level: 1 };
  const document = { id: unit.document_id, revision: 3, title: "Textbook", original_filename: "textbook.pdf", stored_path: "/textbook.pdf",
    status: "processed", ocr_status: "not_required", created_at: "2026-10-29T00:00:00Z", updated_at: "2026-10-29T00:00:00Z",
    sections: [section], study_units: [unit], study_unit_count: 1, page_count: 2, chunk_count: 1, preview_excerpt: "Content", debug_ready: true };
  return {
    preview: { schema_version: "study-unit-revision-preview-v1", operation_id: `unit-revision-${"a".repeat(32)}`,
      plan_id: "plan-1", parent_operation_id: "plan-operation-1", base_document: document, base_debug_digest: "b".repeat(64),
      suggestions: { study_units: [{ title: "Revised unit", page_start: 1, page_end: 2, unit_kind: "chapter", include_in_plan: true, summary: "Revised summary" }], rationale: "Clarify the title" } },
    status: accepted ? "accepted" : "ready",
    result: accepted ? { ...document, revision: 4, updated_at: "2026-10-29T00:01:00Z", sections: [{ ...section, title: "Revised unit" }],
      study_units: [{ ...unit, title: "Revised unit", summary: "Revised summary" }] } : null,
    planning_context_revision: accepted ? 4 : null, error_code: "",
  };
}
