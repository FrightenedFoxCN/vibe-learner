import assert from "node:assert/strict";
import test from "node:test";

import type { TavernRoomDetail } from "@vibe-learner/shared";

import { readTavernRoomSnapshot, tavernReadNotice } from "../lib/tavern-room-read.ts";
import {
  advanceTavernRoomListStatus,
  tavernRoomListPresentation,
} from "../lib/tavern-room-list-status.ts";

const detail = {
  room: { id: "room" },
  messages: [{ content: "committed" }],
} as TavernRoomDetail;

test("recovery read failures do not discard a successful transcript read", async () => {
  const snapshot = await readTavernRoomSnapshot({
    detail: Promise.resolve(detail),
    runs: Promise.resolve([]),
    recovery: Promise.reject(new Error("recovery offline")),
  });
  assert.equal(snapshot.detail, detail);
  assert.deepEqual(snapshot.runs, []);
  assert.equal(snapshot.recovery, null);
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

test("the list does not advertise emptiness before a successful first page", () => {
  const loading = advanceTavernRoomListStatus("loading", "start");
  const failed = advanceTavernRoomListStatus(loading, "failure");
  assert.equal(tavernRoomListPresentation(loading, 0).loadingFirstPage, true);
  const failedView = tavernRoomListPresentation(failed, 0);
  assert.equal(failedView.showEmpty, false);
  assert.equal(failedView.showCount, false);
  assert.match(failedView.firstPageError, /暂时无法载入/);
  // An independently restored room can remain visible alongside the list error.
  assert.equal(tavernRoomListPresentation(failed, 1).showCount, true);
  assert.equal(
    tavernRoomListPresentation(failed, 1).firstPageError,
    failedView.firstPageError,
  );

  const retry = advanceTavernRoomListStatus(failed, "start");
  assert.equal(tavernRoomListPresentation(retry, 0).showEmpty, false);
  const ready = advanceTavernRoomListStatus(retry, "success");
  assert.equal(tavernRoomListPresentation(ready, 0).showEmpty, true);
  assert.equal(tavernRoomListPresentation(ready, 2).showEmpty, false);
  assert.equal(tavernRoomListPresentation(ready, 2).firstPageError, "");
});

test("a failed first-page refresh distinguishes a retained list from an initial error", () => {
  const refreshing = advanceTavernRoomListStatus("ready", "start");
  const stale = advanceTavernRoomListStatus(refreshing, "failure");
  assert.equal(tavernRoomListPresentation(stale, 2).showCount, true);
  assert.match(tavernRoomListPresentation(stale, 2).firstPageError, /当前列表已保留/);
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
