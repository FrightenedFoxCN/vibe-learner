import type { DiagnosticEventFilters, DiagnosticEventPageV1, DiagnosticHarnessIndexV1, DiagnosticOperationLinkV1 } from "@vibe-learner/shared";
import { classifyDiagnostic } from "../../../packages/shared/src/diagnostic.ts";
import schemas from "../../../packages/shared/fixtures/diagnostics/query-schemas-v1.json";
import { getAiBaseUrl } from "./runtime-config";

export class DiagnosticQueryError extends Error {
  constructor(public readonly code: "unavailable" | "invalid_response" | "response_too_large") { super(`diagnostic_query_${code}`); }
}
const invalid = (): never => { throw new DiagnosticQueryError("invalid_response"); };
type Schema = Record<string, any>;
const keywords = new Set(["$ref", "$defs", "title", "description", "default", "type", "anyOf", "const", "enum", "properties", "required", "additionalProperties", "items", "minItems", "maxItems", "minLength", "maxLength", "pattern", "minimum", "maximum"]);

/** Only the checked-in Pydantic schema subset is executable; unknown keywords fail closed. */
function validate(value: unknown, schema: Schema, root: Schema, depth = 0): void {
  if (depth > 32 || Object.keys(schema).some(key => !keywords.has(key))) invalid();
  if (schema.$ref) {
    const match = /^#\/\$defs\/([A-Za-z0-9_]+)$/.exec(schema.$ref);
    if (!match || !Object.hasOwn(root.$defs ?? {}, match[1])) invalid();
    return validate(value, root.$defs[match![1]], root, depth + 1);
  }
  if (schema.anyOf) {
    for (const branch of schema.anyOf) {
      try { validate(value, branch, root, depth + 1); return; } catch (error) { if (!(error instanceof DiagnosticQueryError)) throw error; }
    }
    invalid();
  }
  if (Object.hasOwn(schema, "const") && value !== schema.const) invalid();
  if (schema.enum && !schema.enum.includes(value)) invalid();
  switch (schema.type) {
    case "null": if (value !== null) invalid(); break;
    case "boolean": if (typeof value !== "boolean") invalid(); break;
    case "string":
      if (typeof value !== "string" || value.length > (schema.maxLength ?? 4096) || value.length < (schema.minLength ?? 0) || (schema.pattern && !new RegExp(schema.pattern).test(value))) invalid();
      break;
    case "integer": case "number":
      if (typeof value !== "number" || !Number.isFinite(value) || (schema.type === "integer" && !Number.isSafeInteger(value)) || value < (schema.minimum ?? -Number.MAX_SAFE_INTEGER) || value > (schema.maximum ?? Number.MAX_SAFE_INTEGER)) invalid();
      break;
    case "array":
      if (!Array.isArray(value) || value.length > (schema.maxItems ?? 1000) || value.length < (schema.minItems ?? 0)) invalid();
      for (const item of value as unknown[]) validate(item, schema.items, root, depth + 1);
      break;
    case "object": {
      const object = record(value);
      if (schema.additionalProperties !== false) invalid();
      if (Object.keys(object).some(key => !Object.hasOwn(schema.properties, key))) invalid();
      for (const key of schema.required ?? []) if (!Object.hasOwn(object, key)) invalid();
      for (const [key, item] of Object.entries(object)) validate(item, schema.properties[key], root, depth + 1);
      break;
    }
    case undefined: if (!Object.hasOwn(schema, "const") && !schema.enum) invalid(); break;
    default: invalid();
  }
}
function record(value: unknown): Record<string, any> {
  if (!value || typeof value !== "object" || Array.isArray(value)) return invalid();
  return value as Record<string, any>;
}
function exact(value: unknown, keys: string[]) {
  const object = record(value);
  if (Object.keys(object).length !== keys.length || keys.some(key => !Object.hasOwn(object, key))) invalid();
  return object;
}
function count(value: unknown): asserts value is number { if (!Number.isSafeInteger(value) || (value as number) < 0) invalid(); }
function page(value: unknown, cursor: unknown, after: number | string, hasMore: unknown) {
  if (!Array.isArray(value) || value.length > 100 || typeof hasMore !== "boolean" || typeof cursor !== typeof after || (hasMore && value.length === 0)) invalid();
}
export function decodeDiagnosticEvents(raw: unknown, after = 0): DiagnosticEventPageV1 {
  const value = exact(raw, ["items", "next_cursor", "has_more", "health", "desktop_spool"]);
  page(value.items, value.next_cursor, after, value.has_more);
  count(value.next_cursor);
  const ids = new Set<string>();
  let previous = after;
  for (const item of value.items) {
    const row = exact(item, ["sequence", "event"]);
    count(row.sequence);
    if (row.sequence <= previous) invalid();
    previous = row.sequence;
    validate(row.event, schemas.event, schemas.event);
    const event = row.event;
    if (ids.has(event.event_id)) invalid();
    ids.add(event.event_id);
    const classification = classifyDiagnostic(event.name, event.status_code);
    for (const [key, expected] of Object.entries(classification)) if (event[key] !== expected) invalid();
    const attempt = event.harness;
    if (attempt && [attempt.attempt_id, attempt.attempt_index, attempt.phase, attempt.attempt_status].some(v => v != null) &&
        [attempt.trace_id, attempt.attempt_id, attempt.attempt_index, attempt.phase, attempt.attempt_status].some(v => v == null)) invalid();
  }
  if (value.next_cursor !== previous) invalid();
  const health = exact(value.health, ["dropped", "write_failures", "read_failures", "queued", "writer_alive"]);
  for (const key of ["dropped", "write_failures", "read_failures", "queued"]) count(health[key]);
  if (typeof health.writer_alive !== "boolean") invalid();
  if (value.desktop_spool !== null) {
    const spool = exact(value.desktop_spool, ["rejected", "failures"]);
    count(spool.rejected); count(spool.failures);
  }
  return value as DiagnosticEventPageV1;
}
export interface DiagnosticIndexPage {
  items: DiagnosticHarnessIndexV1[]; next_cursor: string; has_more: boolean;
  coverage: { failures: number; freshness: "eventual" | "unavailable"; canonical_read_back_required: true; cursor?: string; completed_sweeps?: number };
}
export function decodeDiagnosticIndex(raw: unknown, after = ""): DiagnosticIndexPage {
  const value = exact(raw, ["items", "next_cursor", "has_more", "coverage"]);
  page(value.items, value.next_cursor, after, value.has_more);
  let previous = after;
  for (const item of value.items) {
    validate(item, schemas.index, schemas.index);
    if (item.trace_id <= previous) invalid();
    previous = item.trace_id;
  }
  if (value.next_cursor !== previous) invalid();
  const coverage = record(value.coverage);
  exact(coverage, coverage.freshness === "eventual" ? ["failures", "freshness", "canonical_read_back_required", "cursor", "completed_sweeps"] : ["failures", "freshness", "canonical_read_back_required"]);
  count(coverage.failures);
  if (coverage.canonical_read_back_required !== true || !["eventual", "unavailable"].includes(coverage.freshness)) invalid();
  if (coverage.freshness === "eventual") { count(coverage.completed_sweeps); if (typeof coverage.cursor !== "string" || coverage.cursor.length > 160) invalid(); }
  else if (value.items.length || value.has_more) invalid();
  return value as DiagnosticIndexPage;
}
export interface DiagnosticLinkPage { items: DiagnosticOperationLinkV1[]; next_cursor: string; gap: "no_correlation_recorded_or_retained" | "diagnostic_store_unavailable" | null }
export function decodeDiagnosticLinks(raw: unknown, operationId: string, after = ""): DiagnosticLinkPage {
  const value = exact(raw, ["items", "next_cursor", "gap"]);
  page(value.items, value.next_cursor, after, false);
  let previous = after;
  for (const item of value.items) {
    validate(item, schemas.link, schemas.link);
    if (item.operation_id !== operationId || item.request_id <= previous) invalid();
    previous = item.request_id;
  }
  if (value.next_cursor !== previous || ![null, "no_correlation_recorded_or_retained", "diagnostic_store_unavailable"].includes(value.gap) || (value.items.length > 0 && value.gap !== null) || (!value.items.length && value.gap === null)) invalid();
  return value as DiagnosticLinkPage;
}
async function query(path: string, parameters: Record<string, unknown>, signal?: AbortSignal): Promise<unknown> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(parameters)) if (value !== undefined && value !== "") params.set(key, String(value));
  // Deliberately bypass diagnosticFetch: querying diagnostics cannot recursively collect itself.
  const timeout = AbortSignal.timeout(5000);
  let response: Response;
  try { response = await fetch(`${getAiBaseUrl()}/diagnostics/${path}?${params}`, { signal: signal ? AbortSignal.any([signal, timeout]) : timeout }); }
  catch (error) { if (signal?.aborted) throw error; throw new DiagnosticQueryError("unavailable"); }
  if (!response.ok) throw new DiagnosticQueryError("unavailable");
  if (!response.body) invalid();
  const reader = response.body!.getReader();
  const chunks: Uint8Array[] = [];
  let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > 2 * 1024 * 1024) throw new DiagnosticQueryError("response_too_large");
      chunks.push(value);
    }
  } catch (error) {
    await reader.cancel().catch(() => {});
    if (error instanceof DiagnosticQueryError || signal?.aborted) throw error;
    throw new DiagnosticQueryError("unavailable");
  }
  finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.length; }
  try { return JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes)); } catch { return invalid(); }
}
export async function queryDiagnosticEvents(filters: DiagnosticEventFilters = {}, after = 0, signal?: AbortSignal) {
  return decodeDiagnosticEvents(await query("events", { ...filters, after, limit: 100 }, signal), after);
}
export async function queryDiagnosticIndex(filters: Pick<DiagnosticEventFilters, "operation_id" | "workflow" | "stage"> = {}, after = "", signal?: AbortSignal) {
  return decodeDiagnosticIndex(await query("harness-index", { ...filters, after, limit: 25 }, signal), after);
}
export async function queryDiagnosticLinks(operationId: string, after = "", signal?: AbortSignal) {
  return decodeDiagnosticLinks(await query("operation-links", { operation_id: operationId, after, limit: 100 }, signal), operationId, after);
}
