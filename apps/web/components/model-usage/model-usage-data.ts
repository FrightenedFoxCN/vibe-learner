import type { TokenUsageCallRecord, TokenUsageDailyBucket } from "@vibe-learner/shared";
import { formatTimestamp } from "../../lib/format.ts";

const FEATURE_LABELS: Record<string, string> = {
  plan: "计划生成",
  chat: "章节对话",
  setting: "设置辅助",
  embedding: "向量嵌入",
};

const WORKFLOW_LABELS: Record<string, string> = {
  planning: "Planning",
  study_chat: "Study Chat",
  persona: "Persona",
  scene: "Scene",
  document_parse: "Document 解析",
  tavern: "Tavern",
};

export function featureLabel(f: string): string {
  return FEATURE_LABELS[f] ?? f;
}

export function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

export function workflowLabel(value: string): string {
  return WORKFLOW_LABELS[value] ?? (value || "未关联 workflow");
}

// Prefix risky text cells before CSV quoting; numeric token columns are untouched.
function spreadsheetText(value: string): string {
  return /^[\t\r\n]|^[\s\u200B]*[=+\-@＝＋－＠]/u.test(value) ? "'" + value : value;
}

export function serializeUsageCsv(records: TokenUsageCallRecord[], timeZone: string) {
  const escape = (value: string) => `"${value.replaceAll('"', '""')}"`;
  const rows = [
    [
      "时间",
      "时区",
      "workflow",
      "operation",
      "stage",
      "功能",
      "模型",
      "输入 Token",
      "输出 Token",
      "合计 Token",
    ],
    ...records.map((record) => [
      spreadsheetText(formatTimestamp(record.createdAt, { style: "full", timeZone })),
      spreadsheetText(timeZone),
      spreadsheetText(record.workflow),
      spreadsheetText(record.operationId),
      spreadsheetText(record.stage),
      spreadsheetText(featureLabel(record.feature)),
      spreadsheetText(record.model),
      String(record.promptTokens),
      String(record.completionTokens),
      String(record.totalTokens),
    ]),
  ];
  return "\ufeff" + rows.map((row) => row.map(escape).join(",")).join("\n");
}

export interface DayData {
  date: string;
  segments: { feature: string; model: string; tokens: number }[];
  total: number;
}

export function buildDayMap(buckets: TokenUsageDailyBucket[]): DayData[] {
  const map = new Map<string, DayData>();
  for (const b of buckets) {
    if (!map.has(b.date)) {
      map.set(b.date, { date: b.date, segments: [], total: 0 });
    }
    const day = map.get(b.date)!;
    const existing = day.segments.find(
      (s) => s.feature === b.feature && s.model === b.model,
    );
    if (existing) {
      existing.tokens += b.totalTokens;
    } else {
      day.segments.push({ feature: b.feature, model: b.model, tokens: b.totalTokens });
    }
    day.total += b.totalTokens;
  }
  return Array.from(map.values()).sort((a, b) => a.date.localeCompare(b.date));
}

export interface FeatureSummary {
  feature: string;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

export interface FeatureModelSummary {
  feature: string;
  model: string;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  callCount: number;
}

export function buildFeatureSummary(
  buckets: TokenUsageDailyBucket[],
): FeatureSummary[] {
  const map = new Map<string, FeatureSummary>();
  for (const b of buckets) {
    if (!map.has(b.feature)) {
      map.set(b.feature, {
        feature: b.feature,
        promptTokens: 0,
        completionTokens: 0,
        totalTokens: 0,
      });
    }
    const s = map.get(b.feature)!;
    s.promptTokens += b.promptTokens;
    s.completionTokens += b.completionTokens;
    s.totalTokens += b.totalTokens;
  }
  return Array.from(map.values()).sort((a, b) => b.totalTokens - a.totalTokens);
}

export function buildFeatureModelSummary(
  records: TokenUsageCallRecord[],
): FeatureModelSummary[] {
  const map = new Map<string, FeatureModelSummary>();
  for (const record of records) {
    const key = `${record.feature}::${record.model}`;
    if (!map.has(key)) {
      map.set(key, {
        feature: record.feature,
        model: record.model,
        promptTokens: 0,
        completionTokens: 0,
        totalTokens: 0,
        callCount: 0,
      });
    }
    const item = map.get(key)!;
    item.promptTokens += record.promptTokens;
    item.completionTokens += record.completionTokens;
    item.totalTokens += record.totalTokens;
    item.callCount += 1;
  }
  return Array.from(map.values()).sort((a, b) => b.totalTokens - a.totalTokens);
}

export interface UsageFilters {
  workflow: string;
  operation: string;
  dateFrom: string;
  dateTo: string;
}

export const RECORD_PAGE_SIZE = 50;

export function filterUsageRecords(
  records: TokenUsageCallRecord[],
  filters: UsageFilters,
) {
  const { workflow, operation, dateFrom, dateTo } = filters;
  // Bounds compare the recorded date, independent of the display timezone.
  return records.filter(
    (record) =>
      (!workflow || record.workflow === workflow) &&
      (!operation || record.operationId === operation) &&
      (!dateFrom || record.createdAt.slice(0, 10) >= dateFrom) &&
      (!dateTo || record.createdAt.slice(0, 10) <= dateTo),
  );
}

export function sortedUsageOptions(values: string[]) {
  return Array.from(new Set(values.filter(Boolean))).sort();
}

export function sumUsageRecords(records: TokenUsageCallRecord[]) {
  return records.reduce(
    (totals, record) => ({
      prompt: totals.prompt + record.promptTokens,
      completion: totals.completion + record.completionTokens,
      total: totals.total + record.totalTokens,
    }),
    { prompt: 0, completion: 0, total: 0 },
  );
}

export function buildUsageBuckets(
  records: TokenUsageCallRecord[],
): TokenUsageDailyBucket[] {
  const buckets = new Map<string, TokenUsageDailyBucket>();
  for (const {
    createdAt,
    feature,
    model,
    promptTokens,
    completionTokens,
    totalTokens,
  } of records) {
    const date = createdAt.slice(0, 10);
    const key = JSON.stringify([date, feature, model]);
    const bucket = buckets.get(key);
    buckets.set(key, {
      date,
      feature,
      model,
      promptTokens: (bucket?.promptTokens ?? 0) + promptTokens,
      completionTokens: (bucket?.completionTokens ?? 0) + completionTokens,
      totalTokens: (bucket?.totalTokens ?? 0) + totalTokens,
    });
  }
  return [...buckets.values()];
}

export function sortUsageBuckets(buckets: TokenUsageDailyBucket[]) {
  return [...buckets].sort(
    (a, b) => b.date.localeCompare(a.date) || a.feature.localeCompare(b.feature),
  );
}
