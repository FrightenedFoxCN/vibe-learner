import type {
  TavernMessage,
  TavernParticipant,
  TavernRoomState,
  TavernRun,
  TavernRunRecoveryChain,
  TavernSpeakerStepStatus,
} from "@vibe-learner/shared";

export const TAVERN_ACTIVE_ROOM_STORAGE_KEY = "vibe-learner:tavern:active-room";
export const TAVERN_DRAFT_STORAGE_KEY = "vibe-learner:tavern:drafts";
export const TAVERN_CREATION_DRAFT_STORAGE_KEY = "vibe-learner:tavern:creation-draft";
export const TAVERN_PAGE_SIZE = 40;
export const TAVERN_RUN_HISTORY_LIMIT = 50;

export interface TavernRoomDraft {
  message: string;
  guidance: string;
  pendingTurn?: {
    key: string;
    content: string;
    guidance: string;
    targetPersonaIds: string[];
    expectedRoomRevision: number;
  };
}

export interface TavernCreationDraft {
  key: string;
  title: string;
  personaIds: string[];
  sceneId: string;
  openingPrompt: string;
}

export interface TavernFacilitatedRecovery {
  run: TavernRun;
  chainStatus: "recoverable" | "recovered";
  completedCount: number;
  totalCount: number;
  unfinishedPersonaIds: string[];
}

export function readActiveTavernRoomId(): string {
  try {
    return window.localStorage.getItem(TAVERN_ACTIVE_ROOM_STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function rememberActiveTavernRoomId(roomId: string): void {
  try {
    window.localStorage.setItem(TAVERN_ACTIVE_ROOM_STORAGE_KEY, roomId);
  } catch {
    // Storage is a convenience for refresh recovery, not a room-open requirement.
  }
}

export function readTavernRoomDraft(roomId: string): TavernRoomDraft {
  if (!roomId) return { message: "", guidance: "" };
  try {
    const raw = window.sessionStorage.getItem(TAVERN_DRAFT_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) as Record<string, TavernRoomDraft> : {};
    const draft = parsed[roomId];
    if (!draft || typeof draft !== "object") return { message: "", guidance: "" };
    const pending = draft.pendingTurn;
    const pendingTurn = pending
      && typeof pending === "object"
      && typeof pending.key === "string"
      && typeof pending.content === "string"
      && typeof pending.guidance === "string"
      && Array.isArray(pending.targetPersonaIds)
      && pending.targetPersonaIds.every((item) => typeof item === "string")
      && Number.isInteger(pending.expectedRoomRevision)
      && pending.expectedRoomRevision >= 0
        ? {
            key: pending.key.slice(0, 80),
            content: pending.content,
            guidance: pending.guidance,
            targetPersonaIds: pending.targetPersonaIds.slice(0, 4),
            expectedRoomRevision: pending.expectedRoomRevision,
          }
        : undefined;
    return {
      message: typeof draft.message === "string" ? draft.message : "",
      guidance: typeof draft.guidance === "string" ? draft.guidance : "",
      pendingTurn,
    };
  } catch {
    return { message: "", guidance: "" };
  }
}

export function writeTavernRoomDraft(roomId: string, draft: TavernRoomDraft): void {
  if (!roomId) return;
  try {
    const raw = window.sessionStorage.getItem(TAVERN_DRAFT_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) as Record<string, TavernRoomDraft> : {};
    parsed[roomId] = draft;
    window.sessionStorage.setItem(TAVERN_DRAFT_STORAGE_KEY, JSON.stringify(parsed));
  } catch {
    // Draft persistence is best effort; the controlled inputs remain usable.
  }
}

export function readTavernCreationDraft(): TavernCreationDraft | null {
  try {
    const raw = window.sessionStorage.getItem(TAVERN_CREATION_DRAFT_STORAGE_KEY);
    const parsed = raw ? JSON.parse(raw) as Partial<TavernCreationDraft> : null;
    if (
      !parsed ||
      typeof parsed.key !== "string" ||
      typeof parsed.title !== "string" ||
      !Array.isArray(parsed.personaIds) ||
      !parsed.personaIds.every((item) => typeof item === "string") ||
      typeof parsed.sceneId !== "string" ||
      typeof parsed.openingPrompt !== "string"
    ) return null;
    return {
      key: parsed.key.slice(0, 80),
      title: parsed.title,
      personaIds: parsed.personaIds.slice(0, 6),
      sceneId: parsed.sceneId,
      openingPrompt: parsed.openingPrompt,
    };
  } catch {
    return null;
  }
}

export function writeTavernCreationDraft(draft: TavernCreationDraft | null): void {
  try {
    if (draft) {
      window.sessionStorage.setItem(
        TAVERN_CREATION_DRAFT_STORAGE_KEY,
        JSON.stringify(draft)
      );
    } else {
      window.sessionStorage.removeItem(TAVERN_CREATION_DRAFT_STORAGE_KEY);
    }
  } catch {
    // Creation recovery is best effort; the form remains usable without storage.
  }
}

export type TavernParticipantGenerationState =
  | TavernSpeakerStepStatus
  | "previous_completed"
  | "previous_failed"
  | "previous_blocked"
  | "previous_canceled"
  | "idle";

export interface TavernParticipantState {
  participant: TavernParticipant;
  state: TavernParticipantGenerationState;
}

export function mergeTavernMessages(
  current: TavernMessage[],
  incoming: TavernMessage[]
): TavernMessage[] {
  const bySequence = new Map<number, TavernMessage>();
  const byId = new Map<string, number>();
  const expectedRoomId = current[0]?.roomId ?? incoming[0]?.roomId;

  for (const message of [...current, ...incoming]) {
    if (expectedRoomId && message.roomId !== expectedRoomId) {
      throw new TavernMessageConflictError(
        "messages_from_different_rooms",
        message.id,
        message.sequence
      );
    }
    const priorSequence = byId.get(message.id);
    if (priorSequence !== undefined) {
      if (priorSequence !== message.sequence) {
        throw new TavernMessageConflictError(
          "message_id_reused_with_different_sequence",
          message.id,
          message.sequence
        );
      }
      const prior = bySequence.get(priorSequence);
      if (prior && JSON.stringify(prior) !== JSON.stringify(message)) {
        throw new TavernMessageConflictError(
          "append_only_message_changed",
          message.id,
          message.sequence
        );
      }
      continue;
    }
    const priorAtSequence = bySequence.get(message.sequence);
    if (priorAtSequence && priorAtSequence.id !== message.id) {
      throw new TavernMessageConflictError(
        "sequence_reused_with_different_message",
        message.id,
        message.sequence
      );
    }
    bySequence.set(message.sequence, message);
    byId.set(message.id, message.sequence);
  }

  return [...bySequence.values()].sort((left, right) => {
    if (left.sequence !== right.sequence) {
      return left.sequence - right.sequence;
    }
    return left.id.localeCompare(right.id);
  });
}

export class TavernMessageConflictError extends Error {
  readonly code = "tavern_message_identity_conflict";
  readonly messageId: string;
  readonly sequence: number;

  constructor(reason: string, messageId: string, sequence: number) {
    super(`${reason}:${messageId}:${sequence}`);
    this.name = "TavernMessageConflictError";
    this.messageId = messageId;
    this.sequence = sequence;
  }
}

export function projectParticipantStates(
  participants: TavernParticipant[],
  runs: TavernRun[],
  optimisticPersonaIds: string[] = []
): TavernParticipantState[] {
  const orderedParticipants = [...participants]
    .sort((left, right) => left.displayOrder - right.displayOrder);
  const activeRun = [...runs]
    .filter((run) => run.status === "pending")
    .sort(compareRunsNewestFirst)[0];
  const latestTerminalRun = activeRun
    ? undefined
    : [...runs].sort(compareRunsNewestFirst)[0];
  const stepByPersona = new Map<string, TavernParticipantGenerationState>();

  if (activeRun?.speakerSteps.length) {
    for (const step of activeRun.speakerSteps) {
      stepByPersona.set(step.personaId, step.status);
    }
  } else if (activeRun) {
    const startingIds = optimisticPersonaIds.length
      ? optimisticPersonaIds
      : activeRun.scheduledParticipantIds;
    const starting = orderedParticipants
      .filter((participant) => startingIds.includes(participant.personaId));
    starting.forEach((participant, index) => {
      stepByPersona.set(
        participant.personaId,
        optimisticPersonaIds.length && index === 0 ? "generating" : "pending"
      );
    });
  } else if (optimisticPersonaIds.length) {
    const optimistic = orderedParticipants
      .filter((participant) => optimisticPersonaIds.includes(participant.personaId));
    optimistic.forEach((participant, index) => {
      stepByPersona.set(participant.personaId, index === 0 ? "generating" : "pending");
    });
  } else if (latestTerminalRun) {
    for (const step of latestTerminalRun.speakerSteps) {
      if (step.status === "completed") {
        stepByPersona.set(step.personaId, "previous_completed");
      } else if (step.status === "failed") {
        stepByPersona.set(step.personaId, "previous_failed");
      } else if (step.status === "blocked") {
        stepByPersona.set(step.personaId, "previous_blocked");
      } else if (step.status === "canceled") {
        stepByPersona.set(step.personaId, "previous_canceled");
      }
    }
  }

  return orderedParticipants
    .map((participant) => ({
      participant,
      state: stepByPersona.get(participant.personaId) ?? "idle",
    }));
}

export function listRetryableRuns(runs: TavernRun[]): TavernRun[] {
  const runsWithChildren = new Set(
    runs.map((run) => run.parentRunId).filter((id): id is string => Boolean(id))
  );
  return [...runs]
    .filter(
      (run) =>
        (run.status === "partial" || run.status === "failed") &&
        !runsWithChildren.has(run.id)
    )
    .sort(compareRunsNewestFirst);
}

export function latestFacilitatedRecovery(
  runs: TavernRun[]
): TavernFacilitatedRecovery | null {
  const run = listRetryableRuns(runs).find(
    (candidate) =>
      candidate.mode === "facilitated" &&
      candidate.speakerSteps.some(
        (step) => step.status === "failed" || step.status === "blocked"
      )
  );
  if (!run) return null;
  return {
    run,
    chainStatus: "recoverable",
    completedCount: run.speakerSteps.filter((step) => step.status === "completed").length,
    totalCount: run.speakerSteps.length,
    unfinishedPersonaIds: run.speakerSteps
      .filter((step) => step.status === "failed" || step.status === "blocked")
      .map((step) => step.personaId),
  };
}

export function authoritativeFacilitatedRecovery(
  chains: TavernRunRecoveryChain[]
): TavernFacilitatedRecovery | null {
  const candidates = chains.filter(
    (chain) =>
      chain.leafRun.mode === "facilitated" &&
      (chain.rootStatus === "partial" || chain.rootStatus === "failed") &&
      (chain.chainStatus === "recoverable" || chain.chainStatus === "recovered")
  );
  const chain = candidates.find((item) => item.chainStatus === "recoverable")
    ?? candidates.find((item) => item.chainStatus === "recovered");
  if (!chain) return null;
  return {
    run: chain.leafRun,
    chainStatus: chain.chainStatus === "recoverable" ? "recoverable" : "recovered",
    completedCount: chain.completedParticipantIds.length,
    totalCount:
      chain.completedParticipantIds.length + chain.unfinishedParticipantIds.length,
    unfinishedPersonaIds: chain.unfinishedParticipantIds,
  };
}

export function latestTavernMessage(messages: TavernMessage[]): TavernMessage | null {
  return messages.length ? messages[messages.length - 1] : null;
}

export function makeTavernRequestKey(scope: "room" | "turn" | "retry"): string {
  const uuid =
    typeof crypto !== "undefined" && typeof crypto.randomUUID === "function"
      ? crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
  return `${scope}-${uuid}`.slice(0, 80);
}

export function compareRunsNewestFirst(left: TavernRun, right: TavernRun): number {
  const timeDifference = Date.parse(right.createdAt) - Date.parse(left.createdAt);
  if (Number.isFinite(timeDifference) && timeDifference !== 0) {
    return timeDifference;
  }
  return right.id.localeCompare(left.id);
}

export function reconcileTavernRuns(
  current: TavernRun[],
  incoming: TavernRun[],
  limit = TAVERN_RUN_HISTORY_LIMIT
): TavernRun[] {
  const currentById = new Map(current.map((run) => [run.id, run]));
  const seen = new Set<string>();
  const reconciled = incoming.map((run) => {
    seen.add(run.id);
    const existing = currentById.get(run.id);
    // A Tavern run is immutable after it becomes terminal. A list request may
    // have started before the foreground turn committed, so never let that
    // older pending snapshot resurrect a terminal run in the UI.
    return existing && existing.status !== "pending" ? existing : run;
  });

  for (const run of current) {
    if (run.status !== "pending" && !seen.has(run.id)) {
      reconciled.push(run);
    }
  }

  return reconciled
    .sort(compareRunsNewestFirst)
    .slice(0, Math.max(1, limit));
}

export function hasActiveTavernRun(runs: TavernRun[]): boolean {
  return runs.some((run) => run.status === "pending");
}

export function isTavernRoomStateAtLeast(
  incoming: TavernRoomState,
  current: TavernRoomState | null
): boolean {
  return !current || (
    incoming.id === current.id &&
    incoming.revision >= current.revision &&
    incoming.lastSequence >= current.lastSequence
  );
}
