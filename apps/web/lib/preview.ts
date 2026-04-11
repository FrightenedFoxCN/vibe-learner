const DEFAULT_STRING_LIMIT = 480;
const DEFAULT_ARRAY_LIMIT = 6;
const DEFAULT_OBJECT_KEY_LIMIT = 12;
const DEFAULT_DEPTH_LIMIT = 2;

export function compactPreviewString(value: unknown, maxChars = DEFAULT_STRING_LIMIT): string {
  if (typeof value !== "string") {
    return String(value ?? "");
  }
  if (value.length <= maxChars) {
    return value;
  }
  return `${value.slice(0, maxChars)}…(${value.length - maxChars} more chars)`;
}

export function compactPreviewValue(value: unknown, depth = DEFAULT_DEPTH_LIMIT): unknown {
  if (value === null || value === undefined) {
    return value;
  }

  if (typeof value === "string") {
    return compactPreviewString(value);
  }

  if (typeof value === "number" || typeof value === "boolean") {
    return value;
  }

  if (Array.isArray(value)) {
    const compacted = value.slice(0, DEFAULT_ARRAY_LIMIT).map((item) => compactPreviewValue(item, depth - 1));
    if (value.length > DEFAULT_ARRAY_LIMIT) {
      compacted.push(`…(${value.length - DEFAULT_ARRAY_LIMIT} more items)`);
    }
    return compacted;
  }

  if (typeof value === "object") {
    if (depth <= 0) {
      return "[Object]";
    }

    const entries = Object.entries(value as Record<string, unknown>);
    const compacted = Object.fromEntries(
      entries.slice(0, DEFAULT_OBJECT_KEY_LIMIT).map(([key, item]) => [key, compactPreviewValue(item, depth - 1)])
    ) as Record<string, unknown>;

    if (entries.length > DEFAULT_OBJECT_KEY_LIMIT) {
      compacted.__truncated__ = `…(${entries.length - DEFAULT_OBJECT_KEY_LIMIT} more keys)`;
    }

    return compacted;
  }

  return String(value);
}