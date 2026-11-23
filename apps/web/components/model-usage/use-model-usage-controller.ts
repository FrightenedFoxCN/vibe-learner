import { useEffect, useMemo, useState } from "react";
import type { TokenUsageCallRecord, TokenUsageStats } from "@vibe-learner/shared";
import { usePageDebugSnapshot } from "../debug/page-debug-context";
import { getModelUsageStats } from "../../lib/data/model-usage";
import {
  buildDayMap,
  buildFeatureModelSummary,
  buildFeatureSummary,
  filterUsageRecords,
  RECORD_PAGE_SIZE,
  serializeUsageCsv,
  sortedUsageOptions,
  sortUsageBuckets,
  sumUsageRecords,
} from "./model-usage-data";

function downloadUsageCsv(records: TokenUsageCallRecord[], timeZone: string) {
  const blob = new Blob([serializeUsageCsv(records, timeZone)], {
    type: "text/csv;charset=utf-8",
  });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob);
  link.download = `model-usage-${new Date().toISOString().slice(0, 10)}.csv`;
  link.click();
  URL.revokeObjectURL(link.href);
}

export function useModelUsageController() {
  const [stats, setStats] = useState<TokenUsageStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [timeZone, setTimeZone] = useState(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
  );
  const [workflowFilter, setWorkflowFilter] = useState("");
  const [operationFilter, setOperationFilter] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [recordPage, setRecordPage] = useState(1);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError("");
      try {
        const data = await getModelUsageStats();
        if (!cancelled) setStats(data);
      } catch (err) {
        if (!cancelled) setError(String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, []);

  const days = useMemo(() => (stats ? buildDayMap(stats.buckets) : []), [stats]);
  const featureSummary = useMemo(
    () => (stats ? buildFeatureSummary(stats.buckets) : []),
    [stats],
  );
  const buckets = useMemo(
    () => (stats ? sortUsageBuckets(stats.buckets) : []),
    [stats],
  );
  const filteredRecords = useMemo(
    () =>
      filterUsageRecords(stats?.records ?? [], {
        workflow: workflowFilter,
        operation: operationFilter,
        dateFrom,
        dateTo,
      }),
    [dateFrom, dateTo, operationFilter, stats, workflowFilter],
  );
  const featureModelSummary = useMemo(
    () => buildFeatureModelSummary(filteredRecords),
    [filteredRecords],
  );
  const workflowOptions = useMemo(
    () => sortedUsageOptions((stats?.records ?? []).map((record) => record.workflow)),
    [stats],
  );
  // Operation options intentionally follow all active filters, including operation.
  const operationOptions = useMemo(
    () => sortedUsageOptions(filteredRecords.map((record) => record.operationId)),
    [filteredRecords],
  );
  const visibleRecords = filteredRecords.slice(
    (recordPage - 1) * RECORD_PAGE_SIZE,
    recordPage * RECORD_PAGE_SIZE,
  );
  const pageCount = Math.max(1, Math.ceil(filteredRecords.length / RECORD_PAGE_SIZE));
  const filteredTotals = useMemo(
    () => sumUsageRecords(filteredRecords),
    [filteredRecords],
  );
  const debugSnapshot = useMemo(
    () => ({
      title: "用量审计调试面板",
      subtitle: "查看用量统计和原始数据。",
      error,
      summary: [
        { label: "加载状态", value: loading ? "加载中" : "就绪" },
        { label: "调用次数", value: String(stats?.records.length ?? 0) },
        { label: "聚合桶数", value: String(stats?.buckets.length ?? 0) },
        { label: "总 Token", value: String(stats?.totalTokens ?? 0) },
        { label: "功能数", value: String(featureSummary.length) },
      ],
      details: [
        { title: "Token 统计快照", value: stats },
        { title: "按日聚合桶", value: days },
        { title: "功能模型汇总", value: featureModelSummary },
        { title: "逐次调用（前 50 条）", value: stats?.records.slice(0, 50) ?? [] },
      ],
    }),
    [days, error, featureModelSummary, featureSummary.length, loading, stats],
  );

  usePageDebugSnapshot(debugSnapshot);

  return {
    ready: stats !== null,
    loading,
    error,
    filters: {
      timeZone,
      timeZoneOptions: [
        ...new Set([
          timeZone,
          "UTC",
          "Asia/Shanghai",
          "America/Los_Angeles",
          "Europe/London",
        ]),
      ],
      workflowFilter,
      operationFilter,
      dateFrom,
      dateTo,
      workflowOptions,
      operationOptions,
      onTimeZoneChange: setTimeZone,
      onWorkflowChange(value: string) {
        setWorkflowFilter(value);
        setOperationFilter("");
        setRecordPage(1);
      },
      onOperationChange(value: string) {
        setOperationFilter(value);
        setRecordPage(1);
      },
      onDateFromChange(value: string) {
        setDateFrom(value);
        setRecordPage(1);
      },
      onDateToChange(value: string) {
        setDateTo(value);
        setRecordPage(1);
      },
      onExport: () => downloadUsageCsv(filteredRecords, timeZone),
    },
    summary: { count: filteredRecords.length, totals: filteredTotals },
    days,
    featureSummary,
    featureModelSummary,
    buckets,
    calls: {
      hasRecords: Boolean(stats?.records.length),
      visibleRecords,
      timeZone,
      recordPage,
      pageCount,
      onPrevious: () => setRecordPage((page) => Math.max(1, page - 1)),
      onNext: () => setRecordPage((page) => Math.min(pageCount, page + 1)),
    },
  };
}

export type ModelUsageController = ReturnType<typeof useModelUsageController>;
