import { dom } from "./support/dom.js";
import React from "react";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { cleanup, fireEvent, render } from "@testing-library/react";
import { AppRouterContext } from "next/dist/shared/lib/app-router-context.shared-runtime.js";
import { DocumentSetup } from "../components/document-setup.tsx";

afterEach(cleanup);
after(() => dom.window.close());
test("Document Setup rejects printed labels and carries the physical range into an explicit generation", () => {
  const generated = [],
    cached = [];
  const props = {
    personas: [],
    selectedPersonaId: "",
    onSelectPersonaId: () => {},
    onGenerate: (value) => generated.push(value),
    onInterruptGeneration: () => {},
    isBusy: false,
    sceneLibraryItems: [],
    selectedSceneLibraryId: "",
    onSelectSceneLibraryId: () => {},
    planStreamEvents: [],
    planStreamStatus: "idle",
    processStreamEvents: [],
    processStreamStatus: "idle",
    canInterruptGeneration: false,
    isInterruptingGeneration: false,
    cachedState: {
      generationMode: "document",
      objective: "Learn",
      file: new File(["pdf"], "book.pdf"),
      physicalPageRanges: "100–103",
    },
    onCachedStateChange: (value) => cached.push(value),
  };
  const view = render(
    <AppRouterContext.Provider value={{ push() {}, replace() {}, prefetch() {} }}>
      <DocumentSetup {...props} />
    </AppRouterContext.Provider>,
  );
  const range = view.getByRole("textbox", { name: "PDF 物理页范围（可选）" });
  assert.equal(range.value, "100–103");
  fireEvent.change(range, { target: { value: "iv-viii" } });
  assert.ok(view.getByRole("alert"));
  assert.equal(
    view.getByRole("button", { name: "生成计划", exact: true }).disabled,
    true,
  );
  fireEvent.change(range, { target: { value: "100–103" } });
  fireEvent.click(view.getByRole("button", { name: "生成计划", exact: true }));
  assert.equal(generated[0].physicalPageRanges, "100–103");
  assert.equal(cached.at(-1).physicalPageRanges, "100–103");
  fireEvent.change(view.getByRole("combobox", { name: "创建方式" }), {
    target: { value: "goal_only" },
  });
  fireEvent.click(view.getByRole("button", { name: "按目标生成", exact: true }));
  assert.equal(generated[1].physicalPageRanges, "");
});

test("HTTP planning transport serializes the explicit physical constraint without changing coordinates", async () => {
  const { createLearningPlan } = await import("../lib/data/learning-plans.ts");
  const { physicalPageIntent, parsePhysicalPdfRanges } =
    await import("../lib/planning-page-scope.ts");
  const original = globalThis.fetch;
  let captured;
  try {
    globalThis.fetch = async (_url, init) => {
      captured = JSON.parse(init.body);
      return Response.json({ detail: "probe-only" }, { status: 503 });
    };
    await assert.rejects(
      createLearningPlan({
        documentId: "doc",
        personaId: "mentor",
        clientRequestId: "physical-http",
        expectedDocumentUpdatedAt: "revision",
        objective: "Read",
        planningIntent: physicalPageIntent(parsePhysicalPdfRanges("100–103")),
      }),
    );
    assert.deepEqual(captured.planning_intent.pdf_page_ranges, {
      status: "user_explicit",
      value: [{ page_start: 100, page_end: 103 }],
    });
  } finally {
    globalThis.fetch = original;
  }
});
