import assert from "node:assert/strict";
import test from "node:test";
import { TAVERN_COPY_CONTRACT, RUN_STATUS_LABELS, STEP_STATUS_LABELS, TAVERN_COPY, tavernFailureNotice } from "../lib/tavern-copy.ts";

test("versioned Tavern run/step copy covers the complete product state vocabulary", () => {
  assert.equal(TAVERN_COPY_CONTRACT, "tavern-copy-v1");
  assert.deepEqual(Object.keys(RUN_STATUS_LABELS).sort(), ["canceled", "completed", "failed", "partial", "pending"]);
  assert.deepEqual(Object.keys(STEP_STATUS_LABELS).sort(), ["blocked", "canceled", "completed", "failed", "generating", "idle", "pending", "previous_blocked", "previous_canceled", "previous_completed", "previous_failed"]);
  for (const [key, pattern] of [["partial", /部分角色/], ["failed", /本轮未完成/], ["completed", /已完成/], ["pending", /等待/], ["canceled", /已取消/]] as const) {
    assert.match(RUN_STATUS_LABELS[key], pattern);
  }
  for (const key of ["blocked", "previous_blocked"] as const) {
    assert.match(STEP_STATUS_LABELS[key], /尚未执行/);
    assert.doesNotMatch(STEP_STATUS_LABELS[key], /失败|未通过|出错/);
  }
  assert.match(STEP_STATUS_LABELS.previous_failed, /上一轮/);
});

test("recovery, archive and cancel copy describes retained results and honest provider limits", () => {
  for (const text of [TAVERN_COPY.partial, TAVERN_COPY.retryIncomplete, TAVERN_COPY.recovered]) assert.match(text, /不会重复生成/);
  assert.match(TAVERN_COPY.failed, /恢复入口/);
  assert.match(TAVERN_COPY.blocked, /前序.*暂未执行/);
  assert.match(TAVERN_COPY.retryScope, /先前未完成/);
  assert.match(TAVERN_COPY.archived, /只读/);
  assert.match(TAVERN_COPY.canceled, /模型请求可能仍运行到超时/);
  assert.match(TAVERN_COPY.cancelUnconfirmed, /尚未确认.*刷新/);
  for (const text of Object.values(TAVERN_COPY)) assert.doesNotMatch(text, /叶节点|暴露为|failure_code|error_code|tavern_/);
});

test("structured stale/archive/retry failures stay actionable and never expose unrecognized codes", () => {
  const rows = [
    ["tavern_revision_conflict", /刷新.*确认/],
    ["tavern_continue_anchor_stale", /最新一条消息/],
    ["tavern_retry_context_changed", /不能继续旧恢复/],
    ["tavern_retry_already_created", /刷新查看结果/],
    ["tavern_room_not_active", /已归档.*恢复使用/],
    ["tavern_run_in_progress", /正在生成/],
    ["tavern_run_failed", /已保存的消息不会丢失/],
  ] as const;
  for (const [code, expected] of rows) {
    const text = tavernFailureNotice(code, "other", "请求未完成");
    assert.match(text, expected);
    assert.ok(!text.includes(code));
  }
  for (const code of ["UNTRUSTED_PRIVATE_PROVIDER_CODE", "__proto__", "toString"]) {
    assert.equal(tavernFailureNotice(code, "other", "请求未完成"), "请求未完成");
  }
  assert.match(tavernFailureNotice("", "decode", "请求未完成"), /数据未通过可靠性校验/);
  assert.match(tavernFailureNotice("", "network", "请求未完成"), /无法连接/);
});
