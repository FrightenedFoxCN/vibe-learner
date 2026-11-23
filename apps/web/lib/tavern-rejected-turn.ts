import type { TavernErrorDetail } from "@vibe-learner/shared";

import type { TavernRoomDraft } from "./tavern-workspace-state";

export function forgetRejectedTavernTurn(
  draft: TavernRoomDraft,
  requestKey: string,
  status: number | undefined,
  detail: TavernErrorDetail | null,
): TavernRoomDraft {
  const pending = draft.pendingTurn;
  // The POST route supplies a run ID when this key already owns a run.
  // Absence in the bounded runs list alone never proves rejection.
  if (
    pending?.key !== requestKey ||
    status !== 409 ||
    detail?.code !== "tavern_revision_conflict" ||
    detail.runId !== undefined
  )
    return draft;
  return { message: draft.message, guidance: draft.guidance };
}
