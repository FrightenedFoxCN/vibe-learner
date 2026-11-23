import assert from "node:assert/strict";
import test from "node:test";

import type { TavernRun } from "@vibe-learner/shared";

import { confirmTavernCancellation } from "../lib/tavern-cancel-confirmation.ts";
import { reconcileCanceledTavernDraft } from "../lib/tavern-canceled-draft.ts";

const canceled = {
  id: "run-1",
  idempotencyKey: "key",
  triggerKind: "user_message",
  inputMessageId: "message-1",
  status: "canceled",
} as TavernRun;
const base = {
  runId: canceled.id,
  onCancelError: () => {},
  isCurrent: () => true,
};

test("a lost cancellation response still clears the matching composer via read-back", async () => {
  const errors: unknown[] = [];
  const confirmed = await confirmTavernCancellation({
    ...base,
    cancel: async () => {
      throw new Error("disconnected");
    },
    readRuns: async () => [canceled],
    onCancelError: (error) => errors.push(error),
  });
  assert.equal(errors.length, 1);
  assert.ok(confirmed);
  const result = reconcileCanceledTavernDraft(
    {
      message: "sent",
      guidance: "hint",
      pendingTurn: {
        key: "key",
        content: "sent",
        guidance: "hint",
        targetPersonaIds: ["persona"],
        expectedRoomRevision: 1,
      },
    },
    confirmed,
  );
  assert.deepEqual(result, {
    draft: { message: "", guidance: "" },
    clearComposer: true,
  });
});

test("confirmed response survives missing read-back; wrong or pending run is not proof", async () => {
  assert.equal(
    await confirmTavernCancellation({
      ...base,
      cancel: async () => canceled,
      readRuns: async () => undefined,
    }),
    canceled,
  );
  assert.equal(
    await confirmTavernCancellation({
      ...base,
      cancel: async () => ({ ...canceled, id: "wrong" }),
      readRuns: async () => [{ ...canceled, status: "pending" }],
    }),
    undefined,
  );
});

test("an abandoned room does not consume a confirmation from a late read", async () => {
  let current = true;
  assert.equal(
    await confirmTavernCancellation({
      ...base,
      cancel: async () => canceled,
      isCurrent: () => current,
      readRuns: async () => {
        current = false;
        return [canceled];
      },
    }),
    undefined,
  );
});
