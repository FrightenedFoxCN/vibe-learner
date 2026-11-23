import assert from "node:assert/strict";
import { test } from "node:test";
import { documentPlanningTextBlockReason } from "../lib/document-planning-readiness.ts";

test("zero chunks provide a usable fallback and explain disabled OCR", () => {
  const reason = documentPlanningTextBlockReason({
    chunkCount: 0,
    ocrStatus: "unavailable",
  });
  assert.match(reason, /OCR 不可用.*未从教材提取到可用文本/);
  assert.match(reason, /含文本层.*仅学习目标/);
});

test("zero chunks without an unavailable OCR status do not invent that status", () => {
  const reason = documentPlanningTextBlockReason({
    chunkCount: 0,
    ocrStatus: "failed",
  });
  assert.match(reason, /未从教材提取到可用文本/);
  assert.doesNotMatch(reason, /OCR 不可用/);
});

test("readable chunks are not blocked when OCR is unavailable or partial", () => {
  for (const ocrStatus of ["unavailable", "partial"] as const) {
    assert.equal(documentPlanningTextBlockReason({ chunkCount: 1, ocrStatus }), "");
  }
});
