import assert from "node:assert/strict";
import test from "node:test";

import { formatElapsedMs, formatTimestamp } from "../lib/format.ts";

const timestamp = "2024-01-02T00:04:05.987Z";

// Compare with native formatting to preserve local time without pinning ICU punctuation.
test("short and debug timestamps retain their original local display options", () => {
  const date = new Date(timestamp);
  assert.equal(
    formatTimestamp(timestamp, { style: "short" }),
    date.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    }),
  );
  assert.equal(
    formatTimestamp(timestamp, { style: "debug" }),
    date.toLocaleString("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
    }),
  );
});

test("full timestamps use the supplied zone or the host zone when omitted or empty", () => {
  const date = new Date(timestamp);
  for (const timeZone of ["UTC", "Asia/Shanghai", "America/Los_Angeles", ""]) {
    const expected = new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      second: "2-digit",
      hour12: false,
      ...(timeZone ? { timeZone } : {}),
    }).format(date);
    assert.equal(formatTimestamp(timestamp, { style: "full", timeZone }), expected);
    if (!timeZone)
      assert.equal(formatTimestamp(timestamp, { style: "full" }), expected);
  }
});

test("timestamps preserve caller-specific empty labels and return invalid strings verbatim", () => {
  const short = { style: "short" } as const;
  const debug = { style: "debug" } as const;
  const live = { style: "debug", empty: "实时事件" } as const;
  const full = { style: "full", timeZone: "Invalid/Zone" } as const;

  assert.equal(formatTimestamp("", short), "未知时间");
  assert.equal(formatTimestamp("", debug), "");
  assert.equal(formatTimestamp("", live), "实时事件");
  assert.equal(formatTimestamp(undefined, live), "实时事件");
  assert.equal(formatTimestamp("", full), "-");
  for (const options of [short, debug, live, full]) {
    for (const invalid of ["not-a-date", "   "]) {
      assert.equal(formatTimestamp(invalid, options), invalid);
    }
  }
  assert.throws(() => formatTimestamp(timestamp, full), RangeError);
});

test("elapsed milliseconds keep the falsy fallback, unit boundary, and fixed rounding", () => {
  for (const [value, expected] of [
    [0, "进行中"],
    [-0, "进行中"],
    [NaN, "进行中"],
    [-1, "-1 ms"],
    [999.9, "999.9 ms"],
    [1000, "1.0 s"],
    [1250, "1.3 s"],
    [60000, "60.0 s"],
  ] as const) {
    assert.equal(formatElapsedMs(value), expected);
  }
});
