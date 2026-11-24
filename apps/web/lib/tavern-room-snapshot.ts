import type {
  TavernRoomDetail,
  TavernRun,
  TavernRunRecoveryChain,
  TavernTurnResult,
} from "@vibe-learner/shared";

import { mergeOlderTavernTranscript } from "./tavern-transcript-refresh.ts";
import {
  isTavernRoomStateAtLeast,
  mergeTavernMessages,
  reconcileTavernRuns,
} from "./tavern-workspace-state.ts";

type TranscriptWindow = Pick<TavernRoomDetail, "messages" | "nextBeforeSequence">;

export type TavernRoomSnapshot = {
  readonly detail: TavernRoomDetail;
  readonly runs: TavernRun[];
  readonly runsKnown: boolean;
  readonly recoveryChains: TavernRunRecoveryChain[];
  readonly recoveryKnown: boolean;
};

export type TavernRoomSnapshotAction =
  | {
      kind: "open";
      detail: TavernRoomDetail;
      runs: TavernRun[] | null;
      recovery: TavernRunRecoveryChain[] | null;
    }
  | {
      kind: "refresh";
      detail: TavernRoomDetail;
      initial: TranscriptWindow;
      transcript: TranscriptWindow;
      runs: TavernRun[] | null;
      recovery: TavernRunRecoveryChain[] | null;
      ownsRecovery: boolean;
    }
  | { kind: "created"; detail: TavernRoomDetail }
  | { kind: "archive"; detail: TavernRoomDetail }
  | { kind: "turn"; result: TavernTurnResult }
  | { kind: "older"; roomId: string; requestedBefore: number; detail: TavernRoomDetail }
  | { kind: "poll"; roomId: string; runs: TavernRun[] }
  | { kind: "recovery"; roomId: string; chains: TavernRunRecoveryChain[] };

export function reduceTavernRoomSnapshot(
  current: TavernRoomSnapshot | null,
  action: TavernRoomSnapshotAction,
): TavernRoomSnapshot | null {
  if (action.kind === "created") {
    // A creation replay for the visible room does not prove its Run list empty.
    if (current?.detail.room.id === action.detail.room.id) {
      return reduceTavernRoomSnapshot(current, {
        kind: "archive",
        detail: action.detail,
      });
    }
    return reduceTavernRoomSnapshot(current, {
      kind: "open",
      detail: action.detail,
      runs: [],
      recovery: [],
    });
  }
  if (action.kind === "open") {
    return {
      detail: {
        ...action.detail,
        messages: mergeTavernMessages([], action.detail.messages),
      },
      runs: action.runs ?? [],
      runsKnown: action.runs !== null,
      recoveryChains: action.recovery ?? [],
      recoveryKnown: action.recovery !== null,
    };
  }
  if (!current) return current;
  const room = current.detail.room;
  switch (action.kind) {
    case "refresh": {
      if (!isTavernRoomStateAtLeast(action.detail.room, room)) return current;
      // Merge a concurrently loaded older page only if the refresh did not
      // replace the transcript window with a disjoint tail.
      const keepOlderPage =
        action.transcript.messages[0]?.sequence ===
          action.initial.messages[0]?.sequence &&
        current.detail.nextBeforeSequence !== action.initial.nextBeforeSequence;
      const transcript = keepOlderPage
        ? {
            messages: mergeTavernMessages(
              current.detail.messages,
              action.transcript.messages,
            ),
            nextBeforeSequence: current.detail.nextBeforeSequence,
          }
        : action.transcript;
      return {
        detail: { ...action.detail, ...transcript },
        runs:
          action.runs === null
            ? current.runs
            : reconcileTavernRuns(current.runs, action.runs),
        runsKnown: action.ownsRecovery ? action.runs !== null : current.runsKnown,
        recoveryChains: action.ownsRecovery
          ? (action.recovery ?? [])
          : current.recoveryChains,
        recoveryKnown: action.ownsRecovery
          ? action.recovery !== null
          : current.recoveryKnown,
      };
    }
    case "archive":
      if (!isTavernRoomStateAtLeast(action.detail.room, room)) return current;
      return {
        ...current,
        detail: {
          ...current.detail,
          room: action.detail.room,
          participants: action.detail.participants,
          messageCount: action.detail.messageCount,
          messages: mergeTavernMessages(
            current.detail.messages,
            action.detail.messages,
          ),
        },
      };
    case "turn": {
      const { roomState, run, inputMessage, generatedMessages } = action.result;
      if (!isTavernRoomStateAtLeast(roomState, room)) return current;
      const previous = current.runs.find((item) => item.id === run.id);
      if (previous && previous.status !== "pending" && previous.status !== run.status)
        return current;
      return {
        ...current,
        detail: {
          ...current.detail,
          room: { ...room, ...roomState },
          messageCount: Math.max(current.detail.messageCount, roomState.lastSequence),
          messages: mergeTavernMessages(current.detail.messages, [
            ...(inputMessage ? [inputMessage] : []),
            ...generatedMessages,
          ]),
        },
        runs: [run, ...current.runs.filter((item) => item.id !== run.id)],
      };
    }
    case "older": {
      if (action.roomId !== room.id || action.detail.room.id !== room.id)
        return current;
      const transcript = mergeOlderTavernTranscript(
        current.detail,
        action.requestedBefore,
        action.detail,
      );
      return transcript
        ? { ...current, detail: { ...current.detail, ...transcript } }
        : current;
    }
    case "poll":
      if (action.roomId !== room.id) return current;
      // A foreground poll finds a specific run; it does not clear an earlier
      // complete-room read failure or change the actionable recovery chains.
      return { ...current, runs: reconcileTavernRuns(current.runs, action.runs) };
    case "recovery":
      if (action.roomId !== room.id) return current;
      return { ...current, recoveryChains: action.chains };
  }
}
