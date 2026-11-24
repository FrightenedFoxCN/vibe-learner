import assert from "node:assert/strict";
import test from "node:test";
import { diagnosticLinkPagination } from "../lib/diagnostic-link-pagination.ts";

import { parseDiagnosticTimeRange } from "../lib/diagnostic-time-range.ts";

test("diagnostic time ranges reject invalid, equal, and reversed bounds", () => {
  assert.equal(parseDiagnosticTimeRange("bad", "").ok, false);
  for (const until of ["2026-11-24T10:00", "2026-11-24T09:00"]) {
    assert.deepEqual(parseDiagnosticTimeRange("2026-11-24T10:00", until), {
      ok: false,
      field: "until",
      message: "结束时间必须晚于开始时间。",
    });
  }
  assert.deepEqual(parseDiagnosticTimeRange("", ""), {
    ok: true,
    since: undefined,
    until: undefined,
  });
  assert.deepEqual(
    parseDiagnosticTimeRange("2026-11-24T10:00+08:00", "2026-11-24T11:00+08:00"),
    {
      ok: true,
      since: "2026-11-24T02:00:00.000Z",
      until: "2026-11-24T03:00:00.000Z",
    },
  );
});

const cursor = "request-099";
const items = Array.from({ length: 100 }, (_, index) => ({
  operation_id: "harness-operation-" + "1".repeat(32),
  request_id: `request-` + String(index).padStart(3, "0"),
}));

test("a full page followed by an unavailable page keeps a retry, not an end marker", () => {
  assert.equal(
    diagnosticLinkPagination({ items, next_cursor: cursor, gap: null }, items.length)
      .next,
    "继续读取关联请求",
  );
  const unavailable = diagnosticLinkPagination(
    { items: [], next_cursor: cursor, gap: "diagnostic_store_unavailable" },
    items.length,
  );
  assert.match(unavailable.alert ?? "", /已读取的关联仍保留/);
  assert.equal(unavailable.next, "重试读取关联请求");
  assert.equal(unavailable.status, null);
});

test("initial empty and terminal empty pages do not look like store failure", () => {
  const gap = "no_correlation_recorded_or_retained";
  const initial = diagnosticLinkPagination({ items: [], next_cursor: "", gap }, 0);
  const terminal = diagnosticLinkPagination(
    { items: [], next_cursor: cursor, gap },
    items.length,
  );
  assert.equal(initial.status, "没有记录或保留关联请求。");
  assert.equal(terminal.status, "暂无更多保留的关联请求。");
  assert.equal(terminal.alert, null);
  assert.equal(terminal.next, null);
});
