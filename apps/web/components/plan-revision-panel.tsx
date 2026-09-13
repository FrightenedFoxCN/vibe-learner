"use client";

import { useEffect, useRef, useState } from "react";
import type { LearningPlan, PlanRevision } from "@vibe-learner/shared";
import { createPlanRevision, decidePlanRevision, getPlanRevision, listPlanRevisions } from "../lib/api";

import { isApiHttpError } from "../lib/http-error";

const copy: Record<PlanRevision["status"], string> = {
  generating: "正在生成修订预览，可离页后回来查询。",
  ready: "修订预览已保存。请检查差异，再选择接受或拒绝。",
  applying: "正在保存修订，请查询本次结果。",
  accepted: "修订已保存。",
  rejected: "已拒绝此修订，计划没有变化。",
  failed: "本次修订未完成。可以刷新计划后生成新的预览。",
  uncertain: "未能确认模型是否完成；本次修订尚未应用。可查询记录，或主动生成新的预览。",
  conflict: "计划已发生变化，此修订未应用。请刷新计划后重新生成预览。",
};

export function PlanRevisionPanel({ plan, onRefresh }: { plan: LearningPlan; onRefresh: () => Promise<unknown> }) {
  const storageKey = `vibe-learner:plan-revision:v1:${plan.id}`;
  const [instruction, setInstruction] = useState("");
  const [record, setRecord] = useState<PlanRevision | null>(null);
  const [requestId, setRequestId] = useState("");
  const [busy, setBusy] = useState(false);
  const [outcomeUnknown, setOutcomeUnknown] = useState(false);
  const [missingRecord, setMissingRecord] = useState(false);
  const [notice, setNotice] = useState("");
  const [history, setHistory] = useState<number[]>([]);
  const [rollback, setRollback] = useState("");
  const [open, setOpen] = useState(false);
  const mounted = useRef(false);
  const inFlight = useRef(false);
  const refresh = useRef(onRefresh);
  refresh.current = onRefresh;

  async function apply(value: PlanRevision) {
    if (!mounted.current) return;
    setRecord(value);
    setOutcomeUnknown(false);
    setMissingRecord(false);
    setNotice(copy[value.status]);
    if (value.status === "accepted") await refresh.current();
  }
  async function query(id = requestId) {
    if (!id || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    try { await apply(await getPlanRevision(plan.id, id)); }
    catch (error) {
      if (mounted.current) {
        const missing = isApiHttpError(error) && error.status === 404 && error.payload &&
          typeof error.payload === "object" && "detail" in error.payload && error.payload.detail === "plan_revision_not_found";
        setMissingRecord(!!missing);
        setNotice(missing ? "尚未找到这次修订。可继续查询，或清除本地恢复记录后主动重新开始。" : "暂时无法查询修订结果，请稍后继续查询。不会重新发送生成请求。");
      }
    }
    finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  }
  useEffect(() => {
    mounted.current = true;
    let saved = "";
    try { saved = localStorage.getItem(storageKey) ?? ""; } catch { /* unavailable storage is handled before admission */ }
    if (/^[A-Za-z0-9._:-]{1,80}$/.test(saved)) {
      setRequestId(saved); setOpen(true); void query(saved);
    }
    return () => { mounted.current = false; };
    // The parent keys this component by immutable Plan ID.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [storageKey]);
  useEffect(() => {
    if (!open) return;
    let active = true;
    listPlanRevisions(plan.id).then(values => { if (active) setHistory(values); }).catch(() => {
      if (active) setNotice("版本历史暂时不可用，可稍后重新打开此区域。");
    });
    return () => { active = false; };
  }, [open, plan.id, plan.revision]);

  const unresolved = !!requestId && (outcomeUnknown || !record || ["generating", "ready", "applying"].includes(record.status));
  async function generate(rollbackRevision?: number) {
    if (inFlight.current || unresolved) return;
    const id = crypto.randomUUID();
    // Retain identity before issuing a POST; an ambiguous response is query-only.
    try { localStorage.setItem(storageKey, id); }
    catch { setNotice("无法保存恢复记录，请允许本地存储后再修订。"); return; }
    setRequestId(id); setRecord(null); setMissingRecord(false); setBusy(true); inFlight.current = true;
    setNotice(rollbackRevision === undefined ? "正在生成修订预览…" : "正在准备回滚预览…");
    try { await apply(await createPlanRevision(plan.id, { clientRequestId: id, baseRevision: plan.revision,
      ...(rollbackRevision === undefined ? { instruction: instruction.trim() } : { rollbackRevision }) })); }
    catch (error) {
      if (mounted.current) {
        const detail = isApiHttpError(error) && error.payload && typeof error.payload === "object" && "detail" in error.payload ? error.payload.detail : "";
        const definite = isApiHttpError(error) && (error.status === 422 ||
          ((error.status === 404 || error.status === 409) && ["plan_not_found", "learning_plan_revision_conflict", "plan_revision_request_mismatch"].includes(String(detail))));
        if (definite) {
          try { localStorage.removeItem(storageKey); } catch { /* no admitted operation exists */ }
          setRequestId(""); setRecord(null); setOutcomeUnknown(false);
          setNotice("请求未被接收，请刷新当前计划后重新生成预览。");
        } else { setOutcomeUnknown(true); setNotice("本次结果未确认，请查询修订记录。若计划已更新，请先刷新计划。"); }
      }
    }
    finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  }
  async function decide(decision: "accept" | "reject") {
    if (inFlight.current || outcomeUnknown || record?.status !== "ready") return;
    inFlight.current = true; setBusy(true);
    try { await apply(await decidePlanRevision(plan.id, requestId, decision)); }
    catch { if (mounted.current) { setOutcomeUnknown(true); setNotice("保存结果未确认，请查询本次修订；不要重复接受。"); } }
    finally { inFlight.current = false; if (mounted.current) setBusy(false); }
  }
  const proposal = record?.proposal;
  const rows = proposal && record ? [
    ["课程标题", record.basePlan.courseTitle, proposal.courseTitle],
    ["计划概览", record.basePlan.overview, proposal.overview],
    ["今日任务", record.basePlan.todayTasks.join("\n"), proposal.todayTasks.join("\n")],
    ["排期顺序", record.basePlan.schedule.map((item, i) => `${i + 1}. ${item.title}`).join("\n"),
      proposal.schedule.map((item, i) => `${i + 1}. ${item.title}`).join("\n")],
    ...proposal.schedule.map(item => {
      const before = record.basePlan.schedule.find(old => old.id === item.scheduleRef)!;
      return [`排期：${before.title}`, `${before.title}\n${before.focus}`, `${item.title}\n${item.focus}`];
    }),
  ] : [];
  return <details className="plan-revision-panel" open={open} onToggle={event => setOpen(event.currentTarget.open)}>
    <summary>修订计划 <span>版本 {plan.revision}</span></summary>
    <section aria-label="计划修订" aria-busy={busy} className="plan-revision-content">
      <p className="plan-revision-intro">可调整标题、概览、今日任务及现有排期的顺序与重点。教材章节和学习记录会保留。</p>
      <label className="plan-revision-field">修订要求<textarea value={instruction} onChange={event => setInstruction(event.target.value)} maxLength={8000}
        placeholder="例如：先复习基础，再加强例题练习" /></label>
      <div className="plan-revision-actions">
        <button type="button" className="plan-revision-primary" disabled={busy || unresolved || !instruction.trim()} onClick={() => void generate()}>生成修订预览</button>
      </div>
      <div className="plan-revision-rollback">
        <label className="plan-revision-field">历史版本 <select value={rollback} onChange={event => setRollback(event.target.value)}>
          <option value="">选择回滚内容的版本</option>
          {history.filter(value => value < plan.revision).map(value => <option key={value} value={value}>版本 {value}</option>)}
        </select></label>
        <button type="button" className="plan-revision-secondary" disabled={busy || unresolved || rollback === ""} onClick={() => void generate(Number(rollback))}>预览回滚</button>
      </div>
      <p className="plan-revision-hint">回滚会建立新版本，仅恢复计划内容和顺序，保留当前进度。</p>
      <p role="status" aria-live="polite">{notice}</p>
      {!!requestId && <button type="button" className="plan-revision-secondary" disabled={busy} onClick={() => void query()}>查询本次修订结果</button>}
      {missingRecord && <button type="button" className="plan-revision-secondary" disabled={busy} onClick={() => {
        try { localStorage.removeItem(storageKey); } catch { setNotice("无法清除本地恢复记录，请恢复本地存储后重试。"); return; }
        setRequestId(""); setRecord(null); setOutcomeUnknown(false); setMissingRecord(false);
        setNotice("已清除本地恢复记录。请刷新当前计划，再主动生成新预览。");
      }}>清除未找到的恢复记录</button>}
      {proposal && <>
        <p className="plan-revision-explanation">{proposal.explanation}</p>
        <p className="plan-revision-meta">基于版本 {record!.baseRevision}；当前版本 {plan.revision}。</p>
        <div className="plan-revision-table-wrap"><table>
          <caption>修订差异</caption><thead><tr>{["项目", "修订前", "修订后"].map(label => <th scope="col" key={label}>{label}</th>)}</tr></thead>
          <tbody>{rows.map(([label, before, after], index) => <tr key={index}><th scope="row">{label}</th><td>{before}</td><td>{after === before ? "未修改" : after}</td></tr>)}</tbody>
        </table>
        </div>
      </>}
      {record?.status === "ready" && <div className="plan-revision-decision-actions">
        <button type="button" className="plan-revision-primary" disabled={busy || outcomeUnknown || plan.revision !== record.baseRevision} onClick={() => void decide("accept")}>接受修订</button>
        <button type="button" className="plan-revision-secondary" disabled={busy || outcomeUnknown} onClick={() => void decide("reject")}>拒绝修订</button>
      </div>}
      {(record?.status === "conflict" || (record?.status === "ready" && plan.revision !== record.baseRevision)) && <p role="alert">计划版本已变化，旧预览不能应用。请刷新计划并拒绝旧预览，再重新生成。</p>}
      <button type="button" className="plan-revision-secondary" disabled={busy} onClick={() => void refresh.current()}>刷新当前计划</button>
    </section>
  </details>;
}
