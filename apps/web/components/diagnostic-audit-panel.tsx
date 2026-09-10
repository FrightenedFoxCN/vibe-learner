"use client";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { DiagnosticEventFilters, DiagnosticExportV1 } from "@vibe-learner/shared";
import { queryDiagnosticExport } from "../lib/diagnostic-export";
import { DiagnosticQueryError } from "../lib/diagnostic-query";
import { exportJson } from "../lib/export-json";

const button: CSSProperties = { padding: "8px 12px", minHeight: 44, border: "1px solid var(--border)", borderRadius: 8, background: "var(--bg)" };

export function DiagnosticAuditPanel({ filters }: { filters: DiagnosticEventFilters }) {
  const [result, setResult] = useState<DiagnosticExportV1 | null>(null);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  const active = useRef<AbortController | null>(null);
  useEffect(() => () => { active.current?.abort(); active.current = null; }, []);
  async function load() {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setLoading(true); setResult(null); setError(""); setMessage("");
    try {
      const snapshot = await queryDiagnosticExport(filters, controller.signal);
      if (active.current === controller && !controller.signal.aborted) setResult(snapshot);
    } catch (cause) {
      if (active.current === controller && !controller.signal.aborted) setError(cause instanceof DiagnosticQueryError && cause.code === "response_too_large" ? "诊断包超过上限，请缩小筛选范围。" : "诊断包读取失败或响应不合法，请重试。");
    } finally { if (active.current === controller) setLoading(false); }
  }
  async function save() {
    if (!result || saving) return;
    const owner = active.current;
    setSaving(true); setMessage(""); setError("");
    try {
      const saved = await exportJson("vibe-learner-diagnostics.json", result, { compact: true });
      if (active.current === owner) setMessage(saved ? "诊断包已交给浏览器下载或桌面保存。" : "已取消保存诊断包。");
    } catch { if (active.current === owner) setError("诊断包保存失败，请重试。"); }
    finally { if (active.current === owner) setSaving(false); }
  }
  return <section aria-label="诊断统计与导出" style={{ minWidth: 0, overflowWrap: "anywhere" }}>
    <h3>诊断统计与导出</h3>
    <p>使用已应用的筛选条件创建快照。统计按模型、配置和组件版本分组；父子耗时不相加，缺失值保持未知。</p>
    <button style={button} disabled={loading || saving} onClick={load}>{loading ? "正在生成诊断快照…" : "生成诊断快照"}</button>
    {loading && <button style={button} onClick={() => { active.current?.abort(); active.current = null; setLoading(false); setMessage("已取消读取诊断快照。"); }}>取消读取</button>}
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
    {result && <>
      <p role="status">快照时间 {result.created_at}；事件 {result.events.length}；关联 {result.operation_links.length}；Harness 索引 {result.index.length}；指标样本 {result.audit.observations.length}。</p>
      <button style={button} disabled={saving || loading} onClick={save}>{saving ? "正在保存诊断包…" : "下载诊断包"}</button>
      <p>事件、关联和采集覆盖来自同一快照；Harness 索引使用独立快照，可能滞后。时间、页面和级别条件筛选事件，关联阶段可能超出该时间范围。此包不证明完整采集或业务提交。</p>
      <p>已清理事件 {result.retention.removed_events}；索引{result.index_coverage.freshness === "unavailable" ? "不可用" : "可用但可能滞后"}；缺少索引的关联 operation {result.index_coverage.missing_operation_count}。已观察丢弃下限 {result.writer_pages[0].totals.observed_dropped}，未落盘队列及启动前损失仍未知。</p>
      <p>关联记录已清理 {result.link_retention.removed_rows} 次；索引清理 {result.index_retention?.removed_rows ?? "未知"} 次。清理次数不是不同记录的数量；过期源记录可能在索引前被排除。{result.link_retention.legacy_timestamp_rows > 0 || (result.index_retention?.legacy_timestamp_rows ?? 0) > 0 ? "部分历史记录的首次保留时间未知。" : ""}留存统计只描述记录正文；总体磁盘上限尚未认证。</p>
      {!result.audit.groups.length && <p>当前范围没有可统计的指标样本；不代表流程没有执行。</p>}
      <p>以下展示前 100 组；完整分组和原始指标保存在诊断包中。P50/P95 使用各组已测量样本，包含失败耗时。</p>
      {result.audit.groups.slice(0, 100).map((group, i) => <details key={i} style={{ padding: 8, borderBottom: "1px solid var(--border)" }}>
        <summary>{group.key.workflow ?? "流程未知"} / {group.key.stage ?? "阶段未知"} · {group.key.kind} · {group.key.model ?? "模型未知或不适用"} · {group.sample_count} 样本</summary>
        <p>完成 {group.completed_count}；失败 {group.failed_count}；取消 {group.cancelled_count}；跳过 {group.skipped_count}；未知 {group.unknown_count}；恢复 {group.recovered_count}。</p>
        <p>耗时样本 {group.duration_sample_count}；P50 {group.p50_ms === null ? "未知" : `${group.p50_ms.toFixed(1)} ms`}；P95 {group.p95_ms === null ? "未知" : `${group.p95_ms.toFixed(1)} ms`}。</p>
        <p>已报告总 token {group.total_tokens ?? "未知"}（{group.total_token_sample_count} 个用量样本）。用量仅在 provider attempt 组累加。</p>
        <pre style={{ whiteSpace: "pre-wrap", overflowWrap: "anywhere", maxHeight: 300, overflow: "auto" }}>{JSON.stringify({ configuration: group.key, gaps: group.gaps }, null, 2)}</pre>
      </details>)}
    </>}
  </section>;
}
