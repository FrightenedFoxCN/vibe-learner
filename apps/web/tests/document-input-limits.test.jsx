import { dom } from "./support/dom.js";
import React from "react";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { after, afterEach, test } from "node:test";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime.js";
import { DOCUMENT_INPUT_LIMITS } from "@vibe-learner/shared/document-input-limits";
import { DocumentSetup } from "../components/document-setup.tsx";
import { documentUploadError } from "../lib/document-upload-validation.ts";
import { uploadDocument } from "../lib/api.ts";

afterEach(cleanup);
after(() => dom.window.close());

test("browser limits match the Python golden and permit exactly 64 MiB", () => {
  const fixture = JSON.parse(
    readFileSync(
      new URL(
        "../../../packages/shared/fixtures/document-input-limits-v1.json",
        import.meta.url,
      ),
      "utf8",
    ),
  );
  assert.deepEqual(DOCUMENT_INPUT_LIMITS, fixture);
  assert.equal(
    documentUploadError({ size: DOCUMENT_INPUT_LIMITS.upload_max_bytes }),
    "",
  );
  assert.match(
    documentUploadError({ size: DOCUMENT_INPUT_LIMITS.upload_max_bytes + 1 }),
    /64 MiB/,
  );
});

test("upload transport refuses oversized files before FormData or fetch", async () => {
  const originalFetch = globalThis.fetch;
  let requests = 0;
  globalThis.fetch = async () => {
    requests++;
    throw new Error("unexpected fetch");
  };
  try {
    await assert.rejects(
      uploadDocument({ size: DOCUMENT_INPUT_LIMITS.upload_max_bytes + 1 }),
      /拆分或压缩/,
    );
    assert.equal(requests, 0);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("Document Setup explains oversize rejection and a replacement file restores generation", () => {
  const generated = [];
  const largeFile = new File(["pdf"], "too-large.pdf");
  Object.defineProperty(largeFile, "size", {
    value: DOCUMENT_INPUT_LIMITS.upload_max_bytes + 1,
  });
  const view = render(
    <AppRouterContext.Provider value={{ push() {}, replace() {}, prefetch() {} }}>
      <DocumentSetup
        personas={[]}
        selectedPersonaId=""
        onSelectPersonaId={() => {}}
        onGenerate={(input) => generated.push(input)}
        onInterruptGeneration={() => {}}
        isBusy={false}
        sceneLibraryItems={[]}
        selectedSceneLibraryId=""
        onSelectSceneLibraryId={() => {}}
        planStreamEvents={[]}
        planStreamStatus="idle"
        processStreamEvents={[]}
        processStreamStatus="idle"
        canInterruptGeneration={false}
        isInterruptingGeneration={false}
        cachedState={{
          generationMode: "document",
          file: largeFile,
          objective: "Read",
          physicalPageRanges: "",
        }}
      />
    </AppRouterContext.Provider>,
  );
  assert.match(view.getByRole("alert").textContent, /拆分或压缩/);
  const button = view.getByRole("button", { name: "生成计划", exact: true });
  assert.equal(button.disabled, true);
  fireEvent.click(button);
  assert.equal(generated.length, 0);
  const smallFile = new File(["pdf"], "small.pdf");
  fireEvent.change(view.getByLabelText("教材文件（PDF）"), {
    target: { files: [smallFile] },
  });
  assert.equal(view.queryByRole("alert"), null);
  assert.equal(button.disabled, false);
  fireEvent.click(button);
  assert.equal(generated.length, 1);
  assert.equal(generated[0].file, smallFile);
});

test("HTTP limit failures retain their recoverable server message", async () => {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () =>
    Response.json(
      {
        detail: {
          contract_version: "document-input-error-v1",
          code: "document_page_limit_exceeded",
          message: "PDF 超过 512 个物理页，请拆分后重新上传。",
          recovery_action: "split_or_reexport_pdf",
        },
      },
      { status: 413 },
    );
  try {
    await assert.rejects(
      uploadDocument(new File(["pdf"], "pages.pdf")),
      /512 个物理页.*拆分/,
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});
