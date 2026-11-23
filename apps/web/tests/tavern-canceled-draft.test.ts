import assert from "node:assert/strict";
import test from "node:test";

import type { TavernRun } from "@vibe-learner/shared";

import { reconcileCanceledTavernDraft } from "../lib/tavern-canceled-draft.ts";

const draft = {
  message: "draft text",
  guidance: "guidance",
  pendingTurn: {
    key: "draft-key",
    content: "draft text",
    guidance: "guidance",
    targetPersonaIds: ["actor"],
    expectedRoomRevision: 2,
  },
};
const canceled = {
  status: "canceled",
  triggerKind: "user_message",
  inputMessageId: "input-1",
  idempotencyKey: "draft-key",
} as TavernRun;

test("canceling unrelated input, continue, or retry does not consume the draft", () => {
  for (const run of [
    { ...canceled, idempotencyKey: "other-tab" },
    { ...canceled, triggerKind: "continue" as const },
    { ...canceled, triggerKind: "retry" as const },
    { ...canceled, inputMessageId: "" },
    { ...canceled, status: "pending" as const },
  ]) {
    assert.deepEqual(reconcileCanceledTavernDraft(draft, run), {
      draft,
      clearComposer: false,
    });
  }
});

test("only matching persisted input clears the composer; newer edits survive", () => {
  assert.deepEqual(reconcileCanceledTavernDraft(draft, canceled), {
    draft: { message: "", guidance: "" },
    clearComposer: true,
  });
  assert.deepEqual(
    reconcileCanceledTavernDraft({ ...draft, message: "new text" }, canceled),
    {
      draft: { message: "new text", guidance: "guidance" },
      clearComposer: false,
    },
  );
});
