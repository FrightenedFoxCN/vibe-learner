"use client";

import { createStudyChatRequestId } from "./client-request-id.ts";

export type DeferredStudyCallbackReceipt = { epoch: string; count: number };

const STORAGE_KEY = "vibe-learner:study-dialogue-interruption:v1";

interface PersistedDialogueInterruptionState {
  interruptedDialogueSessionId: string;
  deferredInteractiveCallbacks: Record<string, string[]>;
  pauseEpoch: string;
}

export function readInterruptedDialogueSessionId(): string {
  return loadState().interruptedDialogueSessionId;
}

export function writeInterruptedDialogueSessionId(sessionId: string): void {
  const state = loadState();
  state.interruptedDialogueSessionId = sessionId.trim();
  state.pauseEpoch = sessionId.trim() ? createStudyChatRequestId("study-pause") : "";
  saveState(state);
}

export function readDeferredInteractiveCallbacks(sessionId: string): string[] {
  const normalizedSessionId = sessionId.trim();
  if (!normalizedSessionId) {
    return [];
  }
  return [...(loadState().deferredInteractiveCallbacks[normalizedSessionId] ?? [])];
}

export function captureDeferredStudyCallbacks(sessionId: string) {
  const state = loadState();
  const messages = state.deferredInteractiveCallbacks[sessionId] ?? [];
  if (state.interruptedDialogueSessionId !== sessionId) return null;
  if (!state.pauseEpoch) {
    state.pauseEpoch = createStudyChatRequestId("study-pause");
    saveState(state);
  }
  return {
    prefix: messages.join("\n\n"),
    receipt: { epoch: state.pauseEpoch, count: messages.length },
  };
}

export function commitDeferredStudyCallbacks(
  sessionId: string,
  receipt: DeferredStudyCallbackReceipt,
): boolean {
  const state = loadState();
  if (
    state.interruptedDialogueSessionId !== sessionId ||
    state.pauseEpoch !== receipt.epoch
  ) {
    return false;
  }
  const queue = state.deferredInteractiveCallbacks[sessionId] ?? [];
  if (receipt.count > queue.length) return false;
  const remaining = queue.slice(receipt.count);
  if (remaining.length) {
    state.deferredInteractiveCallbacks[sessionId] = remaining;
    state.pauseEpoch = createStudyChatRequestId("study-pause");
  } else {
    delete state.deferredInteractiveCallbacks[sessionId];
    state.interruptedDialogueSessionId = "";
    state.pauseEpoch = "";
  }
  return saveState(state);
}

export function appendDeferredInteractiveCallback(
  sessionId: string,
  message: string,
): void {
  const normalizedSessionId = sessionId.trim();
  const normalizedMessage = message.trim();
  if (!normalizedSessionId || !normalizedMessage) {
    return;
  }
  const state = loadState();
  const existing = state.deferredInteractiveCallbacks[normalizedSessionId] ?? [];
  state.deferredInteractiveCallbacks[normalizedSessionId] = [
    ...existing,
    normalizedMessage,
  ];
  saveState(state);
}

export function clearDeferredInteractiveCallbacks(sessionId: string): void {
  const normalizedSessionId = sessionId.trim();
  if (!normalizedSessionId) {
    return;
  }
  const state = loadState();
  delete state.deferredInteractiveCallbacks[normalizedSessionId];
  if (state.interruptedDialogueSessionId === normalizedSessionId)
    state.pauseEpoch = createStudyChatRequestId("study-pause");
  saveState(state);
}

export function moveDeferredInteractiveCallbacks(
  fromSessionId: string,
  toSessionId: string,
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
  if (state.interruptedDialogueSessionId === normalizedFrom)
    state.pauseEpoch = createStudyChatRequestId("study-pause");
  saveState(state);
}

function loadState(): PersistedDialogueInterruptionState {
  try {
    const raw = globalThis.localStorage?.getItem(STORAGE_KEY);
    if (!raw) {
      return {
        interruptedDialogueSessionId: "",
        deferredInteractiveCallbacks: {},
        pauseEpoch: "",
      };
    }
    const parsed = JSON.parse(raw) as {
      interruptedDialogueSessionId?: unknown;
      deferredInteractiveCallbacks?: unknown;
      pauseEpoch?: unknown;
    };
    return {
      interruptedDialogueSessionId:
        typeof parsed.interruptedDialogueSessionId === "string"
          ? parsed.interruptedDialogueSessionId.trim()
          : "",
      pauseEpoch: typeof parsed.pauseEpoch === "string" ? parsed.pauseEpoch : "",
      deferredInteractiveCallbacks: normalizeDeferredInteractiveCallbacks(
        parsed.deferredInteractiveCallbacks,
      ),
    };
  } catch {
    return {
      interruptedDialogueSessionId: "",
      deferredInteractiveCallbacks: {},
      pauseEpoch: "",
    };
  }
}

function saveState(state: PersistedDialogueInterruptionState): boolean {
  try {
    const storage = globalThis.localStorage;
    if (!storage) return false;
    const callbacks = normalizeDeferredInteractiveCallbacks(
      state.deferredInteractiveCallbacks,
    );
    const interruptedDialogueSessionId = state.interruptedDialogueSessionId.trim();
    if (!interruptedDialogueSessionId && !Object.keys(callbacks).length) {
      storage.removeItem(STORAGE_KEY);
    } else {
      storage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          interruptedDialogueSessionId,
          pauseEpoch: state.pauseEpoch,
          deferredInteractiveCallbacks: callbacks,
        }),
      );
    }
    return true;
  } catch {
    return false;
  }
}

function normalizeDeferredInteractiveCallbacks(
  value: unknown,
): Record<string, string[]> {
  if (!value || typeof value !== "object") {
    return {};
  }
  return Object.fromEntries(
    Object.entries(value as Record<string, unknown>)
      .map(([sessionId, entry]) => [
        sessionId.trim(),
        Array.isArray(entry)
          ? entry.map((item) => String(item ?? "").trim()).filter(Boolean)
          : [],
      ])
      .filter(([sessionId, messages]) => Boolean(sessionId) && messages.length > 0),
  );
}
