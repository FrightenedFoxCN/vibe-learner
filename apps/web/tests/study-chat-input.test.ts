import assert from "node:assert/strict";
import test from "node:test";
import { hasStudyLearnerInput } from "../lib/study-chat-input.ts";

test("whitespace and empty files do not enable send", () => {
  assert.equal(hasStudyLearnerInput(" \n\t", []), false);
  assert.equal(hasStudyLearnerInput("", [{ size: 0 }]), false);
});

test("text-only and attachment-only sends remain available", () => {
  assert.equal(hasStudyLearnerInput("问题", []), true);
  assert.equal(hasStudyLearnerInput(" ", [{ size: 0 }, { size: 3 }]), true);
});
