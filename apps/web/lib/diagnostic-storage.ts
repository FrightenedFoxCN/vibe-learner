import type { DiagnosticStorageV1 } from "@vibe-learner/shared";
import schema from "../../../packages/shared/fixtures/diagnostics/storage-schema-v1.json";
import { DiagnosticQueryError, validateDiagnosticExportSchema, requestDiagnosticStorage } from "./diagnostic-query";

export function decodeDiagnosticStorage(raw: unknown): DiagnosticStorageV1 {
  validateDiagnosticExportSchema(raw, schema);
  const value = raw as DiagnosticStorageV1;
  const invalid = (): never => { throw new DiagnosticQueryError("invalid_response"); };
  if (value.databases[0].name !== "events" || value.databases[1].name !== "index" || new Set(value.unmeasured).size !== 4) invalid();
  for (const row of value.databases) {
    if (row.gap === "not_configured") {
      if (row.status !== "unavailable" || row.files !== null || row.counters !== null || row.max_bytes !== null) invalid();
      continue;
    }
    if (row.counters === null || row.max_bytes === null) invalid();
    if (row.gap === "filesystem_unavailable") {
      if (row.status !== "unavailable" || row.files !== null) invalid();
      continue;
    }
    if (row.files === null) invalid();
    const files = row.files!;
    const total = files.database + files.wal + files.shm + files.journal + files.lock;
    if (!Number.isSafeInteger(total) || total !== files.total_bytes) invalid();
    if (row.gap === "database_absent") {
      if (row.status !== "unavailable" || files.database !== 0) invalid();
    } else if (row.gap !== null || files.database === 0 || row.status !== (total > row.max_bytes! ? "over_observed_limit" : "within_observed_limit")) invalid();
  }
  return value;
}
export async function queryDiagnosticStorage(signal?: AbortSignal) {
  const result = decodeDiagnosticStorage(await requestDiagnosticStorage(signal));
  signal?.throwIfAborted();
  return result;
}
