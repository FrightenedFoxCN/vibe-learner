import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { StrictMode } from "react";
import { cleanup, render } from "@testing-library/react";

import { DebugProvider, useLearningDebugSnapshot, usePublishLearningDebugSnapshot } from "../components/debug-provider.tsx";
import { installDOM } from "./support/dom.js";

const dom = installDOM();
afterEach(cleanup);
after(() => dom.window.close());

function Reader() {
  const snapshot = useLearningDebugSnapshot();
  return <output role="status">{snapshot?.processStreamStatus ?? "no-learning-owner"}</output>;
}

function Publisher({ snapshot }) {
  usePublishLearningDebugSnapshot(snapshot);
  return null;
}

function snapshot(status) {
  return { activeDocument: null, selectedPersona: undefined, studySession: null, response: null,
    processStreamDocumentId: "", processStreamEvents: [], processStreamStatus: status,
    planStreamDocumentId: "", planStreamEvents: [], planStreamStatus: "idle" };
}

test("Debug can render without a learning provider or network initialization", () => {
  const original = globalThis.fetch;
  const calls = [];
  globalThis.fetch = (...args) => { calls.push(args); throw new Error("unexpected request"); };
  try {
    const view = render(<DebugProvider><Reader /></DebugProvider>);
    assert.equal(view.getByRole("status").textContent, "no-learning-owner");
    assert.deepEqual(calls, []);
  } finally {
    globalThis.fetch = original;
  }
});

test("Published snapshots update and are cleared when the learning owner leaves", () => {
  const renderTree = (value) => <StrictMode><DebugProvider>
    {value ? <Publisher snapshot={value} /> : null}<Reader />
  </DebugProvider></StrictMode>;
  const view = render(renderTree(snapshot("running")));
  assert.equal(view.getByRole("status").textContent, "running");
  view.rerender(renderTree(snapshot("completed")));
  assert.equal(view.getByRole("status").textContent, "completed");
  view.rerender(renderTree(null));
  assert.equal(view.getByRole("status").textContent, "no-learning-owner");
  view.rerender(renderTree(snapshot("restored")));
  assert.equal(view.getByRole("status").textContent, "restored");
});
