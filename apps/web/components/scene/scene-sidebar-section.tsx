import type { ReactNode } from "react";
import { MaterialIcon } from "../ui/material-icon";
import css from "./scene-workspace.module.css";

export function SceneSidebarSection({
  title,
  collapsed,
  onToggle,
  children,
}: {
  title: string;
  collapsed: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <div
      className={`${css.panelSurface} shrink-0 overflow-hidden border border-border`}
    >
      <button
        type="button"
        className="flex min-h-11 w-full cursor-pointer items-center justify-between border-0 bg-transparent px-3 py-2.5 text-left"
        aria-expanded={!collapsed}
        onClick={onToggle}
      >
        <span className="text-[10px] font-bold tracking-[0.12em] text-muted uppercase">
          {title}
        </span>
        <span className="inline-flex items-center justify-center text-muted">
          <MaterialIcon name={collapsed ? "chevron_right" : "expand_more"} size={16} />
        </span>
      </button>
      {!collapsed ? (
        <div className="grid content-start gap-2 px-3 pb-3">{children}</div>
      ) : null}
    </div>
  );
}
