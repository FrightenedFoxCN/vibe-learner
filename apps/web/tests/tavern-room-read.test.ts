import assert from "node:assert/strict";
import test from "node:test";

import type { TavernRoomDetail } from "@vibe-learner/shared";

import { readTavernRoomSnapshot, tavernReadNotice } from "../lib/tavern-room-read.ts";

const detail = {
  room: { id: "room" },
  messages: [{ content: "committed" }],
} as TavernRoomDetail;

test("recovery and room-list failures do not discard a successful transcript read", async () => {
  const snapshot = await readTavernRoomSnapshot({
    detail: Promise.resolve(detail),
    runs: Promise.resolve([]),
    recovery: Promise.reject(new Error("recovery offline")),
    rooms: Promise.reject(new Error("list offline")),
  });
  assert.equal(snapshot.detail, detail);
  assert.deepEqual(snapshot.runs, []);
  assert.equal(snapshot.recovery, null);
  assert.equal(snapshot.rooms.status, "rejected");
  assert.match(tavernReadNotice(true, false), /恢复详情/);
});

test("unknown run state is distinct from a verified empty run list", async () => {
  const snapshot = await readTavernRoomSnapshot({
    detail: Promise.resolve(detail),
    runs: Promise.reject(new Error("runs unavailable")),
    recovery: Promise.resolve([]),
  });
  assert.equal(snapshot.detail, detail);
  assert.equal(snapshot.runs, null);
  assert.match(tavernReadNotice(false, true), /互动状态暂未确认/);
  assert.equal(tavernReadNotice(true, true), "");
});

test("without an authoritative transcript, room open still fails", async () => {
  await assert.rejects(
    readTavernRoomSnapshot({
      detail: Promise.reject(new Error("missing room")),
      runs: Promise.resolve([]),
      recovery: Promise.resolve([]),
    }),
    /missing room/,
  );
});
