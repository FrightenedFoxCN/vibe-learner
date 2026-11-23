import type { ReactNode } from "react";
import { MaterialIcon } from "../ui/material-icon";
import styles from "./persona-workspace.module.css";

export function PersonaSidebarSection({
  title,
  expanded,
  onToggle,
  children,
}: {
  title: string;
  expanded: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div className={styles.sidebarSection}>
      <button
        type="button"
        className="flex w-full cursor-pointer items-center justify-between border-none bg-transparent px-3 py-2.5 text-left"
        aria-expanded={expanded}
        onClick={onToggle}
      >
        <span className="text-[10px] font-bold tracking-[0.12em] text-muted uppercase">
          {title}
        </span>
        <span className="inline-flex items-center text-muted">
          <MaterialIcon name={expanded ? "expand_more" : "chevron_right"} size={16} />
        </span>
      </button>
      {expanded ? (
        <div className="grid content-start gap-2 px-3 pb-3">{children}</div>
      ) : null}
    </div>
  );
}
