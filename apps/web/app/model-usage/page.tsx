"use client";

import { useEffect, useMemo, useState, type CSSProperties } from "react";
import type { TokenUsageDailyBucket, TokenUsageStats } from "@vibe-learner/shared";
import { TopNav } from "../../components/top-nav";
import { getModelUsageStats } from "../../lib/api";

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

export default function ModelUsagePage() {
  const [stats, setStats] = useState<TokenUsageStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

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

  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/model-usage" />

      <div style={styles.content}>
        <div style={styles.heading}>
          <h1 style={styles.pageTitle}>用量审计</h1>
          <p style={styles.pageDesc}>各功能模型调用的 token 消耗汇总，按日期和功能分组。</p>
        </div>

        {loading && <div style={styles.statusText}>加载中…</div>}
        {error && <div style={styles.errorBanner}>{error}</div>}

        {stats && (
          <>
            {/* Total summary row */}
            <div style={styles.summaryRow}>
              <div style={styles.summaryCard}>
                <span style={styles.summaryLabel}>总 Token</span>
                <span style={styles.summaryValue}>{formatNumber(stats.totalTokens)}</span>
              </div>
              <div style={styles.summaryCard}>
                <span style={styles.summaryLabel}>输入 Token</span>
                <span style={styles.summaryValue}>{formatNumber(stats.totalPromptTokens)}</span>
              </div>
              <div style={styles.summaryCard}>
                <span style={styles.summaryLabel}>输出 Token</span>
                <span style={styles.summaryValue}>{formatNumber(stats.totalCompletionTokens)}</span>
              </div>
              <div style={styles.summaryCard}>
                <span style={styles.summaryLabel}>记录条数</span>
                <span style={styles.summaryValue}>{stats.buckets.length}</span>
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
                            <td style={{ ...styles.td, fontFamily: "monospace", fontSize: 11 }}>{b.model}</td>
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
    fontSize: 22,
    fontWeight: 700,
    margin: 0,
    marginBottom: 6,
    color: "var(--ink)",
  },
  pageDesc: {
    fontSize: 13,
    color: "var(--muted)",
    margin: 0,
  },
  statusText: {
    fontSize: 13,
    color: "var(--muted)",
    padding: "12px 0",
  },
  errorBanner: {
    padding: "10px 14px",
    background: "#fef2f2",
    color: "#b91c1c",
    borderRadius: 6,
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
    borderRadius: 8,
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
    borderRadius: 8,
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
};
