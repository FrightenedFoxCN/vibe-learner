"use client";
import { useCallback, useState, useSyncExternalStore, type CSSProperties, type FormEvent } from "react";
import type { DiagnosticIndexFilters, DiagnosticEventFilters, DiagnosticEventPageV1, DiagnosticHarnessIndexV1, DiagnosticOperationLinkV1, DiagnosticWriterEpochV1 } from "@vibe-learner/shared";
import { queryDiagnosticEvents, queryDiagnosticIndex, queryDiagnosticLinks, queryDiagnosticWriters } from "../lib/diagnostic-query";
import { currentDiagnosticPage, subscribeDiagnosticPage } from "../lib/diagnostics";
import { useDiagnosticPages } from "../hooks/use-diagnostic-pages";
import { DiagnosticStoragePanel } from "./diagnostic-storage-panel";
import { DiagnosticAuditPanel } from "./diagnostic-audit-panel";
import schemas from "../../../packages/shared/fixtures/diagnostics/query-schemas-v1.json";


const eventId = (row: DiagnosticEventPageV1["items"][number]) => row.event.event_id;
const traceId = (row: DiagnosticHarnessIndexV1) => row.trace_id;
const requestId = (row: DiagnosticOperationLinkV1) => row.request_id;
const emptyPage = () => null;
const paths = ["/", "/plan", "/study", "/persona-spectrum", "/scene-setup", "/tavern", "/settings", "/sensory-tools", "/model-usage"];
const pre: CSSProperties = { whiteSpace: "pre-wrap", overflowWrap: "anywhere", fontSize: 12, maxHeight: 320, overflow: "auto" };
const card: CSSProperties = { padding: 12, border: "1px solid var(--border)", borderRadius: 12, minWidth: 0 };
const button: CSSProperties = { padding: "8px 12px", minHeight: 44, border: "1px solid var(--border)", borderRadius: 8, background: "var(--bg)" };

function Status({ loading, error, count }: { loading: boolean; error: boolean; count: number }) {
  return <><p role="status">{loading ? "正在读取诊断…" : `已读取 ${count} 条`}</p>{error && <p role="alert">诊断读取失败或响应不合法。已有结果可能过期，请重试。</p>}</>;
}
function OperationDetails({ operationId }: { operationId: string }) {
  const [request, setRequest] = useState<string | null>(null);
  const indexQuery = useCallback((after: string, signal: AbortSignal) => queryDiagnosticIndex({ operation_id: operationId }, after, signal), [operationId]);
  const linksQuery = useCallback((after: string, signal: AbortSignal) => queryDiagnosticLinks(operationId, after, signal), [operationId]);
  const index = useDiagnosticPages(indexQuery, "" as string, traceId, 250);
  const links = useDiagnosticPages(linksQuery, "" as string, requestId);
  return <section aria-label="Operation 关联详情" style={card}>
    <h3 style={{ overflowWrap: "anywhere" }}>{operationId}</h3>
    <p>以下是诊断引用。提交结论仍须以领域回执和原始 Harness 记录为准。</p>
    <Status loading={index.loading || links.loading} error={index.error || links.error} count={index.items.length + links.items.length} />
    {index.page?.coverage.freshness === "unavailable" && <p role="alert">Harness 索引不可用。</p>}
    {links.page?.gap && !links.items.length && <p role="status">关联缺口：{links.page.gap}</p>}
    <button style={button} onClick={() => { index.refresh(); links.refresh(); }}>重读关联</button>
    <h4>Harness 阶段与尝试</h4>
    {index.items.map(item => <details key={item.trace_id} style={card}><summary>{item.workflow} / {item.stage} · {item.status ?? "未终结"} · {item.commit_status ?? "无提交结论"}</summary><pre style={pre}>{JSON.stringify(item, null, 2)}</pre></details>)}
    {index.page?.has_more && <button style={button} disabled={index.loading || index.atCapacity} onClick={index.more}>继续读取 Harness</button>}
    <h4>请求、动作与页面关联</h4>
    {links.items.map(item => <details key={item.request_id} style={card}><summary style={{ overflowWrap: "anywhere" }}>{item.request_id}</summary><pre style={pre}>{JSON.stringify(item, null, 2)}</pre><button style={button} onClick={() => setRequest(item.request_id)}>查看关联请求事件</button></details>)}
    {request && <EventResults key={request} filters={{ request_id: request }} allowOperation={false} />}
    {links.page?.items.length === 100 && <button style={button} disabled={links.loading || links.atCapacity} onClick={links.more}>继续读取关联请求</button>}
    {(index.atCapacity || links.atCapacity) && <p>已达本视图显示上限；请缩小筛选范围。</p>}
  </section>;
}
function EventResults({ filters, allowOperation = true, allowResource = true }: { filters: DiagnosticEventFilters; allowOperation?: boolean; allowResource?: boolean }) {
  const [resourceRequest, setResourceRequest] = useState<string | null>(null);
  const [operation, setOperation] = useState<string | null>(null);
  const serialized = JSON.stringify(filters);
  const query = useCallback((after: number, signal: AbortSignal) => queryDiagnosticEvents(JSON.parse(serialized), after, signal), [serialized]);
  const state = useDiagnosticPages(query, 0 as number, eventId);
  return <>
    <Status loading={state.loading} error={state.error} count={state.items.length} />
    <button style={button} onClick={state.refresh} disabled={state.loading}>刷新诊断</button>
    {state.page && <p>写入器：{state.page.health.writer_alive ? "运行中" : "已停止"}；队列 {state.page.health.queued}；丢弃 {state.page.health.dropped}；写入失败 {state.page.health.write_failures}；读取失败 {state.page.health.read_failures}{state.page.desktop_spool && `；桌面拒绝 ${state.page.desktop_spool.rejected} / 失败 ${state.page.desktop_spool.failures}`}</p>}
    {state.page?.retention && <p>保留事件 {state.page.retention.retained_events}；累计移除 {state.page.retention.removed_events}。{state.page.retention.removed_events > 0 ? "已有历史记录被清理，当前显示不代表完整历史。" : ""}{state.page.retention.cursor_gap ? "本次游标范围存在清理缺口。" : ""}{state.page.retention.legacy_timestamp_rows > 0 ? ` ${state.page.retention.legacy_timestamp_rows} 条历史事件的原始入库时间未知。` : ""}</p>}
    {!state.loading && !state.error && !state.items.length && <p>当前筛选没有已保留的事件；不代表该流程从未执行。</p>}
    <div style={{ display: "grid", gap: 8 }}>
      {state.items.map(({ sequence, event }) => <article key={event.event_id} style={card}>
        <details><summary style={{ overflowWrap: "anywhere" }}>#{sequence} · {event.timestamp} · {event.name} · {event.outcome} · {event.duration_ms == null ? "耗时未知" : `${event.duration_ms.toFixed(1)} ms`}</summary>
          <pre style={pre}>{JSON.stringify(event, null, 2)}</pre>
        </details>
        {allowResource && event.resource && event.request_id && <button style={button} onClick={() => setResourceRequest(event.request_id)}>查看资源关联请求</button>}
        {allowOperation && event.harness && <button style={button} onClick={() => setOperation(event.harness!.operation_id)}>展开 operation 关联</button>}
      </article>)}
    </div>
    {state.page?.has_more && <button style={button} onClick={state.more} disabled={state.loading || state.atCapacity}>读取下一页事件</button>}
    {state.atCapacity && <p>已显示 500 条事件，请缩小范围后重新查询。</p>}
    {resourceRequest && <section aria-label="资源关联请求" style={card}><button style={button} onClick={() => setResourceRequest(null)}>收起资源关联请求</button><EventResults key={resourceRequest} filters={{ request_id: resourceRequest }} allowResource={false} /></section>}
    {operation && <><button style={button} onClick={() => setOperation(null)}>收起 operation 关联</button><OperationDetails key={operation} operationId={operation} /></>}
  </>;
}
function IndexResults({ filters }: { filters: DiagnosticEventFilters }) {
  const [operation, setOperation] = useState<string | null>(null);
  const [role, setRole] = useState<DiagnosticIndexFilters["resource_role"]>();
  const serialized = JSON.stringify({ workflow: filters.workflow, stage: filters.stage, operation_id: filters.operation_id,
    resource_id: filters.resource_id, resource_type: filters.resource_type, resource_role: role });
  const query = useCallback((after: string, signal: AbortSignal) => queryDiagnosticIndex(JSON.parse(serialized), after, signal), [serialized]);
  const state = useDiagnosticPages(query, "" as string, traceId, 250);
  return <>
    <p>索引使用流程、阶段、operation 和资源筛选；页面与时间条件不适用于此视图。资源来自历史 canonical 记录，不表示当前状态；未回填或源记录缺失的资源无法匹配。</p>
    <label>资源关联来源<select aria-label="资源关联来源" style={{ minHeight: 44 }} value={role ?? ""} onChange={event => { setRole((event.target.value || undefined) as DiagnosticIndexFilters["resource_role"]); setOperation(null); }}>
      <option value="">全部来源</option><option value="context_subjects">上下文资源</option><option value="attempted_outputs">尝试输出</option><option value="committed_outputs">已提交输出</option>
    </select></label>
    <Status loading={state.loading} error={state.error} count={state.items.length} />
    <button style={button} disabled={state.loading} onClick={state.refresh}>刷新索引</button>
    {state.page && <p>覆盖状态：{state.page.coverage.freshness}；完成扫描 {state.page.coverage.completed_sweeps ?? "未知"}；失败 {state.page.coverage.failures}。索引可能滞后，不能代替提交回执。</p>}
    {state.items.map(item => <article key={item.trace_id} style={card}><p>{item.workflow} / {item.stage} · {item.status ?? "未终结"} · {item.gap ?? "已索引"}</p>{item.operation_id && <button style={button} onClick={() => setOperation(item.operation_id)}>展开 operation 关联</button>}<details><summary>索引指标</summary><pre style={pre}>{JSON.stringify(item, null, 2)}</pre></details></article>)}
    {state.page?.has_more && <button style={button} disabled={state.loading || state.atCapacity} onClick={state.more}>读取下一页索引</button>}
    {state.atCapacity && <p>已显示 250 条索引，请缩小范围。</p>}
    {operation && <OperationDetails key={operation} operationId={operation} />}
  </>;
}
const writerId = (row: DiagnosticWriterEpochV1) => row.epoch_id;
function WriterResults() {
  const query = useCallback((after: number, signal: AbortSignal) => queryDiagnosticWriters(after, signal), []);
  const state = useDiagnosticPages(query, 0 as number, writerId, 500);
  return <section aria-label="采集覆盖">
    <h3>采集覆盖</h3>
    <p>这是本安装的写入器检查点，不使用事件筛选。计数为已观察下限；启动前及未落盘队列的损失无法完整重建。</p>
    <Status loading={state.loading} error={state.error} count={state.items.length} />
    <button style={button} onClick={state.refresh} disabled={state.loading}>刷新采集覆盖</button>
    {state.page && <p>已观察丢弃 {state.page.totals.observed_dropped}；写入失败 {state.page.totals.observed_write_failures}；读取失败 {state.page.totals.observed_read_failures}；未记录关闭 {state.page.totals.unclosed_epochs}；已汇总旧记录 {state.page.totals.retired_epochs}（其中未记录关闭 {state.page.totals.retired_unclosed}）。未关闭可能表示仍在运行或已中断，不代表已证实崩溃。</p>}
    {state.items.map(item => <details key={item.epoch_id} style={card}><summary>写入器 #{item.sequence} · {item.closed_at === null ? "无关闭记录" : "已记录关闭"}</summary><pre style={pre}>{JSON.stringify(item, null, 2)}</pre></details>)}
    {state.page?.has_more && <button style={button} disabled={state.loading || state.atCapacity} onClick={state.more}>读取下一页写入器</button>}
    {state.atCapacity && <p>已达到本次显示上限，请刷新读取当前保留记录。</p>}
  </section>;
}
export function DiagnosticTimeline({ currentPageOnly = false }: { currentPageOnly?: boolean }) {
  const page = useSyncExternalStore(subscribeDiagnosticPage, currentDiagnosticPage, emptyPage);
  const [filters, setFilters] = useState<DiagnosticEventFilters>({});
  const [mode, setMode] = useState<"events" | "index" | "writers" | "audit" | "storage">("events");
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const values = Object.fromEntries(new FormData(event.currentTarget));
    const next: Record<string, string> = {};
    for (const [key, value] of Object.entries(values)) if (typeof value === "string" && value.trim()) next[key] = key === "since" || key === "until" ? new Date(value).toISOString() : value.trim();
    setFilters(next as DiagnosticEventFilters);
  }
  const effective = currentPageOnly ? { page_view_id: page?.id || undefined } : filters;
  return <section aria-label={currentPageOnly ? "当前页面诊断" : "全局诊断时间线"}>
    <h2>{currentPageOnly ? "当前页面诊断" : "全局诊断时间线"}</h2>
    <p>按入库顺序显示保留记录。HTTP 完成不等于业务提交；父子耗时不应相加。</p>
    {!currentPageOnly && <p>事件与导出中的资源条件匹配直接记录的资源引用（包含领域保存结果与已提交回执投影）。跨域 canonical 资源请在 Harness 索引中筛选，再展开关联请求；两者的匹配范围不同。</p>}
    {!currentPageOnly && <>
      <form onSubmit={submit} style={{ display: "grid", gap: 8, gridTemplateColumns: "repeat(auto-fit, minmax(min(180px, 100%), 1fr))" }}>
        <label style={{ display: "grid", gap: 4, minWidth: 0 }}>流程<select style={{ width: "100%", minWidth: 0, minHeight: 44, boxSizing: "border-box" }} name="workflow" aria-label="流程"><option value="">全部</option>{schemas.index.$defs.HarnessWorkflow.enum.map(value => <option key={value}>{value}</option>)}</select></label>
        <label style={{ display: "grid", gap: 4, minWidth: 0 }}>阶段<select style={{ width: "100%", minWidth: 0, minHeight: 44, boxSizing: "border-box" }} name="stage" aria-label="阶段"><option value="">全部</option>{schemas.index.$defs.HarnessStage.enum.map(value => <option key={value}>{value}</option>)}</select></label>
        <label style={{ display: "grid", gap: 4, minWidth: 0 }}>页面<select style={{ width: "100%", minWidth: 0, minHeight: 44, boxSizing: "border-box" }} name="page_path" aria-label="页面"><option value="">全部</option>{paths.map(value => <option key={value}>{value}</option>)}</select></label>
        <label style={{ display: "grid", gap: 4, minWidth: 0 }}>来源<select style={{ width: "100%", minWidth: 0, minHeight: 44, boxSizing: "border-box" }} name="source" aria-label="来源"><option value="">全部</option>{["browser", "server", "desktop"].map(value => <option key={value}>{value}</option>)}</select></label>
        <label style={{ display: "grid", gap: 4, minWidth: 0 }}>级别<select style={{ width: "100%", minWidth: 0, minHeight: 44, boxSizing: "border-box" }} name="severity" aria-label="级别"><option value="">全部</option>{["info", "warning", "error"].map(value => <option key={value}>{value}</option>)}</select></label>
        <label style={{ display: "grid", gap: 4, minWidth: 0 }}>资源类型<select style={{ width: "100%", minWidth: 0, minHeight: 44, boxSizing: "border-box" }} name="resource_type" aria-label="资源类型"><option value="">全部</option>{schemas.index.$defs.HarnessResourceType.enum.map(value => <option key={value}>{value}</option>)}</select></label>
        {["operation_id", "request_id", "flow_id", "action_id", "resource_id"].map(key => <label key={key} style={{ display: "grid", gap: 4, minWidth: 0 }}>{key}<input style={{ width: "100%", minWidth: 0, minHeight: 44, boxSizing: "border-box" }} name={key} maxLength={160} /></label>)}
        <label style={{ display: "grid", gap: 4, minWidth: 0 }}>开始时间（本地）<input style={{ width: "100%", minWidth: 0, minHeight: 44, boxSizing: "border-box" }} type="datetime-local" name="since" /></label><label style={{ display: "grid", gap: 4, minWidth: 0 }}>结束时间（本地）<input style={{ width: "100%", minWidth: 0, minHeight: 44, boxSizing: "border-box" }} type="datetime-local" name="until" /></label>
        <button style={button} type="submit">应用筛选</button>
      </form>
      <div style={{ display: "flex", flexWrap: "wrap", gap: 8, marginTop: 12 }}><button style={button} aria-pressed={mode === "events"} onClick={() => setMode("events")}>事件时间线</button><button style={button} aria-pressed={mode === "index"} onClick={() => setMode("index")}>Harness 索引</button><button style={button} aria-pressed={mode === "writers"} onClick={() => setMode("writers")}>采集覆盖</button><button style={button} aria-pressed={mode === "audit"} onClick={() => setMode("audit")}>统计与导出</button><button style={button} aria-pressed={mode === "storage"} onClick={() => setMode("storage")}>存储状态</button></div>
    </>}
    {currentPageOnly && !page?.id ? <p>当前页面尚未注册诊断身份。</p> : mode === "events" || currentPageOnly ? <EventResults key={JSON.stringify(effective)} filters={effective} /> : mode === "index" ? <IndexResults key={JSON.stringify(filters)} filters={filters} />  : mode === "writers" ? <WriterResults /> : mode === "storage" ? <DiagnosticStoragePanel /> : <DiagnosticAuditPanel key={JSON.stringify(filters)} filters={filters} />}
  </section>;
}
