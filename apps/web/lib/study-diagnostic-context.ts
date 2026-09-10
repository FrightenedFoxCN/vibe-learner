import { createDiagnosticId, diagnosticContext } from "./diagnostics";

const KEY = "vibe-learner:study-diagnostic-flows:v1";
const LIMIT = 128;
const MAX_BYTES = 64 * 1024;
const TTL = 7 * 24 * 60 * 60 * 1000;
const identity = (value: unknown): value is string => typeof value === "string" && /^[A-Za-z0-9:._-]{1,160}$/.test(value);
const flowIdentity = (value: unknown): value is string => typeof value === "string" && /^[A-Za-z0-9_-]{1,96}$/.test(value);
type Entry = { sessionId: string; clientRequestId: string; flowId: string; createdAt: number };
interface StoragePort { read(): string | null; write(value: string): void }

/** Diagnostic correlation only. Never admission, recovery state, or commit proof. */
export function createStudyDiagnosticFlows(storage: StoragePort, now = Date.now, allocate = createDiagnosticId) {
  let entries: Entry[] = [];
  let loaded = false;
  return (sessionId: string, clientRequestId: string, inheritedFlowId?: string | null) => {
    const timestamp = now();
    if (!loaded) {
      loaded = true;
      try {
        const raw = storage.read();
        if (raw && raw.length <= MAX_BYTES && new TextEncoder().encode(raw).length <= MAX_BYTES) {
          const value: unknown = JSON.parse(raw);
          if (Array.isArray(value) && value.length <= LIMIT) {
            const keys = new Set<string>();
            entries = value.filter((item): item is Entry => {
              if (!item || typeof item !== "object" || Object.keys(item).sort().join(",") !== "clientRequestId,createdAt,flowId,sessionId" ||
                  !identity(item.sessionId) || !identity(item.clientRequestId) || !flowIdentity(item.flowId) ||
                  !Number.isSafeInteger(item.createdAt) || item.createdAt < 0 || item.createdAt < timestamp - TTL || item.createdAt > timestamp) return false;
              const key = `${item.sessionId}/${item.clientRequestId}`;
              if (keys.has(key)) return false;
              keys.add(key); return true;
            });
          }
        }
      } catch { /* Storage denial or corruption cannot change the business request. */ }
    }
    entries = entries.filter(item => item.createdAt >= timestamp - TTL && item.createdAt <= timestamp);
    if (!identity(sessionId) || !identity(clientRequestId)) return diagnosticContext();
    let entry = entries.find(item => item.sessionId === sessionId && item.clientRequestId === clientRequestId);
    if (!entry) {
      // Existing request ownership wins over a later parent's hint. Only a new
      // diagnostic mapping may inherit a reviewed random flow identity.
      const flowId = flowIdentity(inheritedFlowId) ? inheritedFlowId : allocate();
      if (!flowIdentity(flowId)) return diagnosticContext();
      entry = { sessionId, clientRequestId, flowId, createdAt: timestamp };
      entries = [...entries.slice(-(LIMIT - 1)), entry];
      while (JSON.stringify(entries).length > MAX_BYTES) entries.shift();
      try { storage.write(JSON.stringify(entries)); } catch { /* Keep bounded in-memory correlation. */ }
    }
    return diagnosticContext(entry.flowId);
  };
}

// Tab-scoped session storage survives reload; no cross-tab or restart claim.
export const studyDiagnosticContext = createStudyDiagnosticFlows({
  read: () => globalThis.sessionStorage?.getItem(KEY) ?? null,
  write: value => globalThis.sessionStorage?.setItem(KEY, value),
});
