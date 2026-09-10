"use client";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import type { DiagnosticStorageV1 } from "@vibe-learner/shared";
import { queryDiagnosticStorage } from "../lib/diagnostic-storage";

const button: CSSProperties = { padding: "8px 12px", minHeight: 44, border: "1px solid var(--border)", borderRadius: 8, background: "var(--bg)" };
const mib = (bytes: number) => `${(bytes / 1024 / 1024).toFixed(2)} MiB`;
export function DiagnosticStorageObservation({ value }: { value: DiagnosticStorageV1 }) {
  return <div style={{ overflowWrap: "anywhere" }}>
    <p>观察时间 {value.observed_at}。文件大小分别读取，计数仅覆盖当前进程；未包括桌面 spool、文件系统分配/元数据、外部写入和 VACUUM 临时文件，尚不证明整个安装目录满足磁盘上限。</p>
    {value.databases.map(row => <article key={row.name} style={{ padding: 12, border: "1px solid var(--border)", borderRadius: 12, marginBottom: 8 }}>
      <h4>{row.name === "events" ? "事件数据库" : "Harness 索引数据库"}</h4>
      <p>{row.status === "over_observed_limit" ? "观察到文件超出预算" : row.status === "within_observed_limit" ? "已观察文件大小在预算内" : "空间状态不可用"}；预算 {row.max_bytes === null ? "未知" : mib(row.max_bytes)}。</p>
      {row.gap && <p>{row.gap === "not_configured" ? "索引未配置。" : row.gap === "database_absent" ? "尚无可观察的数据库文件。" : "文件大小读取失败。"}</p>}
      {row.files && <p>文件合计 {mib(row.files.total_bytes)}；主文件 {mib(row.files.database)}；WAL {mib(row.files.wal)}；SHM {mib(row.files.shm)}；journal {mib(row.files.journal)}；锁文件 {row.files.lock} 字节。</p>}
      {row.counters && <p>配额预留拒绝 {row.counters.quota_refusals}；锁不可用 {row.counters.quota_unavailable}；维护忙 {row.counters.maintenance_busy}；维护失败 {row.counters.maintenance_failures}；完成维护 {row.counters.maintenance_completed}；旧库转换 {row.counters.legacy_migrations}。</p>}
    </article>)}
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
