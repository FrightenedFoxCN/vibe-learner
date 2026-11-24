"use client";

import type { RevisionReadbackTarget } from "../../lib/learning-workspace-state";

import styles from "./plan-revision.module.css";

import { useEffect, useRef, useState } from "react";
import type { LearningPlan, PlanRevision } from "@vibe-learner/shared";
import {
  createPlanRevision,
  decidePlanRevision,
  getPlanRevision,
  listPlanRevisions,
} from "../../lib/data/learning-plans";

import { isApiHttpError } from "../../lib/http-error";
import { planRevisionRecovery } from "../../lib/plan-revision-recovery";

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

export function PlanRevisionPanel({
  plan,
  onRefresh,
  readbackPending = false,
}: {
  plan: LearningPlan;
  onRefresh: (target?: RevisionReadbackTarget) => Promise<unknown>;
  readbackPending?: boolean;
}) {
  const recovery = () => planRevisionRecovery(plan.id, localStorage, sessionStorage);
  const [instruction, setInstruction] = useState("");
  const [record, setRecord] = useState<PlanRevision | null>(null);
  const [requestId, setRequestId] = useState("");
  const [recoverableIds, setRecoverableIds] = useState<string[]>([]);
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
    if (
      value.status === "accepted" &&
      value.result &&
      value.result.revision > plan.revision
    ) {
      await refresh.current({
        kind: "plan",
        id: value.result.id,
        revision: value.result.revision,
      });
    }
  }
  async function query(id = requestId) {
    if (!id || inFlight.current) return;
    inFlight.current = true;
    setBusy(true);
    try {
      await apply(await getPlanRevision(plan.id, id));
    } catch (error) {
      if (mounted.current) {
        const missing =
          isApiHttpError(error) &&
          error.status === 404 &&
          error.payload &&
          typeof error.payload === "object" &&
          "detail" in error.payload &&
          error.payload.detail === "plan_revision_not_found";
        setMissingRecord(!!missing);
        setNotice(
          missing
            ? "尚未找到这次修订。可继续查询，或清除本地恢复记录后主动重新开始。"
            : "暂时无法查询修订结果，请稍后继续查询。不会重新发送生成请求。",
        );
      }
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  function syncRecoverableIds() {
    try {
      setRecoverableIds(recovery().list());
    } catch {
      /* the current request can still be queried by its known ID */
    }
  }
  useEffect(() => {
    mounted.current = true;
    let saved = "";
    try {
      saved = recovery().current();
    } catch {
      /* unavailable storage is handled before admission */
    }
    if (saved) {
      setRequestId(saved);
      setOpen(true);
      void query(saved);
    }
    syncRecoverableIds();
    window.addEventListener("storage", syncRecoverableIds);
    return () => {
      mounted.current = false;
      window.removeEventListener("storage", syncRecoverableIds);
    };
    // The parent keys this component by immutable Plan ID.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan.id]);
  useEffect(() => {
    if (!open) return;
    let active = true;
    listPlanRevisions(plan.id)
      .then((values) => {
        if (active) setHistory(values);
      })
      .catch(() => {
        if (active) setNotice("版本历史暂时不可用，可稍后重新打开此区域。");
      });
    return () => {
      active = false;
    };
  }, [open, plan.id, plan.revision]);

  const unresolved =
    !!requestId &&
    (outcomeUnknown ||
      !record ||
      ["generating", "ready", "applying"].includes(record.status));
  function recover(id: string) {
    if (!id || inFlight.current || unresolved) return;
    try {
      if (!recovery().select(id)) {
        syncRecoverableIds();
        setNotice("这条本地恢复记录已不可用。");
        return;
      }
    } catch {
      setNotice("无法选择本地恢复记录，请恢复本地存储后重试。");
      return;
    }
    setRequestId(id);
    setRecord(null);
    setMissingRecord(false);
    setOutcomeUnknown(false);
    setNotice("正在查询修订结果…");
    void query(id);
  }
  async function generate(rollbackRevision?: number) {
    if (inFlight.current || unresolved || readbackPending) return;
    const id = crypto.randomUUID();
    // Retain identity before issuing a POST; an ambiguous response is query-only.
    try {
      recovery().remember(id);
    } catch {
      setNotice("无法保存恢复记录，请允许本地存储后再修订。");
      return;
    }
    if (requestId) {
      try {
        recovery().clear(requestId);
      } catch {
        /* failure to prune the previous result cannot affect the saved new ID */
      }
    }
    syncRecoverableIds();
    setRequestId(id);
    setRecord(null);
    setMissingRecord(false);
    setBusy(true);
    inFlight.current = true;
    setNotice(
      rollbackRevision === undefined ? "正在生成修订预览…" : "正在准备回滚预览…",
    );
    try {
      await apply(
        await createPlanRevision(plan.id, {
          clientRequestId: id,
          baseRevision: plan.revision,
          ...(rollbackRevision === undefined
            ? { instruction: instruction.trim() }
            : { rollbackRevision }),
        }),
      );
    } catch (error) {
      if (mounted.current) {
        const detail =
          isApiHttpError(error) &&
          error.payload &&
          typeof error.payload === "object" &&
          "detail" in error.payload
            ? error.payload.detail
            : "";
        const definite =
          isApiHttpError(error) &&
          (error.status === 422 ||
            ((error.status === 404 || error.status === 409) &&
              [
                "plan_not_found",
                "learning_plan_revision_conflict",
                "plan_revision_request_mismatch",
              ].includes(String(detail))));
        if (definite) {
          try {
            recovery().clear(id);
          } catch {
            /* no admitted operation exists */
          }
          syncRecoverableIds();
          setRequestId("");
          setRecord(null);
          setOutcomeUnknown(false);
          setNotice("请求未被接收，请刷新当前计划后重新生成预览。");
        } else {
          setOutcomeUnknown(true);
          setNotice("本次结果未确认，请查询修订记录。若计划已更新，请先刷新计划。");
        }
      }
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  async function decide(decision: "accept" | "reject") {
    if (
      inFlight.current ||
      readbackPending ||
      outcomeUnknown ||
      record?.status !== "ready"
    )
      return;
    inFlight.current = true;
    setBusy(true);
    try {
      await apply(await decidePlanRevision(plan.id, requestId, decision));
    } catch {
      if (mounted.current) {
        setOutcomeUnknown(true);
        setNotice("保存结果未确认，请查询本次修订；不要重复接受。");
      }
    } finally {
      inFlight.current = false;
      if (mounted.current) setBusy(false);
    }
  }
  const proposal = record?.proposal;
  const rows =
    proposal && record
      ? [
          ["课程标题", record.basePlan.courseTitle, proposal.courseTitle],
          ["计划概览", record.basePlan.overview, proposal.overview],
          [
            "今日任务",
            record.basePlan.todayTasks.join("\n"),
            proposal.todayTasks.join("\n"),
          ],
          [
            "排期顺序",
            record.basePlan.schedule
              .map((item, i) => `${i + 1}. ${item.title}`)
              .join("\n"),
            proposal.schedule.map((item, i) => `${i + 1}. ${item.title}`).join("\n"),
          ],
          ...proposal.schedule.map((item) => {
            const before = record.basePlan.schedule.find(
              (old) => old.id === item.scheduleRef,
            )!;
            return [
              `排期：${before.title}`,
              `${before.title}\n${before.focus}`,
              `${item.title}\n${item.focus}`,
            ];
          }),
        ]
      : [];
  return (
    <details
      className={styles.panel}
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary>
        修订计划 <span>版本 {plan.revision}</span>
      </summary>
      <section aria-label="计划修订" aria-busy={busy} className={styles.content}>
        <p className={styles.intro}>
          可调整标题、概览、今日任务及现有排期的顺序与重点。教材章节和学习记录会保留。
        </p>
        <label className={styles.field}>
          修订要求
          <textarea
            value={instruction}
            onChange={(event) => setInstruction(event.target.value)}
            maxLength={8000}
            placeholder="例如：先复习基础，再加强例题练习"
          />
        </label>
        <div className={styles.actions}>
          <button
            type="button"
            className={styles.primary}
            disabled={busy || readbackPending || unresolved || !instruction.trim()}
            onClick={() => void generate()}
          >
            生成修订预览
          </button>
        </div>
        <div className={styles.rollback}>
          <label className={styles.field}>
            历史版本{" "}
            <select
              value={rollback}
              onChange={(event) => setRollback(event.target.value)}
            >
              <option value="">选择回滚内容的版本</option>
              {history
                .filter((value) => value < plan.revision)
                .map((value) => (
                  <option key={value} value={value}>
                    版本 {value}
                  </option>
                ))}
            </select>
          </label>
          <button
            type="button"
            className={styles.secondary}
            disabled={busy || readbackPending || unresolved || rollback === ""}
            onClick={() => void generate(Number(rollback))}
          >
            预览回滚
          </button>
        </div>
        <p className={styles.hint}>
          回滚会建立新版本，仅恢复计划内容和顺序，保留当前进度。
        </p>
        <p role="status" aria-live="polite">
          {notice}
        </p>
        {!unresolved && recoverableIds.some((id) => id !== requestId) && (
          <label className={styles.field}>
            查询已有的本地修订
            <select
              value=""
              disabled={busy}
              onChange={(event) => recover(event.target.value)}
            >
              <option value="">选择恢复记录</option>
              {recoverableIds
                .filter((id) => id !== requestId)
                .map((id) => (
                  <option key={id} value={id}>
                    {id}
                  </option>
                ))}
            </select>
          </label>
        )}
        {!!requestId && (
          <button
            type="button"
            className={styles.secondary}
            disabled={busy}
            onClick={() => void query()}
          >
            查询本次修订结果
          </button>
        )}
        {missingRecord && (
          <button
            type="button"
            className={styles.secondary}
            disabled={busy}
            onClick={() => {
              try {
                recovery().clear(requestId);
              } catch {
                setNotice("无法清除本地恢复记录，请恢复本地存储后重试。");
                return;
              }
              syncRecoverableIds();
              setRequestId("");
              setRecord(null);
              setOutcomeUnknown(false);
              setMissingRecord(false);
              setNotice("已清除本地恢复记录。请刷新当前计划，再主动生成新预览。");
            }}
          >
            清除未找到的恢复记录
          </button>
        )}
        {proposal && (
          <>
            <p className={styles.explanation}>{proposal.explanation}</p>
            <p className={styles.meta}>
              基于版本 {record!.baseRevision}；当前版本 {plan.revision}。
            </p>
            <div className={styles.tableWrap}>
              <table>
                <caption>修订差异</caption>
                <thead>
                  <tr>
                    {["项目", "修订前", "修订后"].map((label) => (
                      <th scope="col" key={label}>
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map(([label, before, after], index) => (
                    <tr key={index}>
                      <th scope="row">{label}</th>
                      <td>{before}</td>
                      <td>{after === before ? "未修改" : after}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        {record?.status === "ready" && (
          <div className={styles.decisionActions}>
            <button
              type="button"
              className={styles.primary}
              disabled={
                busy ||
                readbackPending ||
                outcomeUnknown ||
                plan.revision !== record.baseRevision
              }
              onClick={() => void decide("accept")}
            >
              接受修订
            </button>
            <button
              type="button"
              className={styles.secondary}
              disabled={busy || readbackPending || outcomeUnknown}
              onClick={() => void decide("reject")}
            >
              拒绝修订
            </button>
          </div>
        )}
        {(record?.status === "conflict" ||
          (record?.status === "ready" && plan.revision !== record.baseRevision)) && (
          <p role="alert">
            计划版本已变化，旧预览不能应用。请刷新计划并拒绝旧预览，再重新生成。
          </p>
        )}
        <button
          type="button"
          className={styles.secondary}
          disabled={busy}
          onClick={() => void refresh.current()}
        >
          刷新当前计划
        </button>
      </section>
    </details>
  );
}
