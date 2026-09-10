import { dom } from "./support/dom.js";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { after, afterEach, test } from "node:test";
import { StrictMode } from "react";
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { DiagnosticTimeline } from "../components/diagnostic-timeline.tsx";
import { registerDiagnosticPage } from "../lib/diagnostics.ts";
const fixture = JSON.parse(readFileSync(new URL("../../../packages/shared/fixtures/diagnostics/query-pages-v1.json", import.meta.url), "utf8"));
const original = globalThis.fetch;
const originalFormData = globalThis.FormData;
globalThis.FormData = dom.window.FormData;
afterEach(() => { cleanup(); globalThis.fetch = original; });
after(() => { globalThis.FormData = originalFormData; dom.window.close(); });
function events(id, sequence = 1, more = false) {
  const page = structuredClone(fixture.events);
  page.items[0].event.event_id = id;
  page.items[0].sequence = sequence;
  page.next_cursor = sequence;
  page.has_more = more;
  return page;
}

test("timeline lazily reads only events, fences stale filter replies and aborts on unmount", async () => {
  const pending = [];
  globalThis.fetch = (url, init) => new Promise(resolve => pending.push({ url, signal: init.signal, resolve }));
  const view = render(<StrictMode><DiagnosticTimeline /></StrictMode>);
  await waitFor(() => assert.equal(pending.length, 2));
  assert.ok(pending.every(item => item.url.includes("/diagnostics/events?")));
  assert.equal(pending[0].signal.aborted, true);
  fireEvent.change(view.getByLabelText("页面"), { target: { value: "/study" } });
  fireEvent.click(view.getByRole("button", { name: "应用筛选" }));
  await waitFor(() => assert.ok(pending.length >= 3));
  const latest = pending.at(-1);
  assert.equal(new URL(latest.url).searchParams.get("page_path"), "/study");
  await act(async () => { latest.resolve(Response.json(events("new-page"))); });
  await waitFor(() => assert.ok(view.container.textContent.includes("new-page")));
  await act(async () => { for (const item of pending.slice(0, -1)) item.resolve(Response.json(events("stale-page"))); });
  assert.ok(!view.container.textContent.includes("stale-page"));
  fireEvent.click(view.getByRole("button", { name: "刷新诊断" }));
  const refreshing = pending.at(-1);
  view.unmount();
  assert.equal(refreshing.signal.aborted, true);
});

test("pagination merges once and rejects duplicate event identity across pages", async () => {
  const calls = [];
  globalThis.fetch = async url => {
    calls.push(url);
    return Response.json(calls.length === 1 ? events("duplicate", 1, true) : events("duplicate", 2));
  };
  const view = render(<DiagnosticTimeline />);
  await waitFor(() => assert.ok(view.getByRole("button", { name: "读取下一页事件" })));
  fireEvent.click(view.getByRole("button", { name: "读取下一页事件" }));
  await waitFor(() => assert.ok(view.getByRole("alert")));
  assert.equal(new URL(calls[1]).searchParams.get("after"), "1");
  assert.equal(view.container.querySelectorAll("article").length, 1);
});

test("current-page requests bind to registered identity and index loads only when selected", async () => {
  const page = registerDiagnosticPage("/plan");
  const calls = [];
  globalThis.fetch = async url => {
    calls.push(url);
    return Response.json(url.includes("harness-index") ? fixture.index : fixture.events);
  };
  const view = render(<DiagnosticTimeline currentPageOnly />);
  await waitFor(() => assert.ok(calls.length));
  assert.equal(new URL(calls[0]).searchParams.get("page_view_id"), page.id);
  view.unmount(); page.dispose();
  const global = render(<DiagnosticTimeline />);
  await waitFor(() => assert.equal(calls.length, 2));
  assert.ok(calls.every(url => !url.includes("harness-index")));
  fireEvent.click(global.getByRole("button", { name: "Harness 索引" }));
  await waitFor(() => assert.ok(calls.some(url => url.includes("harness-index"))));
  assert.ok(!calls.some(url => url.includes("operation-links")));
});

test("valid next pages append and query failures remain visibly distinct from empty history", async () => {
  let calls = 0;
  globalThis.fetch = async () => {
    calls++;
    if (calls === 3) return new Response("PRIVATE_FAILURE", { status: 503 });
    return Response.json(events(`event-${calls}`, calls, calls === 1));
  };
  const view = render(<DiagnosticTimeline />);
  await waitFor(() => assert.ok(view.getByRole("button", { name: "读取下一页事件" })));
  fireEvent.click(view.getByRole("button", { name: "读取下一页事件" }));
  await waitFor(() => assert.equal(view.container.querySelectorAll("article").length, 2));
  fireEvent.click(view.getByRole("button", { name: "刷新诊断" }));
  await waitFor(() => assert.ok(view.getByRole("alert")));
  assert.ok(!view.container.textContent.includes("PRIVATE_FAILURE"));
  assert.ok(!view.container.textContent.includes("当前筛选没有已保留的事件"));
});

test("retention gaps are visible and cannot masquerade as complete history", async () => {
  const result = events("retained", 2);
  Object.assign(result.retention, { removed_events: 1, removed_through_sequence: 1, cursor_gap: true, legacy_timestamp_rows: 3 });
  globalThis.fetch = async () => Response.json(result);
  const view = render(<DiagnosticTimeline />);
  await waitFor(() => assert.ok(view.container.textContent.includes("当前显示不代表完整历史")));
  assert.ok(view.container.textContent.includes("本次游标范围存在清理缺口"));
  assert.ok(view.container.textContent.includes("原始入库时间未知"));
});


test("writer coverage is lazy and explains unrecorded closure without claiming a crash", async () => {
  const calls = [];
  globalThis.fetch = async url => { calls.push(url); return Response.json(url.includes("/writers?") ? fixture.writers : fixture.events); };
  const view = render(<DiagnosticTimeline />);
  await waitFor(() => assert.equal(calls.length, 1));
  assert.ok(!calls[0].includes("/writers?"));
  fireEvent.click(view.getByRole("button", { name: "采集覆盖", exact: true }));
  await waitFor(() => assert.ok(view.container.textContent.includes("不代表已证实崩溃")));
  assert.ok(calls.at(-1).includes("/writers?"));
  assert.ok(view.container.textContent.includes("计数为已观察下限"));
});
