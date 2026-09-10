import type { DiagnosticEventFilters, DiagnosticExportV1 } from "@vibe-learner/shared";
import schema from "../../../packages/shared/fixtures/diagnostics/export-schema-v1.json";
import { classifyDiagnostic } from "../../../packages/shared/src/diagnostic.ts";
import { DiagnosticQueryError, decodeDiagnosticWriters, requestDiagnosticExport, validateDiagnosticExportSchema } from "./diagnostic-query";

const invalid = (): never => { throw new DiagnosticQueryError("invalid_response"); };
export function decodeDiagnosticExport(raw: unknown, filters: DiagnosticEventFilters): DiagnosticExportV1 {
  validateDiagnosticExportSchema(raw, schema);
  const value = raw as DiagnosticExportV1;
  const normalize = (input: object) => JSON.stringify(Object.entries(input).filter(([, v]) => v != null && v !== "").sort(([a], [b]) => a.localeCompare(b)).map(([key, v]) => [key, key === "since" || key === "until" ? new Date(v as string).toISOString() : v]));
  if (normalize(value.filters) !== normalize(filters)) invalid();
  const ids = new Set<string>();
  let sequence = 0;
  for (const row of value.events) {
    if (row.sequence <= sequence || ids.has(row.event.event_id)) invalid();
    sequence = row.sequence;
    ids.add(row.event.event_id);
    const classification = classifyDiagnostic(row.event.name, row.event.status_code);
    for (const key of ["category", "severity", "outcome", "error_code"] as const) if (row.event[key] !== classification[key]) invalid();
  }
  if (value.retention.retained_events < value.events.length || value.retention.cursor_gap !== (value.retention.removed_through_sequence > 0)) invalid();
  const traces = new Set<string>();
  for (const trace of value.index) { if (traces.has(trace.trace_id)) invalid(); traces.add(trace.trace_id); }
  const links = new Set<string>();
  for (const link of value.operation_links) {
    const id = JSON.stringify([link.operation_id, link.request_id]);
    if (links.has(id)) invalid(); links.add(id);
  }
  let after = 0;
  const writers = new Set<string>();
  const totals = JSON.stringify(value.writer_pages[0].totals);
  for (const [i, page] of value.writer_pages.entries()) {
    decodeDiagnosticWriters(page, after);
    if (page.has_more !== (i < value.writer_pages.length - 1) || JSON.stringify(page.totals) !== totals) invalid();
    for (const item of page.items) { if (writers.has(item.epoch_id)) invalid(); writers.add(item.epoch_id); }
    after = page.next_cursor;
  }
  if (writers.size !== value.writer_pages[0].totals.retained_epochs) invalid();
  if (value.index_coverage.freshness === "unavailable" && (value.index.length || value.index_coverage.cursor !== null || value.index_coverage.completed_sweeps !== null)) invalid();
  if (value.index_coverage.freshness === "eventual" && (value.index_coverage.cursor === null || value.index_coverage.completed_sweeps === null)) invalid();
  if (value.audit.input_event_count !== value.events.length || value.audit.input_trace_count !== value.index.length || value.audit.duplicate_event_count !== 0) invalid();
  const samples = new Set<string>();
  for (const item of value.audit.observations) {
    if (samples.has(item.sample_id) || item.event_ids.some(id => !ids.has(id))) invalid();
    samples.add(item.sample_id);
  }
  let grouped = 0;
  for (const group of value.audit.groups) {
    if (group.sample_count !== group.completed_count + group.failed_count + group.cancelled_count + group.unknown_count + group.skipped_count || group.duration_sample_count > group.sample_count || group.recovered_count > group.sample_count ||
        (group.duration_sample_count === 0 ? group.p50_ms !== null || group.p95_ms !== null : group.p50_ms === null || group.p95_ms === null) || (group.p50_ms !== null && group.p95_ms !== null && group.p50_ms > group.p95_ms)) invalid();
    grouped += group.sample_count;
  }
  if (grouped !== samples.size) invalid();
  return value;
}
export async function queryDiagnosticExport(filters: DiagnosticEventFilters, signal?: AbortSignal) {
  const result = decodeDiagnosticExport(await requestDiagnosticExport(filters, signal), filters);
  signal?.throwIfAborted();
  return result;
}
