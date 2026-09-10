"use client";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { DiagnosticStorageV1 } from "@vibe-learner/shared";
import { queryDiagnosticStorage } from "../lib/diagnostic-storage";

const button: CSSProperties = { padding: "8px 12px", minHeight: 44, border: "1px solid var(--border)", borderRadius: 8, background: "var(--bg)" };
const mib = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(2)} MiB`;
export function DiagnosticStorageObservation({ value }: { value: DiagnosticStorageV1 }) {
  return <div style={{ overflowWrap: "anywhere" }}>
    <p>观察时间 {value.observed_at}。文件大小分别读取，计数仅覆盖当前进程；未包括文件系统分配/元数据、外部写入和 VACUUM 临时文件，尚不证明整个安装目录满足磁盘上限。</p>
    <article style={{ padding: 12, border: "1px solid var(--border)", borderRadius: 12, marginBottom: 8 }}>
      <h4>诊断目录合计</h4>
      <p>{value.directory.budget_state === "over_observed_limit" ? "已观察用量超过参考预算" : value.directory.budget_state === "within_observed_limit" ? "本次目录扫描用量在参考预算内" : "目录总量尚不能完整确认"}：{mib(value.directory.total_bytes)} / {mib(value.directory.max_bytes)}。</p>
      <p>数据库及附属文件 {mib(value.directory.database_bytes)}；桌面暂存目录 {mib(value.directory.spool_bytes)}；其他文件 {mib(value.directory.other_bytes)}。扫描 {value.directory.scanned_entries} 项，跳过 {value.directory.skipped_entries} 项。</p>
      <p>这是独立目录扫描，不能与下方分别采样的大小直接对账，也不代表已执行整个目录的配额控制。目录内未知文件计入大小；不跟随链接、不读取内容、不删除文件。</p>
      {value.directory.gaps.length > 0 && <p>扫描缺口：{value.directory.gaps.map(gap => ({ not_configured: "未配置", filesystem_unavailable: "文件读取不可用", configured_database_outside_directory: "数据库位于其他目录", scan_limit: "达到项目上限", depth_limit: "达到目录深度上限", time_limit: "达到扫描时限", unsupported_entry: "存在链接或特殊文件" })[gap]).join("、")}。最多 {value.directory.scan_limit} 项、{value.directory.max_depth} 层，协作式时限 {value.directory.scan_budget_ms} 毫秒。</p>}
    </article>
    {value.databases.map(row => <article key={row.name} style={{ padding: 12, border: "1px solid var(--border)", borderRadius: 12, marginBottom: 8 }}>
      <h4>{row.name === "events" ? "事件数据库" : "Harness 索引数据库"}</h4>
      <p>{row.status === "over_observed_limit" ? "观察到文件超出预算" : row.status === "within_observed_limit" ? "已观察文件大小在预算内" : "空间状态不可用"}；预算 {row.max_bytes === null ? "未知" : mib(row.max_bytes)}。</p>
      {row.gap && <p>{row.gap === "not_configured" ? "索引未配置。" : row.gap === "database_absent" ? "尚无可观察的数据库文件。" : "文件大小读取失败。"}</p>}
      {row.files && <p>文件合计 {mib(row.files.total_bytes)}；主文件 {mib(row.files.database)}；WAL {mib(row.files.wal)}；SHM {mib(row.files.shm)}；journal {mib(row.files.journal)}；锁文件 {row.files.lock} 字节。</p>}
      {row.recovery && <p>旧库恢复尝试 {row.recovery.attempts}；完成 {row.recovery.completed}；暂缓 {row.recovery.deferred}；失败 {row.recovery.failures}。恢复期间可能临时超过常规预算，额外工作空间上限 {mib(row.recovery.workspace_bytes)}；空间不足或读者占用时暂缓。</p>}
      {row.counters && <p>配额预留拒绝 {row.counters.quota_refusals}；锁不可用 {row.counters.quota_unavailable}；维护忙 {row.counters.maintenance_busy}；维护失败 {row.counters.maintenance_failures}；完成维护 {row.counters.maintenance_completed}；旧库转换 {row.counters.legacy_migrations}。</p>}
    </article>)}
    <article style={{ padding: 12, border: "1px solid var(--border)", borderRadius: 12 }}>
      <h4>桌面暂存队列</h4>
      <p>{value.desktop_spool.status === "observed" ? "已读取目录文件大小" : value.desktop_spool.status === "absent" ? "暂存目录尚不存在" : "目录观察不完整或不可用"}；已观察合计 {mib(value.desktop_spool.total_bytes)}。</p>
      <p>事件 {value.desktop_spool.event_files} 个 / {mib(value.desktop_spool.event_bytes)}；事件预算 {value.desktop_spool.max_event_files} 个 / {mib(value.desktop_spool.max_event_bytes)}。元数据 {value.desktop_spool.metadata_bytes} 字节；其他文件 {value.desktop_spool.other_files} 个 / {mib(value.desktop_spool.other_bytes)}；跳过 {value.desktop_spool.skipped_entries} 项。</p>
      {value.desktop_spool.gap && <p>观察缺口：{({ not_configured: "未配置", filesystem_unavailable: "文件读取不可用", scan_limit: "达到扫描上限", unsupported_entry: "存在未统计的目录或链接" })[value.desktop_spool.gap]}。最多扫描 {value.desktop_spool.scan_limit} 项；部分大小不能证明完整用量。</p>}
    </article>
    <p>预算内也可能因提交空间预留不足而拒绝写入；历史拒绝计数不表示当前仍被阻塞。读快照释放后可能恢复。诊断拒绝不等于业务提交失败。</p>
  </div>;
}
export function DiagnosticStoragePanel() {
  const [value, setValue] = useState<DiagnosticStorageV1 | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const active = useRef<AbortController | null>(null);
  async function load() {
    active.current?.abort();
    const controller = new AbortController();
    active.current = controller;
    setValue(null); setLoading(true); setError(false);
    try {
      const result = await queryDiagnosticStorage(controller.signal);
      if (active.current === controller && !controller.signal.aborted) setValue(result);
    } catch { if (active.current === controller && !controller.signal.aborted) setError(true); }
    finally { if (active.current === controller) setLoading(false); }
  }
  useEffect(() => { void load(); return () => { active.current?.abort(); active.current = null; }; }, []);
  return <section aria-label="诊断存储状态">
    <h3>诊断存储状态</h3>
    <p>本安装的空间与维护观察，不使用事件筛选条件。</p>
    <button style={button} onClick={load} disabled={loading}>刷新存储状态</button>
    {loading && <p role="status">正在读取空间状态…</p>}
    {error && <p role="alert">存储状态读取失败或响应不合法，请重试。</p>}
    {value && <DiagnosticStorageObservation value={value} />}
  </section>;
}
