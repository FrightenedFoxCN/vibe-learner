import type { ReactNode } from "react";

import { Badge } from "../ui/badge";
import styles from "./settings-ui.module.css";

export function SettingsPanel({ children }: { children: ReactNode }) {
  return (
    <section className="grid min-w-0 gap-3 border border-solid border-border bg-panel p-4.5">
      {children}
    </section>
  );
}

export function SettingsField({
  label,
  children,
  compact = false,
}: {
  label: string;
  children: ReactNode;
  compact?: boolean;
}) {
  return (
    <label
      className={[
        "grid min-w-0 gap-1.5 text-sm",
        styles.field,
        compact ? "w-full max-w-[17.5rem]" : undefined,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <span className="text-[11px] font-semibold tracking-wider text-muted uppercase">
        {label}
      </span>
      {children}
    </label>
  );
}

export function SettingsToggle({ children }: { children: ReactNode }) {
  return (
    <label
      className={`${styles.toggle} flex min-h-11 cursor-pointer items-center gap-2 text-sm text-ink`}
    >
      {children}
    </label>
  );
}

export function StatusBadge({
  label,
  tone,
}: {
  label: string;
  tone: "positive" | "negative" | "muted";
}) {
  return <Badge variant={tone === "muted" ? "neutral" : tone}>{label}</Badge>;
}
