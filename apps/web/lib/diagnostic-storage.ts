import type { DiagnosticStorageV1 } from "@vibe-learner/shared";
import schema from "../../../packages/shared/fixtures/diagnostics/storage-schema-v1.json";
import { DiagnosticQueryError, validateDiagnosticExportSchema, requestDiagnosticStorage } from "./diagnostic-query";

export function decodeDiagnosticStorage(raw: unknown): DiagnosticStorageV1 {
  validateDiagnosticExportSchema(raw, schema);
  const value = raw as DiagnosticStorageV1;
  const invalid = (): never => { throw new DiagnosticQueryError("invalid_response"); };
  if (value.databases[0].name !== "events" || value.databases[1].name !== "index" || new Set(value.unmeasured).size !== 3) invalid();
  const directory = value.directory;
  const directoryTotal = directory.database_bytes + directory.spool_bytes + directory.other_bytes;
  if (!Number.isSafeInteger(directoryTotal) || directoryTotal !== directory.total_bytes ||
      directory.database_files + directory.spool_files + directory.other_files > directory.scanned_entries ||
      directory.skipped_entries > directory.scanned_entries || new Set(directory.gaps).size !== directory.gaps.length ||
      ((directory.status === "observed" || directory.status === "absent") !== (directory.gaps.length === 0)) ||
      (directory.status === "observed" && (directory.skipped_entries !== 0 || directory.visited_directories < 1)) ||
      (directory.status === "absent" && (directoryTotal !== 0 || directory.scanned_entries !== 0 || directory.visited_directories !== 0)) ||
      directory.budget_state !== (directoryTotal > directory.max_bytes ? "over_observed_limit" : directory.status === "observed" ? "within_observed_limit" : "unknown")) invalid();
  for (const [bytes, files] of [[directory.database_bytes, directory.database_files], [directory.spool_bytes, directory.spool_files], [directory.other_bytes, directory.other_files]]) {
    if (bytes > 0 && files === 0) invalid();
  }
  const spool = value.desktop_spool;
  const spoolTotal = spool.event_bytes + spool.metadata_bytes + spool.other_bytes;
  if (!Number.isSafeInteger(spoolTotal) || spoolTotal !== spool.total_bytes ||
      spool.event_files + spool.other_files + spool.skipped_entries > spool.scan_limit ||
      ((spool.status === "observed" || spool.status === "absent") !== (spool.gap === null)) ||
      (spool.status === "absent" && (spoolTotal !== 0 || spool.event_files + spool.other_files + spool.skipped_entries !== 0)) ||
      (spool.status === "observed" && spool.skipped_entries !== 0)) invalid();
  for (const row of value.databases) {
    if (row.gap === "not_configured") {
      if (row.status !== "unavailable" || row.files !== null || row.counters !== null || row.recovery !== null || row.max_bytes !== null) invalid();
      continue;
    }
    if (row.counters === null || row.recovery === null || row.max_bytes === null) invalid();
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
