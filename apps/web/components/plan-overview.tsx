"use client";

import type { CSSProperties } from "react";
import type { LearningPlan } from "@gal-learner/shared";
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
    : "上传教材后，这里会显示当前学习计划。";

  return (
    <article style={styles.panel}>
      <div style={styles.selectorSurface}>
        <div style={styles.selectorRow}>
          <label style={styles.selectorField}>
            <span style={styles.selectorLabel}>查看计划</span>
            <div style={styles.selectWrap}>
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
              <span style={styles.selectArrow}>▾</span>
            </div>
            <span style={styles.selectorHint}>
              统一在这里切换当前查看的学习计划与历史快照。
            </span>
          </label>
          <button
            type="button"
            style={styles.refreshButton}
            onClick={onRefresh}
            disabled={isRefreshing}
          >
            {isRefreshing ? "刷新中..." : "刷新快照"}
          </button>
        </div>
      </div>
      <div style={styles.headerRow}>
        <div style={styles.headerContent}>
          <p style={styles.sectionLabel}>学习计划</p>
          <h2 style={styles.panelTitle}>
            {activeCourseTitle}
          </h2>
        </div>
        {plan ? <span style={styles.positionBadge}>{planPositionLabel}</span> : null}
      </div>
      {plan ? (
        <>
          <div style={styles.summaryCard}>
            <p style={styles.summaryLabel}>计划摘要</p>
            <p style={styles.panelSummary}>{plan.overview}</p>
          </div>
          <dl style={styles.metaList}>
            <div style={styles.metaItem}>
              <dt style={styles.metaLabel}>学习目标</dt>
              <dd style={styles.metaValue}>{plan.objective || "未填写"}</dd>
            </div>
            <div style={styles.metaItem}>
              <dt style={styles.metaLabel}>教材</dt>
              <dd style={styles.metaValue}>{documentTitle}</dd>
            </div>
            <div style={styles.metaItem}>
              <dt style={styles.metaLabel}>人格</dt>
              <dd style={styles.metaValue}>{personaName}</dd>
            </div>
            <div style={styles.metaItem}>
              <dt style={styles.metaLabel}>生成时间</dt>
              <dd style={styles.metaValue}>{formatDate(plan.createdAt)}</dd>
            </div>
          </dl>
        </>
      ) : null}
      {plan ? (
        <div style={styles.actionRow}>
          {hasSession ? (
            <div style={styles.sessionStateCard}>
              <span style={styles.sessionStateLabel}>学习会话</span>
              <strong style={styles.sessionStateValue}>当前计划已连接章节会话</strong>
              <span style={styles.sessionHint}>可以直接前往下方继续提问。</span>
            </div>
          ) : (
            <button
              type="button"
              style={styles.primaryButton}
              onClick={onCreateSession}
              disabled={isBusy}
            >
              {isBusy ? "创建中..." : "为当前计划创建学习会话"}
            </button>
          )}
        </div>
      ) : null}
      {plan?.weeklyFocus.length ? (
        <section style={styles.sectionBlock}>
          <div style={styles.blockHeader}>
            <p style={styles.blockLabel}>本周重点</p>
            <span style={styles.blockCount}>{plan.weeklyFocus.length} 项</span>
          </div>
          <ol style={styles.orderedList}>
            {plan.weeklyFocus.map((focus, index) => (
              <li key={`${focus}-${index}`} style={styles.orderedItem}>
                <span style={styles.orderedIndex}>{String(index + 1).padStart(2, "0")}</span>
                <div style={styles.orderedBody}>
                  <strong style={styles.orderedTitle}>{focus}</strong>
                </div>
              </li>
            ))}
          </ol>
        </section>
      ) : null}
      <section style={styles.sectionBlock}>
        <div style={styles.blockHeader}>
          <p style={styles.blockLabel}>今日任务</p>
          <span style={styles.blockCount}>
            {plan?.todayTasks.length ?? 0} 项
          </span>
        </div>
        <ol style={styles.orderedList}>
          {(plan?.todayTasks.length ? plan.todayTasks : ["暂无今日任务。先上传教材并生成计划。"]).map((task, index) => (
            <li key={`${task}-${index}`} style={styles.orderedItem}>
              <span style={styles.orderedIndex}>{String(index + 1).padStart(2, "0")}</span>
              <div style={styles.orderedBody}>
                <p style={styles.taskText}>{task}</p>
              </div>
            </li>
          ))}
        </ol>
      </section>
      {plan?.schedule.length ? (
        <section style={styles.sectionBlock}>
          <div style={styles.blockHeader}>
            <p style={styles.blockLabel}>近期安排</p>
            <span style={styles.blockCount}>{Math.min(plan.schedule.length, 6)} 条</span>
          </div>
          <ol style={styles.timeline}>
            {plan.schedule.slice(0, 6).map((item) => (
              <li key={item.id} style={styles.timelineItem}>
                <div style={styles.timelineContent}>
                  <div style={styles.scheduleTopRow}>
                    <strong style={styles.scheduleTitle}>{item.title}</strong>
                    <span style={styles.scheduleTypeChip}>{formatActivityType(item.activityType)}</span>
                  </div>
                  <p style={styles.scheduleFocus}>{item.focus}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      ) : (
        <p style={styles.emptyHint}>计划生成成功后，这里会展开最近几次学习安排。</p>
      )}
    </article>
  );
}

const styles: Record<string, CSSProperties> = {
  panel: {
    padding: 24,
    borderRadius: 24,
    border: "1px solid var(--border)",
    background: "var(--panel-strong)",
    boxShadow: "var(--shadow)",
    backdropFilter: "blur(18px)",
    display: "grid",
    gap: 16
  },
  selectorSurface: {
    padding: 16,
    borderRadius: 16,
    background: "rgba(248,252,253,0.96)",
    border: "1px solid var(--border)",
    boxShadow: "inset 0 1px 0 rgba(255,255,255,0.6)"
  },
  selectorRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-end",
    gap: 14,
    flexWrap: "wrap"
  },
  selectorField: {
    display: "grid",
    gap: 8,
    flex: 1
  },
  selectorLabel: {
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.12em",
    textTransform: "uppercase",
    color: "var(--muted)"
  },
  selectWrap: {
    position: "relative"
  },
  select: {
    width: "100%",
    minHeight: 48,
    borderRadius: 12,
    border: "1px solid var(--border)",
    padding: "12px 42px 10px 12px",
    background: "rgba(255,255,255,0.96)",
    color: "var(--ink)",
    appearance: "none",
    boxShadow: "inset 0 1px 2px rgba(26, 53, 61, 0.08)"
  },
  selectArrow: {
    position: "absolute",
    right: 16,
    top: "50%",
    transform: "translateY(-50%)",
    color: "var(--muted)",
    pointerEvents: "none",
    fontSize: 16
  },
  selectorHint: {
    color: "var(--muted)",
    fontSize: 13,
    lineHeight: 1.5
  },
  refreshButton: {
    minHeight: 48,
    border: "1px solid rgba(13, 110, 114, 0.24)",
    borderRadius: 12,
    padding: "0 14px",
    background: "rgba(63, 140, 133, 0.1)",
    color: "var(--teal)",
    fontWeight: 700,
    cursor: "pointer",
    whiteSpace: "nowrap"
  },
  headerRow: {
    display: "flex",
    justifyContent: "space-between",
    gap: 16,
    alignItems: "flex-start",
    flexWrap: "wrap"
  },
  headerContent: {
    display: "grid",
    gap: 8
  },
  sectionLabel: {
    margin: 0,
    fontSize: 11,
    fontWeight: 700,
    textTransform: "uppercase",
    letterSpacing: "0.12em",
    color: "var(--muted)"
  },
  panelTitle: {
    margin: 0,
    fontSize: "clamp(1.35rem, 2.1vw, 1.9rem)",
    lineHeight: 1.3,
    letterSpacing: "-0.015em",
    fontFamily: "var(--font-display), sans-serif"
  },
  summaryCard: {
    display: "grid",
    gap: 8,
    padding: "16px",
    borderRadius: 14,
    background: "rgba(255,255,255,0.95)",
    border: "1px solid var(--border)",
    boxShadow: "var(--shadow-soft)"
  },
  summaryLabel: {
    margin: 0,
    color: "var(--muted)",
    fontSize: 12,
    fontWeight: 700,
    letterSpacing: "0.04em"
  },
  panelSummary: {
    margin: 0,
    maxWidth: 720,
    color: "var(--ink)",
    fontSize: 15,
    lineHeight: 1.7
  },
  positionBadge: {
    padding: "8px 12px",
    borderRadius: 12,
    background: "rgba(13, 110, 114, 0.1)",
    border: "1px solid rgba(13, 110, 114, 0.22)",
    color: "var(--accent)",
    fontSize: 13,
    fontWeight: 700,
    whiteSpace: "nowrap"
  },
  metaList: {
    margin: 0,
    padding: 0,
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
    gap: 12
  },
  metaItem: {
    margin: 0,
    padding: "14px",
    borderRadius: 12,
    background: "rgba(248, 252, 253, 0.96)",
    border: "1px solid var(--border)",
    display: "grid",
    gap: 6
  },
  metaLabel: {
    margin: 0,
    color: "var(--muted)",
    fontSize: 12,
    lineHeight: 1.4
  },
  metaValue: {
    margin: 0,
    fontSize: 15,
    lineHeight: 1.4
  },
  actionRow: {
    display: "flex",
    flexWrap: "wrap",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12
  },
  primaryButton: {
    border: 0,
    borderRadius: 12,
    minHeight: 44,
    padding: "0 16px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 700,
    boxShadow: "0 6px 14px rgba(13, 110, 114, 0.24)",
    cursor: "pointer"
  },
  sessionStateCard: {
    display: "grid",
    gap: 4,
    padding: "12px 14px",
    borderRadius: 12,
    background: "rgba(63, 140, 133, 0.1)",
    border: "1px solid rgba(13, 110, 114, 0.2)"
  },
  sessionStateLabel: {
    color: "var(--muted)",
    fontSize: 12
  },
  sessionStateValue: {
    fontSize: 15,
    lineHeight: 1.4
  },
  sessionHint: {
    color: "var(--teal)",
    fontSize: 13
  },
  sectionBlock: {
    display: "grid",
    gap: 12
  },
  blockHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12
  },
  blockLabel: {
    margin: 0,
    fontSize: 14,
    fontWeight: 700,
    letterSpacing: "0.02em"
  },
  blockCount: {
    padding: "6px 10px",
    borderRadius: 12,
    background: "rgba(16, 35, 40, 0.06)",
    color: "var(--muted)",
    fontSize: 12,
    whiteSpace: "nowrap"
  },
  orderedList: {
    listStyle: "none",
    margin: 0,
    padding: 0,
    display: "grid",
    gap: 12
  },
  orderedItem: {
    display: "grid",
    gridTemplateColumns: "44px minmax(0, 1fr)",
    gap: 14,
    alignItems: "flex-start",
    padding: 14,
    borderRadius: 12,
    background: "rgba(255,255,255,0.96)",
    border: "1px solid var(--border)",
    boxShadow: "var(--shadow-soft)"
  },
  orderedIndex: {
    width: 36,
    height: 36,
    borderRadius: 10,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "rgba(13, 110, 114, 0.14)",
    color: "var(--accent)",
    fontSize: 12,
    fontWeight: 700
  },
  orderedBody: {
    display: "grid",
    gap: 4,
    paddingTop: 4
  },
  orderedTitle: {
    fontSize: 15,
    lineHeight: 1.5
  },
  taskText: {
    margin: 0,
    fontSize: 15,
    lineHeight: 1.65
  },
  timeline: {
    listStyle: "none",
    margin: 0,
    padding: 0,
    display: "grid",
    gap: 12
  },
  timelineItem: {
    display: "grid",
    gap: 10,
    alignItems: "flex-start",
    padding: 14,
    borderRadius: 12,
    background: "rgba(255,255,255,0.96)",
    border: "1px solid var(--border)",
    boxShadow: "var(--shadow-soft)"
  },
  timelineContent: {
    display: "grid",
    gap: 8
  },
  scheduleTopRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "flex-start",
    gap: 12,
    flexWrap: "wrap"
  },
  scheduleTitle: {
    fontSize: 15,
    lineHeight: 1.4
  },
  scheduleTypeChip: {
    padding: "6px 10px",
    borderRadius: 10,
    background: "rgba(63, 140, 133, 0.12)",
    color: "var(--teal)",
    fontSize: 12,
    fontWeight: 700,
    whiteSpace: "nowrap"
  },
  scheduleFocus: {
    margin: 0,
    color: "var(--muted)",
    fontSize: 14,
    lineHeight: 1.6
  },
  emptyHint: {
    margin: 0,
    color: "var(--muted)",
    lineHeight: 1.6
  }
};

function formatActivityType(activityType: string) {
  if (activityType === "learn") {
    return "学习";
  }
  if (activityType === "review") {
    return "复习";
  }
  if (activityType === "practice") {
    return "练习";
  }
  return activityType;
}

function formatDate(value: string) {
  if (!value) {
    return "未知时间";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return date.toLocaleString("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  });
}

function resolveCourseTitle(courseTitle: string, documentTitle: string) {
  if (courseTitle.trim()) {
    return courseTitle.trim();
  }
  if (documentTitle.trim()) {
    return documentTitle.trim();
  }
  return "当前学习计划";
}
