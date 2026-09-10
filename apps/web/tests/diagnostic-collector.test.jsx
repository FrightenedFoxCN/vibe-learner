import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { StrictMode } from "react";
import { cleanup, render } from "@testing-library/react";
import { PathnameContext } from "next/dist/shared/lib/hooks-client-context.shared-runtime.js";
import { DiagnosticCollector } from "../components/diagnostic-collector.tsx";
import { diagnosticContext, diagnosticSnapshot } from "../lib/diagnostics.ts";

afterEach(cleanup);
after(() => dom.window.close());
test("actual collector fences StrictMode cleanup and balances route lifetimes without Debug", () => {
  const tree = path => <StrictMode><PathnameContext.Provider value={path}><DiagnosticCollector /></PathnameContext.Provider></StrictMode>;
  const view = render(tree("/plan"));
  const previous = diagnosticContext();
  assert.equal(previous.page_path, "/plan");
  view.rerender(tree("/study"));
  const current = diagnosticContext();
  assert.equal(current.page_path, "/study");
  assert.notEqual(previous.page_view_id, current.page_view_id);
  view.unmount();
  assert.equal(diagnosticContext().page_view_id, null);
  const events = diagnosticSnapshot().events;
  const entered = events.filter(event => event.name === "page_entered");
  assert.ok(entered.length >= 3); // StrictMode replay plus route replacement.
  for (const start of entered) {
    const ends = events.filter(event => event.name === "page_left" && event.page_view_id === start.page_view_id);
    assert.equal(ends.length, 1);
    assert.equal(ends[0].page_path, start.page_path);
    assert.equal(ends[0].action_id, start.action_id);
    assert.ok(ends[0].duration_ms >= 0);
  }
});
