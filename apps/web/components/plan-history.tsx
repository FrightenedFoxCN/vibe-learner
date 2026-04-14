"use client";

import type { CSSProperties } from "react";
import { useEffect, useState } from "react";

import type { PlanHistoryItem } from "../lib/plan-panel-data";
import { MaterialIcon } from "./material-icon";

interface PlanHistoryProps {
  items: PlanHistoryItem[];
  selectedPlanId: string;
  isRefreshing: boolean;
  isBusy: boolean;
  onSelect: (planId: string) => void;
  onRefresh: () => void;
  onDelete: (planId: string) => void | Promise<void>;
}

export function PlanHistory({
  items,
  selectedPlanId,
  isRefreshing,
  isBusy,
  onSelect,
  onRefresh,
  onDelete,
}: PlanHistoryProps) {
  const [isExpanded, setIsExpanded] = useState(items.length <= 1);
  const [pendingDeletePlanId, setPendingDeletePlanId] = useState("");

  useEffect(() => {
    if (!selectedPlanId || items.length <= 1) {
      setIsExpanded(true);
    }
  }, [items.length, selectedPlanId]);

  useEffect(() => {
    if (!pendingDeletePlanId) {
      return;
    }
    if (!items.some((item) => item.id === pendingDeletePlanId)) {
      setPendingDeletePlanId("");
    }
  }, [items, pendingDeletePlanId]);

  return (
    <section style={styles.wrap}>
      <div style={styles.headerRow}>
        <div style={styles.headerMeta}>
          <span style={styles.label}>计划历史 {items.length ? `· ${items.length} 条` : ""}</span>
        </div>
        <div style={styles.headerActions}>
          <button
            type="button"
            style={styles.iconButton}
            onClick={onRefresh}
            disabled={isRefreshing || isBusy}
            aria-label={isRefreshing ? "刷新中" : "刷新计划历史"}
            title={isRefreshing ? "刷新中…" : "刷新"}
          >
            <MaterialIcon name="replay" size={16} />
          </button>
          {items.length ? (
            <button
              type="button"
              style={styles.iconButton}
              onClick={() => setIsExpanded((current) => !current)}
              disabled={isBusy}
              aria-label={isExpanded ? "收起历史" : "展开历史"}
              title={isExpanded ? "收起历史" : "展开历史"}
            >
              <MaterialIcon
                name="expand_more"
                size={16}
                style={{ transform: isExpanded ? "rotate(180deg)" : "none" }}
              />
            </button>
          ) : null}
        </div>
      </div>

      {items.length ? (
        isExpanded ? (
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
                        ...(selected ? styles.itemButtonSelected : {}),
                      }}
                      onClick={() => { if (!selected) onSelect(item.id); }}
                      disabled={selected || isBusy}
                    >
                      <MaterialIcon name="description" size={16} />
                      <span>{selected ? "当前计划" : "查看计划"}</span>
                    </button>
                    {pendingDeletePlanId === item.id ? (
                      <>
                        <button
                          type="button"
                          style={{
                            ...styles.confirmDeleteButton,
                            ...(isBusy ? styles.buttonDisabled : {}),
                          }}
                          disabled={isBusy}
                          onClick={async () => {
                            await onDelete(item.id);
                            setPendingDeletePlanId("");
                          }}
                        >
                          确认删除
                        </button>
                        <button
                          type="button"
                          style={{
                            ...styles.itemButton,
                            ...(isBusy ? styles.buttonDisabled : {}),
                          }}
                          disabled={isBusy}
                          onClick={() => setPendingDeletePlanId("")}
                        >
                          取消
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        style={{
                          ...styles.itemDeleteButton,
                          ...(isBusy ? styles.buttonDisabled : {}),
                        }}
                        disabled={isBusy}
                        onClick={() => setPendingDeletePlanId(item.id)}
                        aria-label={`删除计划 ${item.courseTitle || item.documentTitle}`}
                        title="删除计划"
                      >
                        <MaterialIcon name="delete" size={16} />
                      </button>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        ) : null
      ) : (
        <p style={styles.empty}>还没有历史计划。</p>
      )}
    </section>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    display: "grid",
    gap: 12,
    paddingTop: 16,
    borderTop: "1px solid color-mix(in srgb, var(--border) 76%, white)",
  },
  headerRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  headerMeta: {
    display: "flex",
    alignItems: "center",
  },
  label: {
    fontSize: 10,
    fontWeight: 700,
    letterSpacing: "0.12em",
    textTransform: "uppercase",
    color: "var(--muted)",
  },
  headerActions: {
    display: "flex",
    alignItems: "center",
    gap: 8,
  },
  iconButton: {
    width: 30,
    height: 30,
    border: "none",
    padding: 0,
    background: "color-mix(in srgb, white 70%, var(--surface))",
    color: "var(--ink-2)",
    fontSize: 11,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  },
  list: {
    display: "grid",
    gap: 10,
  },
  item: {
    display: "grid",
    gap: 10,
    padding: "14px 16px",
    border: "1px solid color-mix(in srgb, var(--border) 72%, white)",
    background: "color-mix(in srgb, white 84%, var(--surface))",
  },
  itemActive: {
    borderColor: "color-mix(in srgb, var(--accent) 20%, var(--border))",
    background: "color-mix(in srgb, white 74%, var(--accent-soft))",
  },
  itemTop: {
    display: "flex",
    alignItems: "flex-start",
    justifyContent: "space-between",
    gap: 10,
  },
  itemBody: {
    display: "grid",
    gap: 4,
    minWidth: 0,
  },
  itemTitle: {
    fontSize: 15,
    fontWeight: 600,
    color: "var(--ink)",
  },
  itemMeta: {
    fontSize: 11,
    color: "var(--muted)",
  },
  badge: {
    fontSize: 10,
    color: "var(--accent)",
    border: "none",
    background: "color-mix(in srgb, white 68%, var(--accent-soft))",
    padding: "2px 6px",
    whiteSpace: "nowrap",
  },
  overview: {
    margin: 0,
    color: "var(--muted)",
    lineHeight: 1.6,
    fontSize: 14,
    display: "-webkit-box",
    WebkitLineClamp: 2,
    WebkitBoxOrient: "vertical",
    overflow: "hidden",
  },
  itemActions: {
    display: "flex",
    flexWrap: "wrap",
    gap: 8,
  },
  itemButton: {
    minHeight: 30,
    border: "none",
    padding: "0 10px",
    background: "color-mix(in srgb, white 70%, var(--surface))",
    color: "var(--ink)",
    fontSize: 11,
    fontWeight: 600,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    gap: 6,
  },
  itemButtonSelected: {
    background: "color-mix(in srgb, white 68%, var(--accent-soft))",
    color: "var(--accent)",
  },
  itemDeleteButton: {
    width: 30,
    height: 30,
    border: "none",
    padding: 0,
    background: "color-mix(in srgb, white 84%, var(--negative) 16%)",
    color: "var(--negative)",
    fontSize: 11,
    fontWeight: 600,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  },
  confirmDeleteButton: {
    minHeight: 30,
    border: "none",
    padding: "0 10px",
    background: "color-mix(in srgb, white 84%, var(--negative) 16%)",
    color: "var(--negative)",
    fontSize: 11,
    fontWeight: 700,
    cursor: "pointer",
    display: "inline-flex",
    alignItems: "center",
  },
  buttonDisabled: {
    opacity: 0.45,
    cursor: "not-allowed",
  },
  empty: {
    margin: 0,
    color: "var(--muted)",
    lineHeight: 1.6,
    fontSize: 14,
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
    minute: "2-digit",
  });
}
