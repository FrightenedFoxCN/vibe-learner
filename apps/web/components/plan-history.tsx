"use client";

import type { CSSProperties } from "react";
import type { PlanHistoryItem } from "../lib/plan-panel-data";

interface PlanHistoryProps {
  items: PlanHistoryItem[];
  selectedPlanId: string;
  isRefreshing: boolean;
  isBusy: boolean;
  onSelect: (planId: string) => void;
  onRefresh: () => void;
  onDelete: (planId: string) => void;
}

export function PlanHistory({
  items,
  selectedPlanId,
  isRefreshing,
  isBusy,
  onSelect,
  onRefresh,
  onDelete
}: PlanHistoryProps) {
  return (
    <section style={styles.wrap}>
      <div style={styles.headerRow}>
        <div style={styles.headerMeta}>
          <span style={styles.label}>计划历史 {items.length ? `· ${items.length} 条` : ""}</span>
          <span style={styles.subtle}>切换查看旧计划，或直接删除不再需要的版本。</span>
        </div>
        <button
          type="button"
          style={styles.ghostButton}
          onClick={onRefresh}
          disabled={isRefreshing || isBusy}
        >
          {isRefreshing ? "刷新中…" : "刷新"}
        </button>
      </div>
      {items.length ? (
        <div style={styles.list}>
          {items.map((item) => {
            const selected = item.id === selectedPlanId;
            return (
              <div
                key={item.id}
                style={{ ...styles.item, ...(selected ? styles.itemActive : {}) }}
              >
                <div style={styles.itemTop}>
                  <div style={styles.itemBody}>
                    <strong style={styles.itemTitle}>{item.courseTitle || item.documentTitle}</strong>
                    <span style={styles.itemMeta}>
                      {item.documentTitle} · {item.personaName} · {formatDate(item.createdAt)}
                    </span>
                  </div>
                  {selected ? <span style={styles.badge}>当前</span> : null}
                </div>
                <p style={styles.overview}>{item.overview}</p>
                <div style={styles.itemActions}>
                  <button
                    type="button"
                    style={{
                      ...styles.itemButton,
                      ...(selected ? styles.itemButtonSelected : {})
                    }}
                    onClick={() => { if (!selected) onSelect(item.id); }}
                    disabled={selected || isBusy}
                  >
                    {selected ? "当前计划" : "查看计划"}
                  </button>
                  <button
                    type="button"
                    style={{
                      ...styles.itemDeleteButton,
                      ...(isBusy ? styles.buttonDisabled : {})
                    }}
                    disabled={isBusy}
                    onClick={() => {
                      if (window.confirm(`确认删除计划“${item.courseTitle || item.documentTitle}”？`)) {
                        onDelete(item.id);
                      }
                    }}
                  >
                    删除
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      ) : (
        <p style={styles.empty}>暂无计划历史。上传教材后会自动生成第一版计划。</p>
      )}
    </section>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    display: "grid",
    gap: 0,
    paddingTop: 4,
    borderTop: "1px solid var(--border)"
  },
  headerRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    padding: "16px 0"
  },
  headerMeta: {
    display: "grid",
    gap: 2
  },
  label: {
    fontSize: 13,
    fontWeight: 700,
    color: "var(--ink)"
  },
  subtle: {
    fontSize: 12,
    color: "var(--muted)"
  },
  ghostButton: {
    minHeight: 30,
    border: "1px solid var(--border)",
    padding: "0 10px",
    background: "transparent",
    color: "var(--muted)",
    fontSize: 12,
    cursor: "pointer"
  },
  list: {
    display: "grid",
    gap: 12
  },
  item: {
    display: "grid",
    gap: 10,
    padding: "14px 16px",
    border: "1px solid var(--border)",
    background: "white"
  },
  itemActive: {
    background: "var(--panel)"
  },
  itemTop: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 10
  },
  itemBody: {
    display: "grid",
    gap: 4
  },
  itemTitle: {
    fontSize: 14,
    color: "var(--ink)"
  },
  itemMeta: {
    fontSize: 12,
    color: "var(--muted)"
  },
  badge: {
    fontSize: 11,
    color: "var(--accent)",
    border: "1px solid var(--border)",
    padding: "2px 6px",
    whiteSpace: "nowrap"
  },
  overview: {
    margin: 0,
    color: "var(--muted)",
    lineHeight: 1.6,
    fontSize: 13
  },
  itemActions: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8
  },
  itemButton: {
    minHeight: 32,
    border: "1px solid var(--border)",
    padding: "0 12px",
    background: "white",
    color: "var(--ink)",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer"
  },
  itemButtonSelected: {
    background: "var(--accent-soft)",
    color: "var(--accent)"
  },
  itemDeleteButton: {
    minHeight: 32,
    border: "1px solid color-mix(in srgb, var(--negative) 28%, var(--border))",
    padding: "0 12px",
    background: "white",
    color: "var(--negative)",
    fontSize: 12,
    fontWeight: 600,
    cursor: "pointer"
  },
  buttonDisabled: {
    opacity: 0.45,
    cursor: "not-allowed"
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
