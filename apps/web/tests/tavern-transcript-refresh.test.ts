import assert from "node:assert/strict";
import test from "node:test";

import type { TavernMessage, TavernRoomDetail } from "@vibe-learner/shared";

import {
  mergeOlderTavernTranscript,
  refreshTavernTranscript,
} from "../lib/tavern-transcript-refresh.ts";

function page(first: number, last: number, nextBeforeSequence: number | null) {
  return {
    messages: Array.from(
      { length: last - first + 1 },
      (_, index) =>
        ({
          id: "message-" + (first + index),
          roomId: "room-a",
          sequence: first + index,
        }) as TavernMessage,
    ),
    nextBeforeSequence,
  };
}

test("refresh fetches missing sequences without discarding loaded history", async () => {
  const result = await refreshTavernTranscript(
    page(1, 40, null),
    page(43, 82, 43),
    async (after, limit) => {
      assert.equal(after, 40);
      assert.equal(limit, 2);
      return page(41, 42, null) as TavernRoomDetail;
    },
  );
  assert.deepEqual(result, page(1, 82, null));
});

test("unavailable or oversized bridge retains a reachable tail cursor", async () => {
  const unavailable = await refreshTavernTranscript(
    page(1, 40, null),
    page(43, 82, 43),
    async () => {
      throw new Error("offline");
    },
  );
  assert.deepEqual(unavailable, page(43, 82, 43));
  let reads = 0;
  const oversized = await refreshTavernTranscript(
    page(1, 40, null),
    page(301, 340, 301),
    async () => {
      reads++;
      throw new Error("unexpected bridge read");
    },
  );
  assert.equal(reads, 0);
  assert.deepEqual(oversized, page(301, 340, 301));
});

test("refresh of a previously empty room takes the new history cursor", async () => {
  const tail = page(43, 82, 43);
  const result = await refreshTavernTranscript(page(1, 0, null), tail, async () => {
    assert.fail("empty transcript does not need a bridge");
  });
  assert.deepEqual(result, tail);
});

test("older results from a replaced cursor cannot reopen a transcript gap", () => {
  const freshTail = page(301, 340, 301);
  const obsoletePage = page(21, 60, 21);
  assert.equal(mergeOlderTavernTranscript(freshTail, 61, obsoletePage), null);
  assert.deepEqual(
    mergeOlderTavernTranscript(freshTail, 301, page(261, 300, 261)),
    page(261, 340, 261),
  );
});
