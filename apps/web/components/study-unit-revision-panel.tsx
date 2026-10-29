"use client";

import { useEffect, useRef, useState } from "react";
import type { DocumentRecord, LearningPlan, StudyUnit, StudyUnitRevision } from "@vibe-learner/shared";
import { decideStudyUnitRevision, getStudyUnitRevision } from "../lib/data/learning-plans";
import { isApiHttpError } from "../lib/http-error";

const defaultPort = { getStudyUnitRevision, decideStudyUnitRevision };
const copy: Record<StudyUnitRevision["status"], string> = {
  ready: "当前计划已按原教材单元保存。检查差异后，可独立确认教材修订；也可拒绝或暂时跳过，继续使用当前计划。",
  applying: "正在保存教材修订，可查询本次结果。",
  accepted: "教材单元已更新。当前计划保留原切分；后续新计划将使用确认后的教材。",
  rejected: "已拒绝教材修订，教材和当前计划保持原样。",
  conflict: "教材已发生变化，此修订未应用。请刷新教材后重新生成计划。",
  failed: "教材修订未完成，请查询记录或刷新教材后重新开始。",
};
const kinds: Record<string, string> = { chapter: "正文", front_matter: "前言", solutions: "解答", back_matter: "附录" };
type UnitContent = Pick<StudyUnit, "title" | "pageStart" | "pageEnd" | "unitKind" | "includeInPlan" | "summary">;
function describe(unit: UnitContent) {
  return `${unit.title} · PDF ${unit.pageStart}–${unit.pageEnd} · ${kinds[unit.unitKind]} · ${unit.includeInPlan ? "纳入计划" : "不纳入计划"}${unit.summary ? `\n${unit.summary}` : ""}`;
}

export function StudyUnitRevisionPanel({ plan, document, onRefresh, port = defaultPort }: {
  plan: LearningPlan;
  document: DocumentRecord | null;
  onRefresh: () => Promise<unknown>;
  port?: typeof defaultPort;
}) {
  const [record, setRecord] = useState<StudyUnitRevision | null>(null);
  const [busy, setBusy] = useState(false);
  const [unknown, setUnknown] = useState(false);
  const [notice, setNotice] = useState("");
  const lifetime = useRef(0);
  const flight = useRef(false);
  const refresh = useRef(onRefresh);
  refresh.current = onRefresh;

  useEffect(() => {
    const epoch = ++lifetime.current;
    setRecord(null); setNotice(""); setUnknown(false); setBusy(false); flight.current = false;
    if (plan.documentId) {
      port.getStudyUnitRevision(plan.id, plan.documentId).then(value => {
        if (epoch === lifetime.current) setRecord(value);
      }).catch(error => {
        if (epoch !== lifetime.current) return;
        if (isApiHttpError(error) && error.status === 404 && typeof error.payload === "object" && error.payload !== null && "detail" in error.payload && error.payload.detail === "study_unit_revision_not_found") return;
        setNotice("教材修订预览暂时不可用，请稍后查询。");
      });
    }
    return () => { lifetime.current++; };
  }, [plan.id, plan.documentId, port]);

  async function run(decision?: "accept" | "reject") {
    if (flight.current || (decision && (unknown || record?.status !== "ready"))) return;
    const epoch = lifetime.current;
    flight.current = true; setBusy(true);
    try {
      const value = decision
        ? await port.decideStudyUnitRevision(plan.id, plan.documentId, record!.preview.operationId, decision)
        : await port.getStudyUnitRevision(plan.id, plan.documentId);
      if (epoch !== lifetime.current) return;
      setRecord(value); setUnknown(false); setNotice("");
      if (value.status === "accepted") {
        try { await refresh.current(); }
        catch { if (epoch === lifetime.current) setNotice("教材修订已保存，页面刷新失败。请刷新教材以查看最新版本。"); }
      }
    } catch {
      if (epoch === lifetime.current) {
        if (decision) setUnknown(true);
        setNotice("暂时无法确认结果，请查询本次修订；查询不会重新提交教材修改。");
      }
    } finally {
      if (epoch === lifetime.current) { flight.current = false; setBusy(false); }
    }
  }

  if (!plan.documentId || (!record && !notice)) return null;
  const base = record?.preview.baseDocument;
  const suggestions = record?.preview.suggestions.studyUnits ?? [];
  const oldUnits = base?.studyUnits ?? [];
  const matching = (unit: UnitContent) => oldUnits.filter(old => old.pageStart === unit.pageStart && old.pageEnd === unit.pageEnd);
  const rows = suggestions.map(unit => {
    const old = matching(unit);
    return { before: old.length === 1 ? describe(old[0]) : "—", after: describe(unit),
      status: old.length === 1 ? (describe(old[0]) === describe(unit) ? "保留" : "修改并保留标识") : "新增" };
  });
  oldUnits.filter(old => !suggestions.some(unit => matching(unit).length === 1 && matching(unit)[0].id === old.id))
    .forEach(old => rows.push({ before: describe(old), after: "—", status: "移除（历史计划保留）" }));
  const stale = !!base && (!document || document.id !== base.id || document.revision !== base.revision);
  return <details className="plan-revision-panel" open>
    <summary>教材单元修订预览</summary>
    <section className="plan-revision-content" aria-label="教材单元修订" aria-busy={busy}>
      {record && <p role="status">{copy[record.status]}</p>}
      {base && <p>基于教材版本 {base.revision}；当前教材版本 {document?.revision ?? "待刷新"}。</p>}
      {record?.preview.suggestions.rationale && <p>{record.preview.suggestions.rationale}</p>}
      {!!rows.length && <div className="plan-revision-table-wrap"><table>
        <caption>标题、PDF 物理页范围、分类与保留差异</caption>
        <thead><tr><th scope="col">处理</th><th scope="col">修订前</th><th scope="col">修订后</th></tr></thead>
        <tbody>{rows.map((row, index) => <tr key={index}><th scope="row">{row.status}</th><td>{row.before}</td><td>{row.after}</td></tr>)}</tbody>
      </table></div>}
      {record?.status === "ready" && <div className="plan-revision-decision-actions">
        <button type="button" className="plan-revision-primary" disabled={busy || unknown || stale} onClick={() => void run("accept")}>确认教材修订</button>
        <button type="button" className="plan-revision-secondary" disabled={busy || unknown} onClick={() => void run("reject")}>拒绝教材修订</button>
      </div>}
      {record?.status === "ready" && stale && <p role="alert">教材版本已变化或尚未加载，旧预览不能应用。请刷新教材。</p>}
      {notice && <p role="status">{notice}</p>}
      <button type="button" className="plan-revision-secondary" disabled={busy} onClick={() => void run()}>查询教材修订结果</button>
    </section>
  </details>;
}
