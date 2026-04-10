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
    <div style={styles.wrap}>
      <div style={styles.headerRow}>
        <span style={styles.label}>历史计划 {items.length ? `· ${items.length} 条` : ""}</span>
        <button
          type="button"
          style={styles.ghostButton}
          onClick={onRefresh}
          disabled={isRefreshing}
        >
          {isRefreshing ? "刷新中…" : "刷新"}
        </button>
      </div>
      {items.length ? (
        <div style={styles.list}>
          {items.map((item) => {
            const selected = item.id === selectedPlanId;
            return (
              <button
                key={item.id}
                type="button"
                style={{ ...styles.item, ...(selected ? styles.itemActive : {}) }}
                onClick={() => { if (!selected) onSelect(item.id); }}
              >
                <div style={styles.itemTop}>
                  <strong style={styles.itemTitle}>{item.documentTitle}</strong>
                  {selected ? <span style={styles.badge}>当前</span> : null}
                </div>
                <span style={styles.itemMeta}>
                  {item.personaName} · {formatDate(item.createdAt)}
                </span>
                <p style={styles.overview}>{item.overview}</p>
              </button>
            );
          })}
        </div>
      ) : (
        <p style={styles.empty}>暂无历史计划。上传教材后自动生成。</p>
      )}
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    display: "grid",
    gap: 0
  },
  headerRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    padding: "12px 0",
    borderBottom: "1px solid var(--border)"
  },
  label: {
    fontSize: 13,
    fontWeight: 700,
    color: "var(--ink)"
  },
  ghostButton: {
    height: 30,
    border: "1px solid var(--border)",
    borderRadius: 3,
    padding: "0 10px",
    background: "transparent",
    color: "var(--muted)",
    fontSize: 12,
    cursor: "pointer"
  },
  list: {
    display: "grid",
    gap: 0
  },
  item: {
    textAlign: "left",
    display: "grid",
    gap: 4,
    padding: "12px 0",
    borderBottom: "1px solid var(--border)",
    background: "transparent",
    border: "none",
    borderBottomStyle: "solid",
    borderBottomWidth: 1,
    borderBottomColor: "var(--border)",
    cursor: "pointer",
    width: "100%"
  },
  itemActive: {
    background: "var(--panel)"
  },
  itemTop: {
    display: "flex",
    alignItems: "center",
    gap: 8
  },
  itemTitle: {
    fontSize: 14,
    color: "var(--ink)"
  },
  badge: {
    fontSize: 11,
    color: "var(--accent)",
    border: "1px solid var(--border)",
    borderRadius: 3,
    padding: "1px 6px"
  },
  itemMeta: {
    fontSize: 12,
    color: "var(--muted)"
  },
  overview: {
    margin: 0,
    color: "var(--muted)",
    lineHeight: 1.6,
    fontSize: 13
  },
  empty: {
    margin: "12px 0 0",
    color: "var(--muted)",
    lineHeight: 1.6,
    fontSize: 13
  }
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
