import type { TavernRun } from "@vibe-learner/shared";

import type { TavernRoomDraft } from "./tavern-workspace-state";

export function reconcileCanceledTavernDraft(draft: TavernRoomDraft, run: TavernRun) {
  const pending = draft.pendingTurn;
  if (
    !pending ||
    run.status !== "canceled" ||
    run.triggerKind !== "user_message" ||
    !run.inputMessageId ||
    pending.key !== run.idempotencyKey
  )
    return { draft, clearComposer: false };

  const clearComposer =
    draft.message.trim() === pending.content &&
    draft.guidance.trim() === pending.guidance;
  return {
    draft: clearComposer
      ? { message: "", guidance: "" }
      : { message: draft.message, guidance: draft.guidance },
    clearComposer,
  };
}
