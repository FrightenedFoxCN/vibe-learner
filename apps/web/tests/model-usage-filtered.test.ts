import assert from "node:assert/strict";
import test from "node:test";
import {
  buildDayMap,
  buildFeatureSummary,
  buildUsageBuckets,
  filterUsageRecords,
  sumUsageRecords,
} from "../components/model-usage/model-usage-data.ts";

const call = {
  id: "one",
  createdAt: "2024-01-02T00:30:00Z",
  feature: "plan",
  model: "synthetic",
  workflow: "planning",
  operationId: "op-one",
  stage: "provider",
  promptTokens: 10,
  completionTokens: 3,
  totalTokens: 16,
};

test("daily chart and feature buckets contain exactly the filtered call totals", () => {
  const records = [
    call,
    { ...call, id: "two", workflow: "study_chat", totalTokens: 20 },
    { ...call, id: "three", createdAt: "2024-01-01T23:59:00Z", totalTokens: 30 },
    { ...call, id: "four", operationId: "op-four", totalTokens: 40 },
  ];
  const filtered = filterUsageRecords(records, {
    workflow: "planning",
    operation: "op-one",
    dateFrom: "2024-01-02",
    dateTo: "2024-01-02",
  });
  const buckets = buildUsageBuckets(filtered);
  assert.deepEqual(
    buildDayMap(buckets).map(({ date, total }) => [date, total]),
    [["2024-01-02", 16]],
  );
  assert.equal(
    buildFeatureSummary(buckets)[0].totalTokens,
    sumUsageRecords(filtered).total,
  );
  assert.deepEqual(buildUsageBuckets([]), []);
});
