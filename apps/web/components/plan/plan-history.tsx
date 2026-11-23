"use client";

import styles from "./plan-history.module.css";
import { useEffect, useRef, useState } from "react";

import { formatTimestamp } from "../../lib/format";
import type { PlanHistoryItem } from "../../lib/plan-panel-data";
import { MaterialIcon } from "../ui/material-icon";
import { useConfirm } from "../ui/confirm-provider";

interface PlanHistoryProps {
  items: PlanHistoryItem[];
  selectedPlanId: string;
  isRefreshing: boolean;
  isBusy: boolean;
  onSelect: (planId: string) => void;
  onRefresh: () => void;
  onDelete: (planId: string, expectedRevision: number) => Promise<boolean>;
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
  const heading = useRef<HTMLSpanElement>(null);
  const confirm = useConfirm();

  useEffect(() => {
    if (!selectedPlanId || items.length <= 1) {
      setIsExpanded(true);
    }
  }, [items.length, selectedPlanId]);

  async function requestDelete(item: PlanHistoryItem, trigger: HTMLButtonElement) {
    if (
      !(await confirm({
        title: "删除计划？",
        message:
          "将删除“" + (item.courseTitle || item.documentTitle) + "”。此操作不可撤销。",
        confirmLabel: "删除计划",
        danger: true,
        trigger,
        fallbackFocus: () => heading.current,
      }))
    )
      return;
    if (await onDelete(item.id, item.revision)) {
      // Do not steal focus from a user who moved elsewhere while deletion was pending.
      if (
        document.activeElement === document.body ||
        document.activeElement === trigger
      ) {
        heading.current?.focus({ preventScroll: true });
      }
    }
  }

  return (
    <section className={styles.wrap}>
      <div className={styles.headerRow}>
        <div className={styles.headerMeta}>
          <span ref={heading} tabIndex={-1} className={styles.label}>
            计划历史 {items.length ? `· ${items.length} 条` : ""}
          </span>
        </div>
        <div className={styles.headerActions}>
          <button
            type="button"
            className={styles.iconButton}
            onClick={onRefresh}
            disabled={isRefreshing || isBusy}
            aria-label={isRefreshing ? "刷新中" : "刷新计划历史"}
            title={isRefreshing ? "刷新中…" : "刷新"}
          >
            <MaterialIcon name={isRefreshing ? "hourglass_top" : "refresh"} size={16} />
          </button>
          {items.length ? (
            <button
              type="button"
              className={styles.iconButton}
              onClick={() => setIsExpanded((current) => !current)}
              disabled={isBusy}
              aria-expanded={isExpanded}
              aria-label={isExpanded ? "收起历史" : "展开历史"}
              title={isExpanded ? "收起历史" : "展开历史"}
            >
              <MaterialIcon name="expand_more" size={16} />
            </button>
          ) : null}
        </div>
      </div>

      {items.length ? (
        isExpanded ? (
          <div className={styles.list}>
            {items.map((item) => {
              const selected = item.id === selectedPlanId;
              return (
                <div key={item.id} className={styles.item} data-selected={selected}>
                  <div className={styles.itemTop}>
                    <div className={styles.itemBody}>
                      <strong className={styles.itemTitle}>
                        {item.courseTitle || item.documentTitle}
                      </strong>
                      <span className={styles.itemMeta}>
                        {item.documentTitle} · {item.personaName} ·{" "}
                        {formatTimestamp(item.createdAt, { style: "short" })}
                      </span>
                    </div>
                    {selected ? <span className={styles.badge}>当前</span> : null}
                  </div>
                  <p className={styles.overview}>{item.overview}</p>
                  <div className={styles.itemActions}>
                    <button
                      type="button"
                      className={styles.itemButton}
                      data-selected={selected}
                      onClick={() => {
                        if (!selected) onSelect(item.id);
                      }}
                      disabled={selected || isBusy}
                    >
                      <MaterialIcon name="event_note" size={16} />
                      <span>{selected ? "当前计划" : "查看计划"}</span>
                    </button>
                    <button
                      type="button"
                      className={styles.itemDeleteButton}
                      disabled={isBusy}
                      onClick={(event) => void requestDelete(item, event.currentTarget)}
                      aria-label={
                        "删除计划 " + (item.courseTitle || item.documentTitle)
                      }
                      title="删除计划"
                    >
                      <MaterialIcon name="delete" size={16} />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>
        ) : null
      ) : (
        <p className={styles.empty}>还没有历史计划。</p>
      )}
    </section>
  );
}
