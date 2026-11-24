import assert from "node:assert/strict";
import test from "node:test";
import { AsyncResultFence } from "../lib/async-result-fence.ts";
import { resolvePersonaPromptSuggestion } from "../lib/persona-prompt-suggestion.ts";

for (const transition of ["import", "edit", "change persona"]) {
  test(`${transition} invalidates a shown suggestion after its assist request settled`, () => {
    let draftRevision = 1;
    const fieldTarget = "persona-setting";
    const scope = () => ({ subjectId: "persona:A", draftRevision, fieldTarget });
    const fence = new AsyncResultFence();
    const ticket = fence.begin(scope());
    assert.equal(fence.decide(ticket, scope()), "apply");
    // The setting assist may first update slots; the suggestion owns that resulting draft.
    const suggestedAt = ++draftRevision;
    const old = {
      value: "old constraints",
      source: "assist",
      isCurrent: () => draftRevision === suggestedAt,
    };
    assert.equal(fence.settle(ticket), true);
    assert.equal(resolvePersonaPromptSuggestion(old, old), "old constraints");

    draftRevision++;
    assert.equal(resolvePersonaPromptSuggestion(old, old), null);
    assert.equal(resolvePersonaPromptSuggestion(old, null), null);
  });
}

test("a stale Apply callback cannot apply a newer publication, even with identical text", () => {
  const old = { value: "same text", source: "assist", isCurrent: () => true };
  const latest = { ...old };
  assert.equal(resolvePersonaPromptSuggestion(old, latest), null);
  assert.equal(resolvePersonaPromptSuggestion(latest, latest), "same text");
});
