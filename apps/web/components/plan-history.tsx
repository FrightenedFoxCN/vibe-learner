"use client";

import type { CSSProperties } from "react";
import type { PlanHistoryItem } from "../lib/plan-panel-data";

interface PlanHistoryProps {
  items: PlanHistoryItem[];
  selectedPlanId: string;
  isRefreshing: boolean;
  onSelect: (planId: string) => void;
  onRefresh: () => void;
}

export function PlanHistory({
  items,
  selectedPlanId,
  isRefreshing,
  onSelect,
  onRefresh
}: PlanHistoryProps) {
  return (
    <article style={styles.panel}>
      <div style={styles.headerRow}>
        <div>
          <p style={styles.sectionLabel}>历史计划</p>
          <h2 style={styles.title}>已生成的学习计划</h2>
        </div>
        <div style={styles.headerActions}>
          <button
            type="button"
            style={styles.refreshButton}
            onClick={onRefresh}
            disabled={isRefreshing}
          >
            {isRefreshing ? "刷新中..." : "刷新快照"}
          </button>
          <span style={styles.count}>{items.length} 条</span>
        </div>
      </div>
      {items.length ? (
        <div style={styles.list}>
          {items.map((item) => {
            const selected = item.id === selectedPlanId;
            return (
              <button
                key={item.id}
                type="button"
                style={{
                  ...styles.item,
                  ...(selected ? styles.itemActive : {})
                }}
                onClick={() => {
                  if (!selected) {
                    onSelect(item.id);
                  }
                }}
              >
                <div style={styles.itemHeader}>
                  <strong>{item.documentTitle}</strong>
                  {selected ? <span style={styles.selectedBadge}>当前查看</span> : null}
                </div>
                <span>
                  {item.personaName} · {formatDate(item.createdAt)}
                </span>
                <p style={styles.overview}>{item.overview}</p>
              </button>
            );
          })}
        </div>
      ) : (
        <p style={styles.empty}>还没有历史学习计划。可以先上传教材，或在 `/debug` 中流式生成一份计划。</p>
      )}
    </article>
  );
}

const styles: Record<string, CSSProperties> = {
  panel: {
    padding: 24,
    borderRadius: 28,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    boxShadow: "var(--shadow)"
  },
  headerRow: {
    display: "flex",
    justifyContent: "space-between",
    gap: 12,
    alignItems: "flex-start"
  },
  headerActions: {
    display: "flex",
    alignItems: "center",
    gap: 10
  },
  sectionLabel: {
    margin: 0,
    fontSize: 12,
    textTransform: "uppercase",
    letterSpacing: "0.12em",
    color: "var(--muted)"
  },
  title: {
    margin: "8px 0 0",
    fontSize: 28,
    fontFamily: "var(--font-display), sans-serif"
  },
  count: {
    padding: "8px 12px",
    borderRadius: 999,
    background: "rgba(63, 140, 133, 0.12)",
    border: "1px solid rgba(63, 140, 133, 0.18)",
    fontSize: 13
  },
  refreshButton: {
    border: "1px solid var(--border)",
    borderRadius: 999,
    padding: "8px 12px",
    background: "rgba(255,255,255,0.82)",
    cursor: "pointer"
  },
  list: {
    display: "grid",
    gap: 10,
    marginTop: 16
  },
  item: {
    textAlign: "left",
    display: "grid",
    gap: 6,
    padding: 16,
    borderRadius: 18,
    border: "1px solid var(--border)",
    background: "rgba(255,255,255,0.76)",
    cursor: "pointer"
  },
  itemActive: {
    border: "1px solid var(--accent)",
    background: "var(--accent-soft)"
  },
  itemHeader: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 12
  },
  selectedBadge: {
    padding: "4px 10px",
    borderRadius: 999,
    background: "rgba(63, 140, 133, 0.14)",
    fontSize: 12,
    whiteSpace: "nowrap"
  },
  overview: {
    margin: 0,
    color: "var(--muted)",
    lineHeight: 1.6
  },
  empty: {
    margin: "16px 0 0",
    color: "var(--muted)",
    lineHeight: 1.6
  }
};

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
