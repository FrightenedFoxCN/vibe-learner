import assert from "node:assert/strict";
import test from "node:test";
import type { TokenUsageCallRecord, TokenUsageDailyBucket } from "@vibe-learner/shared";
import {
  buildDayMap,
  buildFeatureModelSummary,
  filterUsageRecords,
  serializeUsageCsv,
  sumUsageRecords,
} from "../components/model-usage/model-usage-data.ts";
import { formatTimestamp } from "../lib/format.ts";

const call: TokenUsageCallRecord = {
  id: "1",
  createdAt: "2024-01-02T00:30:00Z",
  workflow: "planning",
  operationId: 'op,"1"',
  stage: "provider",
  feature: "plan",
  model: 'provider/"model"',
  promptTokens: 10,
  completionTokens: 3,
  totalTokens: 16,
};

test("workflow, operation and recorded calendar date compose without reordering", () => {
  const later = { ...call, id: "2", createdAt: "2024-01-02T23:59:00Z" };
  assert.deepEqual(
    filterUsageRecords(
      [
        later,
        { ...call, workflow: "study_chat" },
        { ...call, operationId: "other" },
        { ...call, createdAt: "2024-01-01T23:59:59Z" },
        call,
        { ...call, createdAt: "2024-01-03T00:00:00Z" },
      ],
      {
        workflow: "planning",
        operation: call.operationId,
        dateFrom: "2024-01-02",
        dateTo: "2024-01-02",
      },
    ),
    [later, call],
  );
});

test("aggregations keep independent counters and merge matching daily chart segments", () => {
  const records = [call, { ...call, totalTokens: 20 }];
  assert.deepEqual(sumUsageRecords(records), { prompt: 20, completion: 6, total: 36 });
  assert.deepEqual(buildFeatureModelSummary(records), [
    {
      feature: call.feature,
      model: call.model,
      promptTokens: 20,
      completionTokens: 6,
      totalTokens: 36,
      callCount: 2,
    },
  ]);
  const bucket: TokenUsageDailyBucket = {
    date: "2024-01-02",
    feature: call.feature,
    model: call.model,
    promptTokens: 10,
    completionTokens: 3,
    totalTokens: 16,
  };
  const days = buildDayMap([
    bucket,
    { ...bucket, date: "2024-01-01" },
    { ...bucket, totalTokens: 20 },
    { ...bucket, model: "other" },
  ]);
  assert.deepEqual(
    days.map((day) => [day.date, day.total]),
    [
      ["2024-01-01", 16],
      ["2024-01-02", 52],
    ],
  );
  assert.deepEqual(
    days[1].segments.map((segment) => [segment.model, segment.tokens]),
    [
      [call.model, 36],
      ["other", 16],
    ],
  );
});

test("CSV preserves BOM, column order, quoting and selected display timezone", () => {
  const timeZone = "America/Los_Angeles";
  const timestamp = formatTimestamp(call.createdAt, { style: "full", timeZone });
  assert.equal(
    serializeUsageCsv([call], timeZone),
    '\ufeff"时间","时区","workflow","operation","stage","功能","模型","输入 Token","输出 Token","合计 Token"\n' +
      '"' +
      timestamp +
      '","America/Los_Angeles","planning","op,""1""","provider","计划生成","provider/""model""","10","3","16"',
  );
});
