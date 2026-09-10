import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, beforeEach, test } from "node:test";
import { StrictMode } from "react";
import { act, cleanup, render } from "@testing-library/react";

import { DebugProvider, useLearningDebugSnapshot, usePublishLearningDebugSnapshot } from "../components/debug-provider.tsx";

import { registerDiagnosticPage } from "../lib/diagnostics.ts";
import { PageDebugProvider, usePageDebugSnapshot, useCurrentPageDebugSnapshot } from "../components/page-debug-context.tsx";
import { PathnameContext } from "next/dist/shared/lib/hooks-client-context.shared-runtime.js";
import { DiagnosticCollector } from "../components/diagnostic-collector.tsx";

let page;
beforeEach(() => { page = registerDiagnosticPage(); });
afterEach(() => { cleanup(); page.dispose(); });
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


for (const [name, Provider, publish, read, value, label] of [
  ["learning", DebugProvider, usePublishLearningDebugSnapshot, useLearningDebugSnapshot, snapshot, state => state?.processStreamStatus],
  ["page", PageDebugProvider, usePageDebugSnapshot, useCurrentPageDebugSnapshot, title => ({ title }), state => state?.title],
]) {
  test(`${name} snapshot ignores replaced owner's updates and cleanup under StrictMode`, () => {
    function Owner({ state }) { publish(state); return null; }
    function Output() { return <output role="status">{label(read()) ?? "empty"}</output>; }
    const old = value("old");
    const next = value("next");
    const tree = (oldState, nextState) => <StrictMode><Provider>
      {oldState && <Owner key="old" state={oldState} />}
      {nextState && <Owner key="next" state={nextState} />}
      <Output />
    </Provider></StrictMode>;
    const view = render(tree(old, null));
    assert.equal(view.getByRole("status").textContent, "old");
    view.rerender(tree(old, next));
    assert.equal(view.getByRole("status").textContent, "next");
    view.rerender(tree(value("late-old"), next));
    assert.equal(view.getByRole("status").textContent, "next");
    view.rerender(tree(null, next));
    assert.equal(view.getByRole("status").textContent, "next");
    view.rerender(tree(null, null));
    assert.equal(view.getByRole("status").textContent, "empty");
  });
}

test("actual route lifecycle hides stale page snapshots and publishes the replacement page", () => {
  function Owner({ title }) { usePageDebugSnapshot({ title }); return null; }
  function Output() { return <output role="status">{useCurrentPageDebugSnapshot()?.title ?? "empty"}</output>; }
  const tree = (path, title) => <StrictMode><PathnameContext.Provider value={path}>
    <DiagnosticCollector /><PageDebugProvider>{title && <Owner key={path} title={title} />}<Output /></PageDebugProvider>
  </PathnameContext.Provider></StrictMode>;
  const view = render(tree("/plan", "plan"));
  assert.equal(view.getByRole("status").textContent, "plan");
  view.rerender(tree("/settings", null));
  assert.equal(view.getByRole("status").textContent, "empty");
  view.rerender(tree("/settings", "settings"));
  assert.equal(view.getByRole("status").textContent, "settings");
  // Registration replacement invalidates the old page immediately, without requiring an unmount.
  act(() => { const replaced = registerDiagnosticPage("/tavern"); replaced.dispose(); });
  assert.equal(view.getByRole("status").textContent, "empty");
});
