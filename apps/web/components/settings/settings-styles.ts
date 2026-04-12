import type { CSSProperties } from "react";

export const settingsStyles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    maxWidth: 1160,
    margin: "0 auto",
    padding: "38px 32px 64px",
    display: "grid",
    gap: 20,
    alignContent: "start"
  },
  header: {
    display: "grid",
    gap: 10
  },
  title: {
    margin: 0,
    fontSize: 28,
    fontWeight: 800,
    letterSpacing: "-0.02em",
    lineHeight: 1.2,
    color: "var(--ink)"
  },
  subtitle: {
    margin: 0,
    fontSize: 14,
    color: "var(--muted)",
    lineHeight: 1.7,
    maxWidth: 760
  },
  loading: {
    fontSize: 14,
    color: "var(--muted)"
  },
  error: {
    background: "color-mix(in srgb, var(--negative) 8%, white)",
    border: "1px solid color-mix(in srgb, var(--negative) 35%, var(--border))",
    color: "var(--negative)",
    padding: "10px 12px",
    fontSize: 13
  },
  form: {
    display: "grid",
    gap: 16
  },
  card: {
    border: "1px solid var(--border)",
    background: "var(--panel)",
    padding: "18px 18px 16px",
    display: "grid",
    gap: 12
  },
  cardTitle: {
    margin: 0,
    fontSize: 18,
    color: "var(--ink)"
  },
  cardDescription: {
    margin: 0,
    fontSize: 13,
    lineHeight: 1.7,
    color: "var(--muted)"
  },
  subCard: {
    border: "1px solid var(--border)",
    background: "var(--bg)",
    padding: "14px 14px 12px",
    display: "grid",
    gap: 10
  },
  subCardHeader: {
    display: "grid",
    gap: 4
  },
  subTitle: {
    margin: 0,
    fontSize: 15,
    color: "var(--ink-2)"
  },
  tip: {
    margin: 0,
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.6
  },
  field: {
    display: "grid",
    gap: 6,
    fontSize: 13
  },
  label: {
    fontSize: 11,
    fontWeight: 600,
    textTransform: "uppercase",
    letterSpacing: "0.07em",
    color: "var(--muted)"
  },
  fieldHint: {
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.5
  },
  probeRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    flexWrap: "wrap"
  },
  probeHint: {
    fontSize: 12,
    color: "var(--muted)"
  },
  advancedContent: {
    display: "grid",
    gap: 12
  },
  toggleGrid: {
    display: "grid",
    gap: 10,
    gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))"
  },
  switchField: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 14,
    color: "var(--ink)"
  },
  checkboxField: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    fontSize: 13,
    color: "var(--ink)"
  },
  checkboxLabel: {
    color: "var(--ink)",
    fontSize: 13
  },
  grid2: {
    display: "grid",
    gap: 12,
    gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))"
  },
  secondaryBtn: {
    height: 28,
    border: "1px solid var(--border)",
    padding: "0 12px",
    background: "transparent",
    color: "var(--muted)",
    fontSize: 12,
    cursor: "pointer",
    fontWeight: 600,
    display: "inline-flex",
    alignItems: "center"
  },
  ghostBtn: {
    height: 28,
    border: "1px dashed var(--border)",
    padding: "0 12px",
    background: "transparent",
    color: "var(--ink-2)",
    fontSize: 12,
    cursor: "pointer",
    fontWeight: 600,
    display: "inline-flex",
    alignItems: "center"
  },
  statusBar: {
    border: "1px solid var(--border)",
    background: "color-mix(in srgb, var(--panel) 86%, white)",
    padding: "12px 14px",
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
    flexWrap: "wrap"
  },
  statusMain: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    flexWrap: "wrap"
  },
  statusText: {
    fontSize: 13,
    color: "var(--ink)"
  },
  updatedAt: {
    fontSize: 12,
    color: "var(--muted)"
  },
  badge: {
    display: "inline-flex",
    alignItems: "center",
    padding: "3px 8px",
    fontSize: 11,
    fontWeight: 700,
    letterSpacing: "0.03em",
    border: "1px solid var(--border)",
    textTransform: "uppercase"
  },
  badgePositive: {
    color: "var(--positive)",
    borderColor: "color-mix(in srgb, var(--positive) 30%, var(--border))",
    background: "color-mix(in srgb, var(--positive) 8%, white)"
  },
  badgeNegative: {
    color: "var(--negative)",
    borderColor: "color-mix(in srgb, var(--negative) 30%, var(--border))",
    background: "color-mix(in srgb, var(--negative) 8%, white)"
  },
  badgeMuted: {
    color: "var(--muted)",
    borderColor: "var(--border)",
    background: "transparent"
  },
  auditGrid: {
    display: "grid",
    gap: 12,
    gridTemplateColumns: "repeat(auto-fit, minmax(250px, 1fr))"
  },
  auditCard: {
    border: "1px solid var(--border)",
    background: "var(--bg)",
    padding: "14px",
    display: "grid",
    gap: 10,
    alignContent: "start"
  },
  auditHeader: {
    display: "grid",
    gap: 4
  },
  auditTitle: {
    margin: 0,
    fontSize: 15,
    color: "var(--ink)"
  },
  auditDescription: {
    margin: 0,
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.6
  },
  auditModel: {
    fontSize: 13,
    color: "var(--ink-2)",
    lineHeight: 1.6
  },
  capabilityStack: {
    display: "grid",
    gap: 6
  },
  capabilityRow: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    flexWrap: "wrap"
  },
  capabilityNote: {
    margin: 0,
    fontSize: 12,
    color: "var(--muted)",
    lineHeight: 1.6
  },
  ruleText: {
    fontSize: 12,
    color: "var(--ink-2)"
  }
};
