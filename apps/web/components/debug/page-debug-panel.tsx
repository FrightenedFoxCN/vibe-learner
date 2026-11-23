"use client";

import type { ReactNode } from "react";
import styles from "./page-debug-panel.module.css";

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
  children,
}: PageDebugPanelProps) {
  return (
    <details className={styles.card} open>
      <summary className={styles.summary}>{title}</summary>
      {error ? <div className={styles.error}>{error}</div> : null}
      {summary.length ? (
        <div className={styles.summaryGrid}>
          {summary.map((item) => (
            <div key={item.label} className={styles.summaryItem}>
              <span className={styles.caption}>{item.label}</span>
              <strong className={styles.summaryValue}>{item.value}</strong>
            </div>
          ))}
        </div>
      ) : null}
      {details.length ? (
        <div className={styles.detailList}>
          {details.map((item) => (
            <div key={item.title} className={styles.detailCard}>
              <strong className={styles.detailTitle}>{item.title}</strong>
              <pre className={styles.pre}>{renderValue(item.value)}</pre>
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
