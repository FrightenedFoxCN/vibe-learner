import type { StudyUnitRevision, StudyUnitSuggestion } from "@vibe-learner/shared";
import { StrictResponseDecoder } from "./strict-response-decode.ts";
import { decodeDocumentRecord } from "./document-decode.ts";
import { PlanningDecodeError } from "./planning-decode.ts";

const fail = (path: string, reason: string): never => { throw new PlanningDecodeError(path, reason); };
const d = new StrictResponseDecoder(fail);
function exact(value: Record<string, unknown>, keys: string[], path: string) {
  for (const key of Object.keys(value)) if (!keys.includes(key)) fail(`${path}.${key}`, "unexpected_field");
  for (const key of keys) d.field(value, key, path);
}
function bounded(raw: unknown, path: string, limit: number, empty = false) {
  const value = d.string(raw, path, empty);
  if (Array.from(value).length > limit || (!empty && !value.trim())) fail(path, "invalid_string");
  return value;
}

export function decodeStudyUnitRevision(raw: unknown, planId: string, documentId: string): StudyUnitRevision {
  const p = "study_unit_revision";
  const v = d.record(raw, p);
  exact(v, ["preview", "status", "result", "planning_context_revision", "error_code"], p);
  const preview = d.record(v.preview, `${p}.preview`);
  exact(preview, ["schema_version", "operation_id", "plan_id", "parent_operation_id", "base_document", "base_debug_digest", "suggestions"], `${p}.preview`);
  d.equal(preview.schema_version, "study-unit-revision-preview-v1", p);
  d.equal(preview.plan_id, planId, p);
  const operationId = d.string(preview.operation_id, p);
  if (!/^unit-revision-[a-f0-9]{32}$/.test(operationId)) fail(p, "invalid_operation_id");
  const parentOperationId = d.string(preview.parent_operation_id, p);
  const baseDebugDigest = d.string(preview.base_debug_digest, p);
  if (!/^[a-f0-9]{64}$/.test(baseDebugDigest)) fail(p, "invalid_digest");
  const baseDocument = decodeDocumentRecord(preview.base_document, documentId);
  const suggestions = d.record(preview.suggestions, `${p}.suggestions`);
  exact(suggestions, ["study_units", "rationale"], `${p}.suggestions`);
  const studyUnits = d.array(suggestions.study_units, `${p}.suggestions.study_units`, (raw, path): StudyUnitSuggestion => {
    const unit = d.record(raw, path);
    exact(unit, ["title", "page_start", "page_end", "unit_kind", "include_in_plan", "summary"], path);
    const result = {
      title: bounded(unit.title, `${path}.title`, 500),
      pageStart: d.integer(unit.page_start, `${path}.page_start`, 1),
      pageEnd: d.integer(unit.page_end, `${path}.page_end`, 1),
      unitKind: d.enumeration(unit.unit_kind, ["chapter", "front_matter", "solutions", "back_matter"] as const, `${path}.unit_kind`),
      includeInPlan: d.boolean(unit.include_in_plan, `${path}.include_in_plan`),
      summary: bounded(unit.summary, `${path}.summary`, 2000, true),
    };
    d.range(result.pageStart, result.pageEnd, path, baseDocument.pageCount);
    return result;
  });
  if (!studyUnits.length || studyUnits.length > 24 || !studyUnits.some(unit => unit.includeInPlan)) fail(p, "invalid_unit_count");
  studyUnits.forEach((unit, index) => {
    if (index && unit.pageStart <= studyUnits[index - 1].pageEnd) fail(p, "units_overlap_or_unordered");
  });
  const status = d.enumeration(v.status, ["ready", "applying", "accepted", "rejected", "conflict", "failed"] as const, `${p}.status`);
  const result = d.nullable(v.result, `${p}.result`, value => decodeDocumentRecord(value, documentId));
  const planningContextRevision = d.nullable(v.planning_context_revision, p, value => d.integer(value, p));
  if ((status === "accepted") !== (result !== null) || (result === null) !== (planningContextRevision === null)) fail(p, "result_status_mismatch");
  if (result) {
    if (result.revision !== baseDocument.revision + 1 || planningContextRevision !== result.revision || result.studyUnits.length !== studyUnits.length) fail(p, "committed_revision_mismatch");
    result.studyUnits.forEach((unit, index) => {
      const suggestion = studyUnits[index];
      const old = baseDocument.studyUnits.filter(before => before.pageStart === suggestion.pageStart && before.pageEnd === suggestion.pageEnd);
      const expectedId = old.length === 1 ? old[0].id : `${documentId}:unit:${operationId}:${index + 1}`;
      if (unit.id !== expectedId || unit.title !== suggestion.title.trim() || unit.pageStart !== suggestion.pageStart || unit.pageEnd !== suggestion.pageEnd || unit.unitKind !== suggestion.unitKind || unit.includeInPlan !== suggestion.includeInPlan || unit.summary !== suggestion.summary || unit.confidence !== (old.length === 1 ? old[0].confidence : 0.95)) fail(p, "committed_unit_mismatch");
    });
    const expected = { ...baseDocument, revision: result.revision, updatedAt: result.updatedAt,
      sections: result.sections, studyUnits: result.studyUnits, studyUnitCount: result.studyUnitCount };
    if (JSON.stringify(result) !== JSON.stringify(expected)) fail(p, "committed_document_mismatch");
  }
  return { preview: { operationId, planId, parentOperationId, baseDocument, baseDebugDigest,
    suggestions: { studyUnits, rationale: bounded(suggestions.rationale, p, 2000, true) } }, status, result, planningContextRevision,
    errorCode: d.string(v.error_code, `${p}.error_code`, true) };
}
