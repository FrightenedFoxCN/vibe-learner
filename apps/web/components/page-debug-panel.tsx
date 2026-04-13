"use client";

import type { CSSProperties, ReactNode } from "react";

interface PageDebugPanelProps {
  title: string;
  subtitle?: string;
  error?: string;
  summary?: Array<{ label: string; value: string }>;
  details?: Array<{ title: string; value: unknown }>;
  children?: ReactNode;
}

export function PageDebugPanel({
  title,
  error = "",
  summary = [],
  details = [],
  children
}: PageDebugPanelProps) {
  return (
    <details style={styles.card} open>
      <summary style={styles.summary}>{title}</summary>
      {error ? <div style={styles.error}>{error}</div> : null}
      {summary.length ? (
        <div style={styles.summaryGrid}>
          {summary.map((item) => (
            <div key={item.label} style={styles.summaryItem}>
              <span style={styles.caption}>{item.label}</span>
              <strong style={styles.summaryValue}>{item.value}</strong>
            </div>
          ))}
        </div>
      ) : null}
      {details.length ? (
        <div style={styles.detailList}>
          {details.map((item) => (
            <div key={item.title} style={styles.detailCard}>
              <strong style={styles.detailTitle}>{item.title}</strong>
              <pre style={styles.pre}>{renderValue(item.value)}</pre>
            </div>
          ))}
        </div>
      ) : null}
      {children}
    </details>
  );
}

function renderValue(value: unknown) {
  if (typeof value === "string") {
    return value;
  }
  if (value === undefined) {
    return "undefined";
  }
  if (value === null) {
    return "null";
  }
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

const styles: Record<string, CSSProperties> = {
  card: {
    border: "1px solid var(--border)",
    background: "var(--bg)",
    borderRadius: 16,
    padding: "14px 16px"
  },
  summary: {
    cursor: "pointer",
    fontSize: 14,
    fontWeight: 700,
    color: "var(--ink)"
  },
  error: {
    marginTop: 12,
    padding: "10px 12px",
    borderRadius: 12,
    border: "1px solid color-mix(in srgb, var(--negative) 24%, var(--border))",
    background: "color-mix(in srgb, var(--negative) 10%, white)",
    color: "var(--negative)",
    fontSize: 13,
    lineHeight: 1.6,
    whiteSpace: "pre-wrap"
  },
  summaryGrid: {
    display: "grid",
    gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
    gap: 10,
    marginTop: 12
  },
  summaryItem: {
    display: "grid",
    gap: 4,
    padding: "10px 12px",
    borderRadius: 12,
    background: "var(--panel)"
  },
  summaryValue: {
    fontSize: 13,
    color: "var(--ink-2)",
    wordBreak: "break-word"
  },
  caption: {
    fontSize: 12,
    color: "var(--muted)"
  },
  detailList: {
    display: "grid",
    gap: 10,
    marginTop: 12
  },
  detailCard: {
    display: "grid",
    gap: 6,
    padding: "12px 14px",
    borderRadius: 12,
    background: "var(--panel)"
  },
  detailTitle: {
    fontSize: 13,
    color: "var(--ink)"
  },
  pre: {
    margin: 0,
    padding: "10px 12px",
    borderRadius: 10,
    background: "white",
    border: "1px solid var(--border)",
    whiteSpace: "pre-wrap",
    overflowX: "auto",
    fontSize: 11,
    lineHeight: 1.6,
    fontFamily: "var(--font-mono)"
  }
};
