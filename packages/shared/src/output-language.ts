/** Application input; "auto" delegates language choice without changing evidence. */
export function isOutputLanguagePreference(value: unknown): value is string {
  return (
    typeof value === "string" &&
    value.length <= 35 &&
    value.toLowerCase() !== "unknown" &&
    /^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$/.test(value)
  );
}
