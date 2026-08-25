import assert from "node:assert/strict";
import test from "node:test";

import {
  normalizeTavernRoomDetail,
  normalizeTavernRoomList,
  normalizeTavernRunList,
  normalizeTavernTurnResult,
} from "../lib/tavern-decode.ts";

const apiBaseUrl = process.env.TAVERN_TEST_API_URL;

test("strict Tavern decoders accept live backend room aggregates", {
  skip: !apiBaseUrl,
}, async () => {
  const roomPayload = await fetch(`${apiBaseUrl}/tavern/rooms`).then((response) => {
    assert.equal(response.ok, true);
    return response.json();
  });
  const roomPage = normalizeTavernRoomList(roomPayload);
  assert.ok(roomPage.items.length > 0, "live backend must expose a Tavern room fixture");
  const roomId = roomPage.items[0]!.id;

  const [detailPayload, runPayload] = await Promise.all([
    fetch(`${apiBaseUrl}/tavern/rooms/${roomId}?tail=true&limit=40`).then((response) => {
      assert.equal(response.ok, true);
      return response.json();
    }),
    fetch(`${apiBaseUrl}/tavern/rooms/${roomId}/runs?limit=50`).then((response) => {
      assert.equal(response.ok, true);
      return response.json();
    }),
  ]);

  const detail = normalizeTavernRoomDetail(detailPayload, roomId);
  const runs = normalizeTavernRunList(runPayload, roomId);
  assert.equal(detail.room.id, roomId);
  assert.ok(detail.messages.length > 0);
  assert.ok(runs.length > 0);

  const terminalRun = runs.find((run) => run.status !== "pending");
  assert.ok(terminalRun, "live backend must expose a terminal Tavern run fixture");
  const replayPayload = await fetch(
    `${apiBaseUrl}/tavern/rooms/${roomId}/runs/${terminalRun.id}/resume`,
    { method: "POST" }
  ).then((response) => {
    assert.equal(response.ok, true);
    return response.json();
  });
  const replay = normalizeTavernTurnResult(replayPayload, roomId);
  assert.equal(replay.run.id, terminalRun.id);
  assert.equal(replay.run.status, terminalRun.status);
});
