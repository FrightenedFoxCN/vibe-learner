import { dom } from "./support/dom.js";
import React from "react";
import assert from "node:assert/strict";
import { after, afterEach, test } from "node:test";
import { act, cleanup, fireEvent, render, waitFor } from "@testing-library/react";
import { StudyUnitRevisionPanel } from "../components/study-unit-revision-panel.tsx";
import { decodeStudyUnitRevision } from "../lib/study-unit-revision-decode.ts";
import { wireUnitRevision } from "./support/study-unit-revision-wire.ts";

afterEach(cleanup);
after(() => dom.window.close());
const ready = () => decodeStudyUnitRevision(wireUnitRevision(), "plan-1", "document-1");
const accepted = () => decodeStudyUnitRevision(wireUnitRevision(true), "plan-1", "document-1");
const props = { plan: { id: "plan-1", documentId: "document-1" }, document: ready().preview.baseDocument };
function deferred() {
  let resolve;
  const promise = new Promise(yes => { resolve = yes; });
  return { promise, resolve };
}

test("lost acceptance response disables decisions until query-only read-back", async () => {
  let reads = 0, writes = 0, refreshes = 0;
  const port = {
    getStudyUnitRevision: async () => ++reads === 1 ? ready() : accepted(),
    decideStudyUnitRevision: async () => { writes++; throw new Error("response lost"); },
  };
  const view = render(<StudyUnitRevisionPanel {...props} port={port} onRefresh={async () => { refreshes++; }} />);
  await waitFor(() => assert.ok(view.getByRole("button", { name: "确认教材修订" })));
  assert.match(view.getByRole("table").textContent, /修改并保留标识/);
  fireEvent.click(view.getByRole("button", { name: "确认教材修订" }));
  await waitFor(() => assert.match(view.container.textContent, /暂时无法确认结果/));
  assert.equal(view.getByRole("button", { name: "确认教材修订" }).disabled, true);
  assert.equal(view.getByRole("button", { name: "拒绝教材修订" }).disabled, true);
  fireEvent.click(view.getByRole("button", { name: "查询教材修订结果" }));
  await waitFor(() => assert.equal(refreshes, 1));
  assert.match(view.container.textContent, /教材单元已更新/);
  assert.equal(writes, 1);
  assert.equal(reads, 2);
});

test("stale document disables acceptance while rejection leaves the document untouched", async () => {
  const actions = [];
  const port = { getStudyUnitRevision: async () => ready(), decideStudyUnitRevision: async (...args) => {
    actions.push(args); return { ...ready(), status: "rejected" };
  } };
  const view = render(<StudyUnitRevisionPanel {...props} document={{ ...props.document, revision: 4 }} port={port} onRefresh={async () => assert.fail("reject must not refresh a mutation")} />);
  await waitFor(() => assert.ok(view.getByRole("button", { name: "拒绝教材修订" })));
  assert.equal(view.getByRole("button", { name: "确认教材修订" }).disabled, true);
  fireEvent.click(view.getByRole("button", { name: "拒绝教材修订" }));
  await waitFor(() => assert.match(view.container.textContent, /已拒绝教材修订/));
  assert.equal(actions.length, 1);
  assert.equal(actions[0].at(-1), "reject");
});

test("switching plan and unmounting fence late responses without posting decisions", async () => {
  const first = deferred(), second = deferred();
  let reads = 0;
  const port = { getStudyUnitRevision: () => ++reads === 1 ? first.promise : second.promise,
    decideStudyUnitRevision: async () => assert.fail("read-back must not submit") };
  const view = render(<StudyUnitRevisionPanel {...props} port={port} onRefresh={async () => assert.fail("late response")} />);
  view.rerender(<StudyUnitRevisionPanel {...props} plan={{ id: "plan-2", documentId: "document-1" }} port={port} onRefresh={async () => {}} />);
  await act(async () => first.resolve(accepted()));
  assert.equal(view.container.textContent, "");
  view.unmount();
  await act(async () => second.resolve(ready()));
  assert.equal(reads, 2);
});
