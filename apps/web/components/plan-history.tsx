"use client";

import type { CSSProperties } from "react";
import type { DocumentRecord, LearningPlan, PersonaProfile } from "@gal-learner/shared";

interface PlanHistoryProps {
  plans: LearningPlan[];
  documents: DocumentRecord[];
  personas: PersonaProfile[];
  selectedPlanId: string;
  onSelect: (planId: string) => void;
}

export function PlanHistory({
  plans,
  documents,
  personas,
  selectedPlanId,
  onSelect
}: PlanHistoryProps) {
  return (
    <article style={styles.panel}>
      <div style={styles.headerRow}>
        <div>
          <p style={styles.sectionLabel}>历史计划</p>
          <h2 style={styles.title}>已生成的学习计划</h2>
        </div>
        <span style={styles.count}>{plans.length} 条</span>
      </div>
      {plans.length ? (
        <div style={styles.list}>
          {plans.map((plan) => {
            const document = documents.find((item) => item.id === plan.documentId);
            const persona = personas.find((item) => item.id === plan.personaId);
            const selected = plan.id === selectedPlanId;
            return (
              <button
                key={plan.id}
                type="button"
                style={{
                  ...styles.item,
                  ...(selected ? styles.itemActive : {})
                }}
                onClick={() => onSelect(plan.id)}
              >
                <strong>{document?.title ?? plan.documentId}</strong>
                <span>
                  {persona?.name ?? plan.personaId} · 截止 {plan.deadline} · {formatDate(plan.createdAt)}
                </span>
                <p style={styles.overview}>{plan.overview}</p>
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
