import assert from "node:assert/strict";
import test from "node:test";
import { readBackFollowUpCancellation } from "../lib/study-follow-up-cancel.ts";

const before = {
  id: "session",
  revision: 2,
  pendingFollowUps: [{ id: "original", status: "pending" }],
};
const target = new Set(["original"]);

test("unchanged authoritative pending target can be rearmed", async () => {
  assert.deepEqual(
    await readBackFollowUpCancellation(before, target, async () => before),
    { state: "pending", session: before },
  );
});

test("lost response after cancellation does not rearm a stopped target", async () => {
  const after = {
    ...before,
    revision: 3,
    pendingFollowUps: [
      { id: "original", status: "canceled" },
      { id: "other", status: "pending" },
    ],
  };
  assert.deepEqual(
    await readBackFollowUpCancellation(before, target, async () => after),
    { state: "stopped", session: after },
  );
});

test("failed or stale readback cannot rearm the target", async () => {
  for (const read of [
    async () => {
      throw new Error("offline");
    },
    async () => ({ ...before, revision: 1 }),
    async () => ({ ...before, id: "other" }),
  ])
    assert.deepEqual(await readBackFollowUpCancellation(before, target, read), {
      state: "unknown",
    });
});
