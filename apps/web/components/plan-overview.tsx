"use client";

import type { CSSProperties } from "react";
import type { LearningPlan } from "@vibe-learner/shared";
import type { PlanHistoryItem } from "../lib/plan-panel-data";

interface PlanOverviewProps {
  plan: LearningPlan | null;
  items: PlanHistoryItem[];
  selectedPlanId: string;
  documentTitle: string;
  personaName: string;
  planPositionLabel: string;
  hasSession: boolean;
  isBusy: boolean;
  isRefreshing: boolean;
  onSelectPlan: (planId: string) => void;
  onRefresh: () => void;
  onCreateSession: () => void;
}

export function PlanOverview({
  plan,
  items,
  selectedPlanId,
  documentTitle,
  personaName,
  planPositionLabel,
  hasSession,
  isBusy,
  isRefreshing,
  onSelectPlan,
  onRefresh,
  onCreateSession,
}: PlanOverviewProps) {
  const activeCourseTitle = plan
    ? resolveCourseTitle(plan.courseTitle, documentTitle)
    : "上传教材后，这里会显示当前计划。";

  return (
    <div style={styles.wrap}>
      <div style={styles.selectorRow}>
        <select
          value={selectedPlanId}
          onChange={(event) => onSelectPlan(event.target.value)}
          style={styles.select}
          disabled={!items.length}
        >
          {items.length ? (
            items.map((item, index) => (
              <option key={item.id} value={item.id}>
                {`#${index + 1} ${resolveCourseTitle(item.courseTitle, item.documentTitle)} · ${formatDate(item.createdAt)}`}
              </option>
            ))
          ) : (
            <option value="">暂无学习计划</option>
          )}
        </select>
        <button
          type="button"
          style={styles.ghostButton}
          onClick={onRefresh}
          disabled={isRefreshing}
        >
          {isRefreshing ? "刷新中…" : "刷新"}
        </button>
      </div>

      <div style={styles.titleRow}>
        <h2 style={styles.title}>{activeCourseTitle}</h2>
        {plan ? <span style={styles.badge}>{planPositionLabel}</span> : null}
      </div>

      {plan ? (
        <>
          <p style={styles.overview}>{plan.overview}</p>

          <dl style={styles.meta}>
            <div style={styles.metaItem}>
              <dt style={styles.metaKey}>学习目标</dt>
              <dd style={styles.metaVal}>{plan.objective || "未填写"}</dd>
            </div>
            <div style={styles.metaItem}>
              <dt style={styles.metaKey}>教材</dt>
              <dd style={styles.metaVal}>{documentTitle}</dd>
            </div>
            <div style={styles.metaItem}>
              <dt style={styles.metaKey}>教师人格</dt>
              <dd style={styles.metaVal}>{personaName}</dd>
            </div>
            <div style={styles.metaItem}>
              <dt style={styles.metaKey}>生成时间</dt>
              <dd style={styles.metaVal}>{formatDate(plan.createdAt)}</dd>
            </div>
          </dl>

          <div style={styles.actionRow}>
            {hasSession ? (
              <span style={styles.sessionConnected}>章节会话已连接</span>
            ) : (
              <button
                type="button"
                style={{
                  ...styles.primaryButton,
                  ...(isBusy ? styles.buttonDisabled : {})
                }}
                onClick={onCreateSession}
                disabled={isBusy}
              >
                {isBusy ? "创建中…" : "创建章节会话"}
              </button>
            )}
          </div>
        </>
      ) : null}

      {plan?.weeklyFocus.length ? (
        <div style={styles.section}>
          <div style={styles.sectionHead}>
            <span style={styles.sectionLabel}>主线主题</span>
            <span style={styles.count}>{plan.weeklyFocus.length}</span>
          </div>
          <ol style={styles.list}>
            {plan.weeklyFocus.map((focus, index) => (
              <li key={`${focus}-${index}`} style={styles.listItem}>
                <span style={styles.idx}>{index + 1}</span>
                <span>{focus}</span>
              </li>
            ))}
          </ol>
        </div>
      ) : null}

      <div style={styles.section}>
        <div style={styles.sectionHead}>
          <span style={styles.sectionLabel}>今日任务</span>
          <span style={styles.count}>{plan?.todayTasks.length ?? 0}</span>
        </div>
        <ol style={styles.list}>
          {(plan?.todayTasks.length
            ? plan.todayTasks
            : ["暂无今日任务，先上传教材并生成计划。"]
          ).map((task, index) => (
            <li key={`${task}-${index}`} style={styles.listItem}>
              <span style={styles.idx}>{index + 1}</span>
              <span>{task}</span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    display: "grid",
    gap: 0,
    paddingLeft: 40,
  },
  selectorRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    paddingBottom: 14,
  },
  select: {
    flex: 1,
    height: 34,
    border: "1px solid var(--border)",
    padding: "0 8px",
    background: "var(--panel)",
    color: "var(--ink)",
    fontSize: 13,
    minWidth: 0,
  },
  ghostButton: {
    height: 34,
    border: "1px solid var(--border)",
    padding: "0 12px",
    background: "transparent",
    color: "var(--muted)",
    fontSize: 13,
    cursor: "pointer",
    whiteSpace: "nowrap",
  },
  titleRow: {
    display: "flex",
    alignItems: "baseline",
    justifyContent: "space-between",
    gap: 12,
    paddingBottom: 8,
  },
  title: {
    margin: 0,
    fontSize: "clamp(1.1rem, 1.6vw, 1.35rem)",
    lineHeight: 1.3,
    fontWeight: 700,
    color: "var(--ink)",
  },
  badge: {
    fontSize: 12,
    color: "var(--muted)",
    whiteSpace: "nowrap",
  },
  overview: {
    margin: "0 0 16px",
    color: "var(--muted)",
    fontSize: 13,
    lineHeight: 1.7,
  },
  meta: {
    margin: 0,
    padding: "0 0 14px",
    display: "flex",
    flexWrap: "wrap",
    gap: "6px 20px",
  },
  metaItem: {
    display: "flex",
    gap: 6,
    alignItems: "baseline",
  },
  metaKey: {
    fontSize: 11,
    fontWeight: 600,
    color: "var(--muted)",
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    flexShrink: 0,
  },
  metaVal: {
    margin: 0,
    fontSize: 13,
    color: "var(--ink)",
  },
  actionRow: {
    paddingBottom: 16,
  },
  primaryButton: {
    border: "none",
    height: 34,
    padding: "0 16px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 13,
  },
  buttonDisabled: {
    opacity: 0.45,
    cursor: "not-allowed",
  },
  sessionConnected: {
    fontSize: 13,
    color: "var(--positive)",
    fontWeight: 500,
  },
  section: {
    paddingTop: 16,
    paddingBottom: 4,
    borderTop: "1px solid var(--border)",
    display: "grid",
    gap: 10,
  },
  sectionHead: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  sectionLabel: {
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "var(--muted)",
  },
  count: {
    fontSize: 11,
    color: "var(--muted)",
    background: "var(--panel)",
    border: "1px solid var(--border)",
    padding: "1px 6px",
    fontWeight: 600,
  },
  list: {
    listStyle: "none",
    margin: 0,
    padding: 0,
    display: "grid",
    gap: 6,
  },
  listItem: {
    display: "flex",
    gap: 10,
    alignItems: "baseline",
    fontSize: 13,
    lineHeight: 1.6,
    color: "var(--ink)",
  },
  idx: {
    fontSize: 11,
    fontWeight: 700,
    color: "var(--accent)",
    minWidth: 16,
    flexShrink: 0,
  },
};

function formatDate(value: string) {
  if (!value) return "未知时间";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function resolveCourseTitle(courseTitle: string, documentTitle: string) {
  if (courseTitle.trim()) return courseTitle.trim();
  if (documentTitle.trim()) return documentTitle.trim();
  return "当前学习计划";
}
