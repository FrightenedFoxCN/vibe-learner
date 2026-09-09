export function createStudyChatRequestId(scope: string): string {
  const normalizedScope = scope.toLowerCase().replace(/[^a-z0-9-]+/g, "-").slice(0, 20) || "chat";
  const suffix = typeof globalThis.crypto?.randomUUID === "function"
    ? globalThis.crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `study-${normalizedScope}-${suffix}`.slice(0, 80);
}
