import type { TavernMessage, TavernRoomDetail } from "@vibe-learner/shared";

import { mergeTavernMessages } from "./tavern-workspace-state.ts";

const MAX_BRIDGE_MESSAGES = 200;

interface TranscriptWindow {
  messages: TavernMessage[];
  nextBeforeSequence: number | null;
}

function firstGap(messages: TavernMessage[]): { after: number; count: number } | null {
  for (let index = 1; index < messages.length; index += 1) {
    const after = messages[index - 1].sequence;
    const count = messages[index].sequence - after - 1;
    if (count > 0) return { after, count };
  }
  return null;
}

export function mergeOlderTavernTranscript(
  current: TranscriptWindow,
  requestedBefore: number,
  previous: TranscriptWindow,
): TranscriptWindow | null {
  if (requestedBefore !== current.nextBeforeSequence) return null;
  return {
    messages: mergeTavernMessages(current.messages, previous.messages),
    nextBeforeSequence: previous.nextBeforeSequence,
  };
}

export async function refreshTavernTranscript(
  current: TranscriptWindow,
  tail: TranscriptWindow,
  loadAfter: (sequence: number, limit: number) => Promise<TavernRoomDetail>,
): Promise<TranscriptWindow> {
  const messages = mergeTavernMessages(current.messages, tail.messages);
  const gap = firstGap(messages);
  if (!gap) {
    return {
      messages,
      nextBeforeSequence: current.messages.length
        ? current.nextBeforeSequence
        : tail.nextBeforeSequence,
    };
  }
  if (gap.count <= MAX_BRIDGE_MESSAGES) {
    const page = await loadAfter(gap.after, gap.count).catch(() => null);
    if (page) {
      const bridged = mergeTavernMessages(messages, page.messages);
      if (!firstGap(bridged)) {
        return { messages: bridged, nextBeforeSequence: current.nextBeforeSequence };
      }
    }
  }
  // An unavailable bridge falls back to a tail with a usable history cursor.
  return tail;
}
