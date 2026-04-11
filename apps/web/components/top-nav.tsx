"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import type { CSSProperties, JSX } from "react";

interface TopNavProps {
  currentPath: "/" | "/plan" | "/study" | "/persona-spectrum" | "/scene-setup" | "/sensory-tools" | "/debug";
}

/* ─── SVG icons (16×16, stroke, currentColor) ─── */

function IconHome() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 7.5L8 2L15 7.5V14H10.5V9.5H5.5V14H1V7.5Z" />
    </svg>
  );
}

function IconPlan() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <rect x="2" y="1" width="12" height="14" />
      <line x1="5" y1="5" x2="11" y2="5" />
      <line x1="5" y1="8" x2="11" y2="8" />
      <line x1="5" y1="11" x2="9" y2="11" />
    </svg>
  );
}

function IconStudy() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1 1H10V8H5L1 12V1Z" />
      <path d="M10 4H15V10H10" />
    </svg>
  );
}

function IconPersona() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round">
      <circle cx="8" cy="5" r="3" />
      <path d="M1 15c0-3.866 3.134-7 7-7s7 3.134 7 7" />
    </svg>
  );
}

function IconScene() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12l3.5-4.5L9 10l2.5-3L14 12" />
      <path d="M2 3h12v10H2z" />
      <circle cx="5" cy="6" r="0.8" />
    </svg>
  );
}

function IconDebug() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <rect x="1" y="2" width="14" height="12" />
      <polyline points="4,6 7,9 4,12" />
      <line x1="9" y1="12" x2="13" y2="12" />
    </svg>
  );
}

function IconSensory() {
  return (
    <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M1.5 8c1.6-2.8 3.8-4.2 6.5-4.2S12.9 5.2 14.5 8c-1.6 2.8-3.8 4.2-6.5 4.2S3.1 10.8 1.5 8Z" />
      <circle cx="8" cy="8" r="2.1" />
    </svg>
  );
}

function IconChevronLeft() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9,2 4,7 9,12" />
    </svg>
  );
}

function IconChevronRight() {
  return (
    <svg width="14" height="14" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="5,2 10,7 5,12" />
    </svg>
  );
}

const NAV_ITEMS: Array<{
  href: TopNavProps["currentPath"];
  label: string;
  Icon: () => JSX.Element;
}> = [
  { href: "/",                 label: "导航首页", Icon: IconHome    },
  { href: "/plan",             label: "计划生成", Icon: IconPlan    },
  { href: "/study",            label: "章节对话", Icon: IconStudy   },
  { href: "/persona-spectrum", label: "人格色谱", Icon: IconPersona },
  { href: "/scene-setup",      label: "场景搭建", Icon: IconScene   },
  { href: "/sensory-tools",    label: "感官工具", Icon: IconSensory },
  { href: "/debug",            label: "调试后台", Icon: IconDebug   },
];

export function TopNav({ currentPath }: TopNavProps) {
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const saved = window.localStorage.getItem("vibe-nav-collapsed");
    if (saved === "1") setCollapsed(true);
  }, []);

  useEffect(() => {
    const width = collapsed ? "56px" : "200px";
    document.documentElement.style.setProperty("--app-nav-width", width);
    window.localStorage.setItem("vibe-nav-collapsed", collapsed ? "1" : "0");
  }, [collapsed]);

  return (
    <aside className="app-side-nav" style={styles.aside} aria-label="Primary navigation">
      {/* Brand */}
      <div className="app-nav-brand-row" style={styles.topRow}>
        <div style={styles.brandMark}>VL</div>
        {!collapsed ? <span style={styles.brandName}>Vibe Learner</span> : null}
      </div>

      {/* Nav links */}
      <nav className="app-nav-links" style={styles.nav}>
        {NAV_ITEMS.map((item) => {
          const active = item.href === currentPath;
          return (
            <Link
              key={item.href}
              href={item.href as never}
              className={active ? "app-nav-link--active" : "app-nav-link"}
              style={collapsed ? styles.linkCollapsed : undefined}
              title={item.label}
            >
              <item.Icon />
              {!collapsed ? <span>{item.label}</span> : null}
            </Link>
          );
        })}
      </nav>

      {/* Spacer pushes the toggle to the bottom */}
      <div style={{ flex: 1 }} />

      {/* Collapse toggle — pinned to bottom */}
      <button
        type="button"
        className="app-nav-collapse-btn"
        style={collapsed ? styles.toggleCollapsed : styles.toggle}
        onClick={() => setCollapsed((v) => !v)}
        aria-label={collapsed ? "Expand navigation" : "Collapse navigation"}
        title={collapsed ? "展开侧栏" : "收起侧栏"}
      >
        {collapsed ? <IconChevronRight /> : <><IconChevronLeft /><span>收起</span></>}
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
    background: "var(--accent)",
    color: "white",
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    fontSize: 11,
    fontWeight: 800,
    letterSpacing: "0.06em",
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
