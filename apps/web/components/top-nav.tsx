"use client";

import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

import { BrandMark } from "./brand-mark";
import { MaterialIcon, type MaterialIconName } from "./material-icon";
import { AppLink, type AppRoutePath } from "../lib/app-navigation";
import {
  APP_NAV_COLLAPSED_STORAGE_KEY,
  BROWSER_VIEW_TOGGLE_NAV_EVENT,
  readStoredBoolean,
  writeStoredBoolean
} from "../lib/view-preferences";

interface TopNavProps {
  currentPath: AppRoutePath;
}

const NAV_ITEMS: Array<{
  href: AppRoutePath;
  label: string;
  icon: MaterialIconName;
}> = [
  { href: "/", label: "导航首页", icon: "home" },
  { href: "/plan", label: "计划生成", icon: "event_note" },
  { href: "/study", label: "章节对话", icon: "forum" },
  { href: "/persona-spectrum", label: "人格色谱", icon: "psychology_alt" },
  { href: "/scene-setup", label: "场景搭建", icon: "account_tree" },
  { href: "/sensory-tools", label: "感官工具", icon: "tune" },
  { href: "/settings", label: "统一设置", icon: "settings" },
  { href: "/model-usage", label: "用量审计", icon: "bar_chart" },
];

export function TopNav({ currentPath }: TopNavProps) {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    setCollapsed(readStoredBoolean(APP_NAV_COLLAPSED_STORAGE_KEY));
  }, []);

  useEffect(() => {
    const handleToggle = () => {
      setCollapsed((value) => !value);
    };
    window.addEventListener(BROWSER_VIEW_TOGGLE_NAV_EVENT, handleToggle);
    return () => {
      window.removeEventListener(BROWSER_VIEW_TOGGLE_NAV_EVENT, handleToggle);
    };
  }, []);

  useEffect(() => {
    const width = collapsed ? "56px" : "200px";
    document.documentElement.style.setProperty("--app-nav-width", width);
    writeStoredBoolean(APP_NAV_COLLAPSED_STORAGE_KEY, collapsed);
  }, [collapsed]);

  return (
    <aside className="app-side-nav" style={styles.aside} aria-label="Primary navigation">
      <div className="app-nav-brand-row" style={styles.topRow}>
        <div style={styles.brandMark}>
          <BrandMark size={28} />
        </div>
        {!collapsed ? <span style={styles.brandName}>Vibe Learner</span> : null}
      </div>

      <nav className="app-nav-links" style={styles.nav}>
        {NAV_ITEMS.map((item) => {
          const active = item.href === currentPath;
          return (
            <AppLink
              key={item.href}
              path={item.href}
              className={active ? "app-nav-link--active" : "app-nav-link"}
              style={collapsed ? styles.linkCollapsed : undefined}
              title={item.label}
            >
              <MaterialIcon name={item.icon} size={18} />
              {!collapsed ? <span>{item.label}</span> : null}
            </AppLink>
          );
        })}
      </nav>

      <div style={{ flex: 1 }} />

      <button
        type="button"
        className="app-nav-collapse-btn"
        style={collapsed ? styles.toggleCollapsed : styles.toggle}
        onClick={() => setCollapsed((value) => !value)}
        aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
        title={collapsed ? "展开侧栏" : "收起侧栏"}
      >
        {collapsed ? (
          <MaterialIcon name="chevron_right" size={18} />
        ) : (
          <>
            <MaterialIcon name="chevron_left" size={18} />
            <span>收起</span>
          </>
        )}
      </button>
    </aside>
  );
}

const toggleBase: CSSProperties = {
  border: "none",
  borderTop: "1px solid var(--border)",
  background: "transparent",
  height: 44,
  cursor: "pointer",
  color: "var(--muted)",
  fontSize: 13,
  display: "flex",
  alignItems: "center",
  flexShrink: 0,
  transition: "color 100ms",
  width: "100%",
};

const styles: Record<string, CSSProperties> = {
  aside: {
    position: "fixed",
    left: 0,
    top: 0,
    bottom: 0,
    width: "var(--app-nav-width)",
    borderRight: "1px solid var(--border)",
    background: "var(--bg)",
    zIndex: 40,
    display: "flex",
    flexDirection: "column",
    transition: "width 200ms ease",
    overflow: "hidden",
  },
  topRow: {
    display: "flex",
    alignItems: "center",
    gap: 10,
    padding: "14px 14px 12px",
    borderBottom: "1px solid var(--border)",
    flexShrink: 0,
    overflow: "hidden",
  },
  brandMark: {
    width: 28,
    height: 28,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  brandName: {
    color: "var(--ink)",
    fontSize: 13,
    fontWeight: 600,
    letterSpacing: "0.01em",
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
  },
  nav: {
    display: "flex",
    flexDirection: "column",
    gap: 0,
    flexShrink: 0,
    paddingTop: 4,
  },
  linkCollapsed: {
    justifyContent: "center",
    padding: "0",
  },
  toggle: {
    ...toggleBase,
    padding: "0 14px",
    gap: 8,
  },
  toggleCollapsed: {
    ...toggleBase,
    justifyContent: "center",
  },
};
