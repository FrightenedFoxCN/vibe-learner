import { observeLocalAction } from "./diagnostic-actions.ts";
import type { DiagnosticContext } from "./diagnostics.ts";

export const JSON_IMPORT_MAX_BYTES = 8 * 1024 * 1024;

/** Check bytes before reading; callers still validate domain shape before mutation. */
export async function readBoundedJsonImport(
  file: Pick<File, "size" | "text">,
  kind: "persona" | "scene",
  context?: DiagnosticContext,
): Promise<unknown> {
  return observeLocalAction(kind === "persona" ? "json_import_read_persona" : "json_import_read_scene", async () => {
    if (file.size > JSON_IMPORT_MAX_BYTES) throw new Error(`${kind}_import_file_too_large`);
    return JSON.parse(await file.text()) as unknown;
  }, { context });
}

/** Completion means guarded draft application, not a persisted domain commit. */
export async function importJsonDraft<T>(
  file: Pick<File, "size" | "text">,
  kind: "persona" | "scene",
  decode: (raw: unknown) => T,
  apply: (draft: T) => boolean,
): Promise<boolean> {
  return observeLocalAction(kind === "persona" ? "json_import_persona_draft" : "json_import_scene_draft", async context => {
    const raw = await readBoundedJsonImport(file, kind, context);
    return apply(decode(raw));
  }, { cancelled: applied => !applied });
}
