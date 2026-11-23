import assert from "node:assert/strict";
import test from "node:test";

import { normalizeTavernErrorDetail } from "../lib/tavern-decode.ts";
import { forgetRejectedTavernTurn } from "../lib/tavern-rejected-turn.ts";

const draft = {
  message: "keep this text",
  guidance: "keep guidance",
  pendingTurn: {
    key: "first-key",
    content: "keep this text",
    guidance: "keep guidance",
    targetPersonaIds: ["actor"],
    expectedRoomRevision: 2,
  },
};
function conflict(runId = "") {
  return normalizeTavernErrorDetail({
    detail: {
      code: "tavern_revision_conflict",
      run_id: runId,
      child_run_id: "",
      current_revision: 3,
      recovery_action: "reload_room",
    },
  });
}

test("a definite revision rejection releases only the matching request key", () => {
  assert.deepEqual(forgetRejectedTavernTurn(draft, "first-key", 409, conflict()), {
    message: draft.message,
    guidance: draft.guidance,
  });
  assert.equal(forgetRejectedTavernTurn(draft, "other-key", 409, conflict()), draft);
});

test("ambiguous or admitted results retain the original request identity", () => {
  assert.equal(forgetRejectedTavernTurn(draft, "first-key", undefined, null), draft);
  assert.equal(forgetRejectedTavernTurn(draft, "first-key", 502, conflict()), draft);
  assert.equal(
    forgetRejectedTavernTurn(draft, "first-key", 409, conflict("admitted-run")),
    draft,
  );
});
