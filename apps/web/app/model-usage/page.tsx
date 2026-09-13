"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import type { TokenUsageCallRecord, TokenUsageDailyBucket, TokenUsageStats } from "@vibe-learner/shared";
import { TopNav } from "../../components/top-nav";
import { usePageDebugSnapshot } from "../../components/page-debug-context";
import { getModelUsageStats } from "../../lib/data/model-usage";

const FEATURE_LABELS: Record<string, string> = {
  plan: "计划生成",
  chat: "章节对话",
  setting: "设置辅助",
  embedding: "向量嵌入",
};

const FEATURE_COLORS: Record<string, string> = {
  plan: "#6366f1",
  chat: "#22c55e",
  setting: "#f59e0b",
  embedding: "#06b6d4",
};

const DEFAULT_COLOR = "#94a3b8";
const WORKFLOW_LABELS: Record<string, string> = {
  planning: "Planning",
  study_chat: "Study Chat",
  persona: "Persona",
  scene: "Scene",
  document_parse: "Document 解析",
  tavern: "Tavern",
};

function featureLabel(f: string): string {
  return FEATURE_LABELS[f] ?? f;
}

function featureColor(f: string): string {
  return FEATURE_COLORS[f] ?? DEFAULT_COLOR;
}

function formatNumber(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(1) + "K";
  return String(n);
}

function formatDateTime(value: string, timeZone?: string): string {
  if (!value) return "-";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
    ...(timeZone ? { timeZone } : {}),
  }).format(date);
}

function workflowLabel(value: string): string { return WORKFLOW_LABELS[value] ?? (value || "未关联 workflow"); }

function exportUsageCsv(records: TokenUsageCallRecord[], timeZone: string) {
  const escape = (value: string) => `"${value.replaceAll('"', '""')}"`;
  const rows = [
    ["时间", "时区", "workflow", "operation", "stage", "功能", "模型", "输入 Token", "输出 Token", "合计 Token"],
    ...records.map(record => [formatDateTime(record.createdAt, timeZone), timeZone, record.workflow, record.operationId, record.stage, featureLabel(record.feature), record.model, String(record.promptTokens), String(record.completionTokens), String(record.totalTokens)]),
  ];
  const blob = new Blob(["\ufeff" + rows.map(row => row.map(escape).join(",")).join("\n")], { type: "text/csv;charset=utf-8" });
  const link = document.createElement("a");
  link.href = URL.createObjectURL(blob); link.download = `model-usage-${new Date().toISOString().slice(0, 10)}.csv`; link.click();
  URL.revokeObjectURL(link.href);
}

interface DayData {
  date: string;
  segments: { feature: string; model: string; tokens: number }[];
  total: number;
}

function buildDayMap(buckets: TokenUsageDailyBucket[]): DayData[] {
  const map = new Map<string, DayData>();
  for (const b of buckets) {
    if (!map.has(b.date)) {
      map.set(b.date, { date: b.date, segments: [], total: 0 });
    }
    const day = map.get(b.date)!;
    const existing = day.segments.find((s) => s.feature === b.feature && s.model === b.model);
    if (existing) {
      existing.tokens += b.totalTokens;
    } else {
      day.segments.push({ feature: b.feature, model: b.model, tokens: b.totalTokens });
    }
    day.total += b.totalTokens;
  }
  return Array.from(map.values()).sort((a, b) => a.date.localeCompare(b.date));
}

function StackedBarChart({ days }: { days: DayData[] }) {
  if (days.length === 0) {
    return (
      <div style={styles.emptyChart}>暂无数据</div>
    );
  }

  const maxTotal = Math.max(...days.map((d) => d.total), 1);
  const chartHeight = 200;
  const barWidth = Math.max(20, Math.min(48, Math.floor(600 / days.length) - 4));
  const gutter = Math.max(4, Math.min(12, Math.floor(200 / days.length)));
  const chartWidth = days.length * (barWidth + gutter) + gutter;

  const uniqueFeatures = Array.from(new Set(days.flatMap((d) => d.segments.map((s) => s.feature)))).sort();

  return (
    <div style={styles.chartWrapper}>
      <div style={styles.legend}>
        {uniqueFeatures.map((f) => (
          <span key={f} style={styles.legendItem}>
            <span style={{ ...styles.legendDot, background: featureColor(f) }} />
            {featureLabel(f)}
          </span>
        ))}
      </div>
      <div style={{ overflowX: "auto" }}>
        <svg
          width={chartWidth}
          height={chartHeight + 40}
          aria-label="模型用量堆积柱状图"
        >
          {/* Y-axis gridlines */}
          {[0, 0.25, 0.5, 0.75, 1].map((ratio) => {
            const y = chartHeight - ratio * chartHeight;
            return (
              <line
                key={ratio}
                x1={0}
                y1={y}
                x2={chartWidth}
                y2={y}
                stroke="var(--border)"
                strokeWidth={1}
              />
            );
          })}

          {days.map((day, i) => {
            const x = gutter + i * (barWidth + gutter);
            let stackY = chartHeight;
            const totalBarHeight = (day.total / maxTotal) * chartHeight;

            const rects = day.segments
              .slice()
              .sort((a, b) => a.feature.localeCompare(b.feature))
              .map((seg) => {
                const segHeight = (seg.tokens / maxTotal) * chartHeight;
                stackY -= segHeight;
                return (
                  <rect
                    key={`${seg.feature}-${seg.model}`}
                    x={x}
                    y={stackY}
                    width={barWidth}
                    height={segHeight}
                    fill={featureColor(seg.feature)}
                    opacity={0.85}
                  >
                    <title>
                      {day.date} · {featureLabel(seg.feature)} ({seg.model}){"\n"}
                      {formatNumber(seg.tokens)} tokens
                    </title>
                  </rect>
                );
              });

            return (
              <g key={day.date}>
                {rects}
                {/* Total label above bar */}
                {totalBarHeight > 12 && (
                  <text
                    x={x + barWidth / 2}
                    y={chartHeight - totalBarHeight - 3}
                    textAnchor="middle"
                    fontSize={9}
                    fill="var(--muted)"
                  >
                    {formatNumber(day.total)}
                  </text>
                )}
                {/* Date label below */}
                <text
                  x={x + barWidth / 2}
                  y={chartHeight + 14}
                  textAnchor="middle"
                  fontSize={9}
                  fill="var(--muted)"
                  transform={`rotate(-30, ${x + barWidth / 2}, ${chartHeight + 14})`}
                >
                  {day.date.slice(5)}
                </text>
              </g>
            );
          })}
        </svg>
      </div>
    </div>
  );
}

interface FeatureSummary {
  feature: string;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
}

interface FeatureModelSummary {
  feature: string;
  model: string;
  promptTokens: number;
  completionTokens: number;
  totalTokens: number;
  callCount: number;
}

function buildFeatureSummary(buckets: TokenUsageDailyBucket[]): FeatureSummary[] {
  const map = new Map<string, FeatureSummary>();
  for (const b of buckets) {
    if (!map.has(b.feature)) {
      map.set(b.feature, { feature: b.feature, promptTokens: 0, completionTokens: 0, totalTokens: 0 });
    }
    const s = map.get(b.feature)!;
    s.promptTokens += b.promptTokens;
    s.completionTokens += b.completionTokens;
    s.totalTokens += b.totalTokens;
  }
  return Array.from(map.values()).sort((a, b) => b.totalTokens - a.totalTokens);
}

function buildFeatureModelSummary(records: TokenUsageCallRecord[]): FeatureModelSummary[] {
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

export default function ModelUsagePage() {
  const [stats, setStats] = useState<TokenUsageStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [timeZone, setTimeZone] = useState(() => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC");
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
    return () => { cancelled = true; };
  }, []);

  const days = useMemo(() => stats ? buildDayMap(stats.buckets) : [], [stats]);
  const featureSummary = useMemo(() => stats ? buildFeatureSummary(stats.buckets) : [], [stats]);
  const filteredRecords = useMemo(() => (stats?.records ?? []).filter(record =>
    (!workflowFilter || record.workflow === workflowFilter) &&
    (!operationFilter || record.operationId === operationFilter) &&
    (!dateFrom || record.createdAt.slice(0, 10) >= dateFrom) &&
    (!dateTo || record.createdAt.slice(0, 10) <= dateTo)
  ), [dateFrom, dateTo, operationFilter, stats, workflowFilter]);
  const featureModelSummary = useMemo(() => buildFeatureModelSummary(filteredRecords), [filteredRecords]);
  const workflowOptions = useMemo(() => Array.from(new Set((stats?.records ?? []).map(record => record.workflow).filter(Boolean))).sort(), [stats]);
  const operationOptions = useMemo(() => Array.from(new Set(filteredRecords.map(record => record.operationId).filter(Boolean))).sort(), [filteredRecords]);
  const recordPageSize = 50;
  const visibleRecords = filteredRecords.slice((recordPage - 1) * recordPageSize, recordPage * recordPageSize);
  const filteredTotals = useMemo(() => filteredRecords.reduce((totals, record) => ({
    prompt: totals.prompt + record.promptTokens,
    completion: totals.completion + record.completionTokens,
    total: totals.total + record.totalTokens,
  }), { prompt: 0, completion: 0, total: 0 }), [filteredRecords]);
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
        { label: "功能数", value: String(featureSummary.length) }
      ],
      details: [
        { title: "Token 统计快照", value: stats },
        { title: "按日聚合桶", value: days },
        { title: "功能模型汇总", value: featureModelSummary },
        { title: "逐次调用（前 50 条）", value: stats?.records.slice(0, 50) ?? [] }
      ]
    }),
    [days, error, featureModelSummary, featureSummary.length, loading, stats]
  );

  usePageDebugSnapshot(debugSnapshot);

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/model-usage" />

      <div style={styles.content}>
        <div style={styles.heading}>
          <h1 style={styles.pageTitle}>用量审计</h1>
        </div>

        {loading && <div style={styles.statusText}>加载中…</div>}
        {error && <div style={styles.errorBanner}>{error}</div>}

        {stats && (
          <>
            <section style={styles.filters} aria-label="用量筛选">
              <label style={styles.filterField}>显示时区<select value={timeZone} onChange={event => setTimeZone(event.target.value)} style={styles.filterControl}>
                {[timeZone, "UTC", "Asia/Shanghai", "America/Los_Angeles", "Europe/London"].filter((value, index, values) => value && values.indexOf(value) === index).map(value => <option key={value} value={value}>{value}</option>)}
              </select></label>
              <label style={styles.filterField}>Workflow<select value={workflowFilter} onChange={event => { setWorkflowFilter(event.target.value); setOperationFilter(""); setRecordPage(1); }} style={styles.filterControl}><option value="">全部 workflow</option>{workflowOptions.map(value => <option key={value} value={value}>{workflowLabel(value)}</option>)}</select></label>
              <label style={styles.filterField}>Operation<select value={operationFilter} onChange={event => { setOperationFilter(event.target.value); setRecordPage(1); }} style={styles.filterControl}><option value="">全部 operation</option>{operationOptions.map(value => <option key={value} value={value}>{value}</option>)}</select></label>
              <label style={styles.filterField}>起始日期<input type="date" value={dateFrom} onChange={event => { setDateFrom(event.target.value); setRecordPage(1); }} style={styles.filterControl} /></label>
              <label style={styles.filterField}>结束日期<input type="date" value={dateTo} onChange={event => { setDateTo(event.target.value); setRecordPage(1); }} style={styles.filterControl} /></label>
              <button type="button" style={styles.exportButton} onClick={() => exportUsageCsv(filteredRecords, timeZone)}>导出当前筛选 CSV</button>
            </section>
            <p style={styles.scopeNote}>当前显示时区：{timeZone}。统计按已记录的 provider Token 汇总；价格未配置时不虚构金额，实际费用以服务商账单为准。筛选结果 {filteredRecords.length} 条。</p>
            {/* Total summary row */}
            <div style={styles.summaryRow}>
              <div style={styles.summaryCard}>
                <span style={styles.summaryLabel}>总 Token</span>
                <span style={styles.summaryValue}>{formatNumber(filteredTotals.total)}</span>
              </div>
              <div style={styles.summaryCard}>
                <span style={styles.summaryLabel}>输入 Token</span>
                <span style={styles.summaryValue}>{formatNumber(filteredTotals.prompt)}</span>
              </div>
              <div style={styles.summaryCard}>
                <span style={styles.summaryLabel}>输出 Token</span>
                <span style={styles.summaryValue}>{formatNumber(filteredTotals.completion)}</span>
              </div>
              <div style={styles.summaryCard}>
                <span style={styles.summaryLabel}>调用次数</span>
                <span style={styles.summaryValue}>{filteredRecords.length}</span>
              </div>
            </div>

            {/* Stacked bar chart */}
            <div style={styles.section}>
              <h2 style={styles.sectionTitle}>按日期的 Token 用量（堆积柱状图）</h2>
              <StackedBarChart days={days} />
            </div>

            {/* Per-feature breakdown table */}
            <div style={styles.section}>
              <h2 style={styles.sectionTitle}>按功能汇总</h2>
              {featureSummary.length === 0 ? (
                <p style={styles.statusText}>暂无数据</p>
              ) : (
                <table style={styles.table}>
                  <thead>
                    <tr>
                      <th style={styles.th}>功能</th>
                      <th style={{ ...styles.th, textAlign: "right" }}>输入 Token</th>
                      <th style={{ ...styles.th, textAlign: "right" }}>输出 Token</th>
                      <th style={{ ...styles.th, textAlign: "right" }}>合计</th>
                    </tr>
                  </thead>
                  <tbody>
                    {featureSummary.map((row) => (
                      <tr key={row.feature}>
                        <td style={styles.td}>
                          <span style={{ ...styles.featureDot, background: featureColor(row.feature) }} />
                          {featureLabel(row.feature)}
                        </td>
                        <td style={{ ...styles.td, textAlign: "right" }}>{formatNumber(row.promptTokens)}</td>
                        <td style={{ ...styles.td, textAlign: "right" }}>{formatNumber(row.completionTokens)}</td>
                        <td style={{ ...styles.td, textAlign: "right", fontWeight: 600 }}>{formatNumber(row.totalTokens)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>

            <div style={styles.section}>
              <h2 style={styles.sectionTitle}>按功能 × 模型汇总</h2>
              {featureModelSummary.length === 0 ? (
                <p style={styles.statusText}>暂无数据</p>
              ) : (
                <div style={styles.tableScroll}>
                  <table style={styles.table}>
                    <thead>
                      <tr>
                        <th style={styles.th}>功能</th>
                        <th style={styles.th}>模型</th>
                        <th style={{ ...styles.th, textAlign: "right" }}>调用次数</th>
                        <th style={{ ...styles.th, textAlign: "right" }}>输入 Token</th>
                        <th style={{ ...styles.th, textAlign: "right" }}>输出 Token</th>
                        <th style={{ ...styles.th, textAlign: "right" }}>合计</th>
                      </tr>
                    </thead>
                    <tbody>
                      {featureModelSummary.map((row) => (
                        <tr key={`${row.feature}-${row.model}`}>
                          <td style={styles.td}>
                            <span style={{ ...styles.featureDot, background: featureColor(row.feature) }} />
                            {featureLabel(row.feature)}
                          </td>
                          <td style={{ ...styles.td, ...styles.monospaceCell }}>{row.model}</td>
                          <td style={{ ...styles.td, textAlign: "right" }}>{formatNumber(row.callCount)}</td>
                          <td style={{ ...styles.td, textAlign: "right" }}>{formatNumber(row.promptTokens)}</td>
                          <td style={{ ...styles.td, textAlign: "right" }}>{formatNumber(row.completionTokens)}</td>
                          <td style={{ ...styles.td, textAlign: "right", fontWeight: 600 }}>{formatNumber(row.totalTokens)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>

            {/* Raw buckets table */}
            {stats.buckets.length > 0 && (
              <div style={styles.section}>
                <h2 style={styles.sectionTitle}>明细记录（按日期 × 功能 × 模型）</h2>
                <div style={styles.tableScroll}>
                  <table style={styles.table}>
                    <thead>
                      <tr>
                        <th style={styles.th}>日期</th>
                        <th style={styles.th}>功能</th>
                        <th style={styles.th}>模型</th>
                        <th style={{ ...styles.th, textAlign: "right" }}>输入</th>
                        <th style={{ ...styles.th, textAlign: "right" }}>输出</th>
                        <th style={{ ...styles.th, textAlign: "right" }}>合计</th>
                      </tr>
                    </thead>
                    <tbody>
                      {[...stats.buckets]
                        .sort((a, b) => b.date.localeCompare(a.date) || a.feature.localeCompare(b.feature))
                        .map((b, i) => (
                          <tr key={`${b.date}-${b.feature}-${b.model}-${i}`}>
                            <td style={styles.td}>{b.date}</td>
                            <td style={styles.td}>
                              <span style={{ ...styles.featureDot, background: featureColor(b.feature) }} />
                              {featureLabel(b.feature)}
                            </td>
                            <td style={{ ...styles.td, ...styles.monospaceCell }}>{b.model}</td>
                            <td style={{ ...styles.td, textAlign: "right" }}>{formatNumber(b.promptTokens)}</td>
                            <td style={{ ...styles.td, textAlign: "right" }}>{formatNumber(b.completionTokens)}</td>
                            <td style={{ ...styles.td, textAlign: "right", fontWeight: 600 }}>{formatNumber(b.totalTokens)}</td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {stats.records.length > 0 && (
              <div style={styles.section}>
                <h2 style={styles.sectionTitle}>逐次调用明细</h2>
                <div style={styles.tableScroll}>
                  <table style={styles.table}>
                    <thead>
                      <tr>
                        <th style={styles.th}>时间</th>
                        <th style={styles.th}>功能</th>
                        <th style={styles.th}>模型</th>
                        <th style={{ ...styles.th, textAlign: "right" }}>输入</th>
                        <th style={{ ...styles.th, textAlign: "right" }}>输出</th>
                        <th style={{ ...styles.th, textAlign: "right" }}>合计</th>
                      </tr>
                    </thead>
                    <tbody>
                      {visibleRecords.map((record) => (
                        <tr key={record.id}>
                          <td style={styles.td}>{formatDateTime(record.createdAt, timeZone)}</td>
                          <td style={styles.td}>
                            <span style={{ ...styles.featureDot, background: featureColor(record.feature) }} />
                            {featureLabel(record.feature)}<br /><small>{workflowLabel(record.workflow)} · {record.operationId || "无 operation"}</small>
                          </td>
                          <td style={{ ...styles.td, ...styles.monospaceCell }}>{record.model}</td>
                          <td style={{ ...styles.td, textAlign: "right" }}>{formatNumber(record.promptTokens)}</td>
                          <td style={{ ...styles.td, textAlign: "right" }}>{formatNumber(record.completionTokens)}</td>
                          <td style={{ ...styles.td, textAlign: "right", fontWeight: 600 }}>{formatNumber(record.totalTokens)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <div style={styles.pagination} aria-label="用量分页"><span>第 {recordPage} / {Math.max(1, Math.ceil(filteredRecords.length / recordPageSize))} 页</span><button type="button" style={styles.pageButton} disabled={recordPage <= 1} onClick={() => setRecordPage(page => page - 1)}>上一页</button><button type="button" style={styles.pageButton} disabled={recordPage * recordPageSize >= filteredRecords.length} onClick={() => setRecordPage(page => page + 1)}>下一页</button></div>
              </div>
            )}
          </>
        )}

      </div>
    </main>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    background: "var(--bg)",
    color: "var(--ink)",
  },
  content: {
    maxWidth: 900,
    margin: "0 auto",
    padding: "32px 24px 64px",
  },
  heading: {
    marginBottom: 24,
  },
  pageTitle: {
    fontSize: 28,
    fontWeight: 800,
    letterSpacing: "-0.02em",
    lineHeight: 1.2,
    margin: 0,
    marginBottom: 6,
    color: "var(--ink)",
  },
  pageDesc: {
    fontSize: 13,
    color: "var(--muted)",
    margin: 0,
  },
  filters: { display: "flex", flexWrap: "wrap", gap: 10, alignItems: "end", padding: 12, border: "1px solid var(--border)", background: "var(--panel)", marginBottom: 8 },
  filterField: { display: "grid", gap: 4, minWidth: 150, color: "var(--muted)", fontSize: 11 },
  filterControl: { minHeight: 40, border: "1px solid var(--border)", padding: "7px 9px", background: "var(--bg)", color: "var(--ink)" },
  exportButton: { minHeight: 40, border: "1px solid var(--accent)", padding: "7px 12px", background: "var(--accent)", color: "white", cursor: "pointer", fontWeight: 600 },
  scopeNote: { margin: "0 0 20px", color: "var(--muted)", fontSize: 12 },
  statusText: {
    fontSize: 13,
    color: "var(--muted)",
    padding: "12px 0",
  },
  errorBanner: {
    padding: "10px 12px",
    background: "color-mix(in srgb, var(--negative) 8%, white)",
    border: "1px solid color-mix(in srgb, var(--negative) 35%, var(--border))",
    color: "var(--negative)",
    fontSize: 13,
    marginBottom: 16,
  },
  summaryRow: {
    display: "flex",
    gap: 12,
    flexWrap: "wrap",
    marginBottom: 28,
  },
  summaryCard: {
    flex: "1 1 160px",
    border: "1px solid var(--border)",
    padding: "14px 18px",
    display: "flex",
    flexDirection: "column",
    gap: 4,
  },
  summaryLabel: {
    fontSize: 11,
    color: "var(--muted)",
    textTransform: "uppercase",
    letterSpacing: "0.05em",
  },
  summaryValue: {
    fontSize: 24,
    fontWeight: 700,
    color: "var(--ink)",
    fontVariantNumeric: "tabular-nums",
  },
  section: {
    marginBottom: 36,
  },
  sectionTitle: {
    fontSize: 14,
    fontWeight: 600,
    color: "var(--ink)",
    marginBottom: 14,
    margin: 0,
    marginBlockEnd: 14,
  },
  chartWrapper: {
    border: "1px solid var(--border)",
    padding: "16px 16px 8px",
  },
  legend: {
    display: "flex",
    gap: 16,
    flexWrap: "wrap",
    marginBottom: 12,
  },
  legendItem: {
    display: "flex",
    alignItems: "center",
    gap: 6,
    fontSize: 12,
    color: "var(--muted)",
  },
  legendDot: {
    width: 10,
    height: 10,
    borderRadius: 2,
    flexShrink: 0,
  },
  emptyChart: {
    textAlign: "center",
    padding: "40px 0",
    fontSize: 13,
    color: "var(--muted)",
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 13,
  },
  th: {
    padding: "8px 12px",
    textAlign: "left",
    fontWeight: 600,
    fontSize: 11,
    color: "var(--muted)",
    borderBottom: "1px solid var(--border)",
    whiteSpace: "nowrap",
  },
  td: {
    padding: "8px 12px",
    borderBottom: "1px solid var(--border)",
    color: "var(--ink)",
    verticalAlign: "middle",
  },
  featureDot: {
    display: "inline-block",
    width: 8,
    height: 8,
    borderRadius: 2,
    marginRight: 6,
    verticalAlign: "middle",
    flexShrink: 0,
  },
  tableScroll: {
    overflowX: "auto",
  },
  pagination: { display: "flex", gap: 8, alignItems: "center", justifyContent: "flex-end", marginTop: 10, color: "var(--muted)", fontSize: 12 },
  pageButton: { minHeight: 36, border: "1px solid var(--border)", padding: "6px 10px", background: "var(--bg)", color: "var(--ink-2)", cursor: "pointer" },
  monospaceCell: {
    fontFamily: "monospace",
    fontSize: 11,
  },
};
