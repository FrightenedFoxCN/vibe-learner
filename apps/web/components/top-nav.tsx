"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { CSSProperties } from "react";

interface TopNavProps {
  currentPath: "/" | "/plan" | "/study" | "/persona-spectrum" | "/debug";
}

const NAV_ITEMS: Array<{ href: TopNavProps["currentPath"]; label: string }> = [
  { href: "/", label: "导航首页" },
  { href: "/plan", label: "计划生成" },
  { href: "/study", label: "章节对话" },
  { href: "/persona-spectrum", label: "人格色谱" },
  { href: "/debug", label: "调试后台" },
];

export function TopNav({ currentPath }: TopNavProps) {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const saved = window.localStorage.getItem("vibe-nav-collapsed");
    if (saved === "1") {
      setCollapsed(true);
    }
  }, []);

  useEffect(() => {
    const width = collapsed ? "64px" : "220px";
    document.documentElement.style.setProperty("--app-nav-width", width);
    window.localStorage.setItem("vibe-nav-collapsed", collapsed ? "1" : "0");
  }, [collapsed]);

  return (
    <aside className="app-side-nav" style={styles.aside} aria-label="Primary navigation">
      <div className="app-nav-brand-row" style={styles.topRow}>
        <div style={collapsed ? styles.brandCollapsed : styles.brand}>
          <strong style={styles.brandTitle}>VL</strong>
          {!collapsed ? <span style={styles.brandSub}>Vibe Learner</span> : null}
        </div>
        <button
          type="button"
          className="app-nav-collapse-btn"
          style={styles.collapseButton}
          onClick={() => setCollapsed((value) => !value)}
          aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
        >
          {collapsed ? "›" : "‹"}
        </button>
      </div>

      <nav className="app-nav-links" style={styles.nav}>
        {NAV_ITEMS.map((item) => {
          const active = item.href === currentPath;
          return (
            <Link
              key={item.href}
              href={item.href as never}
              className={active ? "app-nav-link--active" : "app-nav-link"}
              title={collapsed ? item.label : undefined}
            >
              <span style={styles.linkDot}>{active ? "●" : "○"}</span>
              {!collapsed ? <span>{item.label}</span> : null}
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}

const styles: Record<string, CSSProperties> = {
  aside: {
    position: "fixed",
    left: 0,
    top: 0,
    bottom: 0,
    width: "var(--app-nav-width)",
    borderRight: "1px solid var(--border)",
    background: "var(--bg)",
    padding: "16px 0",
    zIndex: 40,
    display: "grid",
    alignContent: "start",
    gap: 0,
    transition: "width 220ms ease",
  },
  topRow: {
    display: "flex",
    justifyContent: "space-between",
    alignItems: "center",
    gap: 8,
    padding: "0 14px 14px",
    borderBottom: "1px solid var(--border)",
    marginBottom: 8,
  },
  brand: {
    display: "flex",
    alignItems: "baseline",
    gap: 6,
  },
  brandCollapsed: {
    display: "grid",
    placeItems: "center",
    width: "100%",
  },
  brandTitle: {
    color: "var(--accent)",
    fontSize: 13,
    fontWeight: 700,
    letterSpacing: "0.08em",
  },
  brandSub: {
    color: "var(--muted)",
    fontSize: 11,
  },
  collapseButton: {
    border: "none",
    background: "transparent",
    color: "var(--muted)",
    width: 28,
    height: 28,
    cursor: "pointer",
    fontSize: 16,
    lineHeight: 1,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    flexShrink: 0,
  },
  nav: {
    display: "grid",
    gap: 0,
  },
  linkDot: {
    width: 14,
    textAlign: "center",
    fontSize: 11,
    lineHeight: 1,
    flexShrink: 0,
  },
};
