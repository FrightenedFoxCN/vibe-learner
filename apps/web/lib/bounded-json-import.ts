export const JSON_IMPORT_MAX_BYTES = 8 * 1024 * 1024;

/** Check bytes before reading; callers still validate domain shape before mutation. */
export async function readBoundedJsonImport(
  file: Pick<File, "size" | "text">,
  kind: "persona" | "scene",
): Promise<unknown> {
  if (file.size > JSON_IMPORT_MAX_BYTES) throw new Error(`${kind}_import_file_too_large`);
  return JSON.parse(await file.text()) as unknown;
}
