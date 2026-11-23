import assert from "node:assert/strict";
import test from "node:test";
import { serializeUsageCsv } from "../components/model-usage/model-usage-data.ts";

test("CSV marks formula-shaped text while leaving legitimate numbers intact", () => {
  const record = {
    id: "id",
    createdAt: "2024-01-02T00:30:00Z",
    workflow: "=ordinary text",
    operationId: "  +ordinary text",
    stage: "\tordinary text",
    feature: "plan",
    model: '＠ordinary,"text"',
    promptTokens: 2,
    completionTokens: 3,
    totalTokens: 7,
  };
  const csv = serializeUsageCsv([record], "UTC");
  assert.ok(
    csv.endsWith(
      `"'=ordinary text","'  +ordinary text","'\tordinary text","计划生成","'＠ordinary,""text""","2","3","7"`,
    ),
  );
});
