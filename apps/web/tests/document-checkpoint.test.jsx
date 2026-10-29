import { dom } from "./support/dom.js";
import React from "react";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { DocumentCheckpointPanel } from "../components/document-checkpoint-panel.tsx";
import { decodeDocumentCheckpoint } from "../lib/document-checkpoint-decode.ts";
import { decodeDocumentRecord } from "../lib/document-decode.ts";
import { wireUnitRevision } from "./support/study-unit-revision-wire.ts";

afterEach(() => {
  cleanup();
  window.sessionStorage.clear();
});
after(() => dom.window.close());
function wire(status = "failed") {
  return {
    contract_version: "document-checkpoint-response-v1",
    operation_id: "document-process-op-source",
    document_id: "document-1",
    operation_status: status,
    page_count: 2,
    completed_page_count: 1,
    stage: "pages",
    force_ocr: true,
    storage_limited: false,
    child_operation_id: null,
    pages: [
      { page_number: 1, text_preview: "Saved OCR text", extraction_source: "ocr" },
    ],
    study_units: [],
    result: status === "committed" ? wireUnitRevision().preview.base_document : null,
    projection_state: status === "committed" ? "committed" : "checkpoint_only",
  };
}
const record = (status = "failed") =>
  decodeDocumentCheckpoint(wire(status), "document-1");
test("decoder rejects malformed counts, states and false commit claims", () => {
  for (const patch of [
    { completed_page_count: 3 },
    { force_ocr: "false" },
    { operation_status: "completed" },
    { projection_state: "committed" },
    { stage: "other" },
    { result: wireUnitRevision().preview.base_document },
  ])
    assert.throws(() =>
      decodeDocumentCheckpoint({ ...wire(), ...patch }, "document-1"),
    );
  assert.equal(record().projectionState, "checkpoint_only");
  assert.equal(record("committed").result.id, "document-1");
});

test("resume uses immutable source identity; response loss recovers child through GET without another POST", async () => {
  let reads = 0,
    writes = 0,
    continued = 0;
  const committed = {
    ...record("committed"),
    operationId: "document-process-op-child",
  };
  const port = {
    getDocumentCheckpoint: async (_doc, id) => {
      reads++;
      return id === committed.operationId
        ? committed
        : reads === 1
          ? record()
          : { ...record(), childOperationId: committed.operationId };
    },
    processDocument: async (doc, options) => {
      writes++;
      assert.equal(doc, "document-1");
      assert.equal(options.resumeFromOperationId, record().operationId);
      assert.equal(options.forceOcr, true);
      throw new Error("lost response");
    },
  };
  const view = render(
    <DocumentCheckpointPanel
      documentId="document-1"
      status="error"
      port={port}
      onContinue={() => continued++}
    />,
  );
  await waitFor(() => assert.match(view.container.textContent, /已保存 1\/2 页/));
  assert.match(view.container.textContent, /尚未提交/);
  fireEvent.click(
    view.getByRole("button", { name: "从保存进度继续处理", exact: true }),
  );
  await waitFor(() => assert.match(view.container.textContent, /尚未确认/));
  fireEvent.click(view.getByRole("button", { name: "查询保存进度", exact: true }));
  await waitFor(() =>
    assert.ok(view.getByRole("button", { name: "使用该教材生成计划", exact: true })),
  );
  fireEvent.click(
    view.getByRole("button", { name: "使用该教材生成计划", exact: true }),
  );
  assert.equal(continued, 1);
  assert.equal(writes, 1);
  assert.equal(reads, 3);
});

test("persisted document identity survives remount and late resume cannot update the next document", async () => {
  let resolve;
  const pending = new Promise((yes) => {
    resolve = yes;
  });
  const port = {
    getDocumentCheckpoint: async (id) => ({ ...record(), documentId: id }),
    processDocument: () => pending,
  };
  const view = render(
    <DocumentCheckpointPanel
      documentId="document-1"
      status="error"
      port={port}
      onContinue={() => assert.fail("late document")}
    />,
  );
  await waitFor(() =>
    assert.ok(view.getByRole("button", { name: "从保存进度继续处理" })),
  );
  view.unmount();
  const next = render(
    <DocumentCheckpointPanel
      documentId=""
      status="idle"
      port={port}
      onContinue={() => assert.fail("late document")}
    />,
  );
  await waitFor(() =>
    assert.ok(next.getByRole("button", { name: "从保存进度继续处理" })),
  );
  fireEvent.click(next.getByRole("button", { name: "从保存进度继续处理" }));
  next.rerender(
    <DocumentCheckpointPanel
      documentId="document-2"
      status="error"
      port={port}
      onContinue={() => assert.fail("late document")}
    />,
  );
  await act(async () =>
    resolve(decodeDocumentRecord(wireUnitRevision().preview.base_document)),
  );
  await waitFor(() =>
    assert.ok(next.getByRole("button", { name: "从保存进度继续处理" })),
  );
  assert.equal(next.queryByRole("button", { name: "使用该教材生成计划" }), null);
});
