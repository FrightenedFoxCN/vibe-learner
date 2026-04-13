"use client";

const STORAGE_KEY = "vibe-learner:study-dialogue-interruption:v1";

interface PersistedDialogueInterruptionState {
  interruptedDialogueSessionId: string;
  deferredInteractiveCallbacks: Record<string, string[]>;
}

export function readInterruptedDialogueSessionId(): string {
  return loadState().interruptedDialogueSessionId;
}

export function writeInterruptedDialogueSessionId(sessionId: string): void {
  const state = loadState();
  state.interruptedDialogueSessionId = sessionId.trim();
  saveState(state);
}

export function readDeferredInteractiveCallbacks(sessionId: string): string[] {
  const normalizedSessionId = sessionId.trim();
  if (!normalizedSessionId) {
    return [];
  }
  return [...(loadState().deferredInteractiveCallbacks[normalizedSessionId] ?? [])];
}

export function appendDeferredInteractiveCallback(sessionId: string, message: string): void {
  const normalizedSessionId = sessionId.trim();
  const normalizedMessage = message.trim();
  if (!normalizedSessionId || !normalizedMessage) {
    return;
  }
  const state = loadState();
  const existing = state.deferredInteractiveCallbacks[normalizedSessionId] ?? [];
  state.deferredInteractiveCallbacks[normalizedSessionId] = [...existing, normalizedMessage];
  saveState(state);
}

export function clearDeferredInteractiveCallbacks(sessionId: string): void {
  const normalizedSessionId = sessionId.trim();
  if (!normalizedSessionId) {
    return;
  }
  const state = loadState();
  delete state.deferredInteractiveCallbacks[normalizedSessionId];
  saveState(state);
}

export function moveDeferredInteractiveCallbacks(
  fromSessionId: string,
  toSessionId: string
): void {
  const normalizedFrom = fromSessionId.trim();
  const normalizedTo = toSessionId.trim();
  if (!normalizedFrom || !normalizedTo || normalizedFrom === normalizedTo) {
    return;
  }
  const state = loadState();
  const source = state.deferredInteractiveCallbacks[normalizedFrom] ?? [];
  if (!source.length) {
    return;
  }
  const target = state.deferredInteractiveCallbacks[normalizedTo] ?? [];
  state.deferredInteractiveCallbacks[normalizedTo] = [...target, ...source];
  delete state.deferredInteractiveCallbacks[normalizedFrom];
  saveState(state);
}

function loadState(): PersistedDialogueInterruptionState {
  if (typeof globalThis.localStorage === "undefined") {
    return {
      interruptedDialogueSessionId: "",
      deferredInteractiveCallbacks: {},
    };
  }
  try {
    const raw = globalThis.localStorage.getItem(STORAGE_KEY);
    if (!raw) {
      return {
        interruptedDialogueSessionId: "",
        deferredInteractiveCallbacks: {},
      };
    }
    const parsed = JSON.parse(raw) as {
      interruptedDialogueSessionId?: unknown;
      deferredInteractiveCallbacks?: unknown;
    };
    return {
      interruptedDialogueSessionId:
        typeof parsed.interruptedDialogueSessionId === "string"
          ? parsed.interruptedDialogueSessionId.trim()
          : "",
      deferredInteractiveCallbacks: normalizeDeferredInteractiveCallbacks(
        parsed.deferredInteractiveCallbacks
      ),
    };
  } catch {
    return {
      interruptedDialogueSessionId: "",
      deferredInteractiveCallbacks: {},
    };
  }
}

function saveState(state: PersistedDialogueInterruptionState): void {
  if (typeof globalThis.localStorage === "undefined") {
    return;
  }
  const callbacks = normalizeDeferredInteractiveCallbacks(state.deferredInteractiveCallbacks);
  const interruptedDialogueSessionId = state.interruptedDialogueSessionId.trim();
  if (!interruptedDialogueSessionId && !Object.keys(callbacks).length) {
    globalThis.localStorage.removeItem(STORAGE_KEY);
    return;
  }
  globalThis.localStorage.setItem(
    STORAGE_KEY,
    JSON.stringify({
      interruptedDialogueSessionId,
      deferredInteractiveCallbacks: callbacks,
    })
  );
}

function normalizeDeferredInteractiveCallbacks(
  value: unknown
): Record<string, string[]> {
  if (!value || typeof value !== "object") {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .map(([sessionId, entry]) => [
        sessionId.trim(),
        Array.isArray(entry)
          ? entry
              .map((item) => String(item ?? "").trim())
              .filter(Boolean)
          : [],
      ])
      .filter(([sessionId, messages]) => Boolean(sessionId) && messages.length > 0)
  );
}
