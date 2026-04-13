import type { CSSProperties } from "react";
import Link from "next/link";

import { MaterialIcon, type MaterialIconName } from "../components/material-icon";
import { TopNav } from "../components/top-nav";

const PAGES = [
  {
    num: "01",
    href: "/plan" as const,
    icon: "description" as MaterialIconName,
    title: "计划生成",
    desc: "上传教材并生成学习计划。",
  },
  {
    num: "02",
    href: "/study" as const,
    icon: "chat" as MaterialIconName,
    title: "章节对话",
    desc: "按章节提问，联动查看教材。",
  },
  {
    num: "03",
    href: "/persona-spectrum" as const,
    icon: "person" as MaterialIconName,
    title: "人格色谱",
    desc: "管理教师人格与风格。",
  },
  {
    num: "04",
    href: "/scene-setup" as const,
    icon: "account_tree" as MaterialIconName,
    title: "场景搭建",
    desc: "搭建学习场景与物体。",
  },
  {
    num: "05",
    href: "/sensory-tools" as const,
    icon: "visibility" as MaterialIconName,
    title: "感官工具",
    desc: "管理对话可用工具。",
  },
  {
    num: "06",
    href: "/settings" as const,
    icon: "settings" as MaterialIconName,
    title: "统一设置",
    desc: "管理运行参数与连接。",
  },
];

export default function HomePage() {
  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/" />

      <header style={styles.header}>
        <h1 style={styles.title}>学习工作台</h1>
        <p style={styles.subtitle}>计划 · 对话 · 人格</p>
        <div style={styles.rule} />
      </header>

      <nav className="home-nav-grid">
        {PAGES.map((page) => (
          <Link
            key={page.href}
            href={page.href as never}
            className="home-nav-item"
            style={styles.navItem}
          >
            <div style={styles.navTopRow}>
              <span style={styles.navNum}>{page.num}</span>
              <span style={styles.navIconWrap}>
                <MaterialIcon name={page.icon} size={18} />
              </span>
            </div>
            <span style={styles.navTitle}>{page.title}</span>
            <span style={styles.navDesc}>{page.desc}</span>
            <span style={styles.navArrow}>
              <MaterialIcon name="arrow_forward" size={18} />
            </span>
          </Link>
        ))}
      </nav>
    </main>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    maxWidth: 1280,
    margin: "0 auto",
    padding: "48px 32px 64px",
    display: "grid",
    gap: 40,
    alignContent: "start",
  },
  header: {
    display: "grid",
    gap: 8,
  },
  title: {
    margin: 0,
    fontSize: 28,
    fontWeight: 800,
    color: "var(--ink)",
    letterSpacing: "-0.02em",
    lineHeight: 1.2,
  },
  subtitle: {
    margin: 0,
    fontSize: 14,
    color: "var(--muted)",
    letterSpacing: "0.01em",
  },
  rule: {
    height: 1,
    background: "var(--border)",
    marginTop: 8,
  },
  navItem: {
    display: "grid",
    gap: 8,
    padding: "28px 28px 24px",
    background: "var(--bg)",
    textDecoration: "none",
  },
  navNum: {
    fontSize: 11,
    fontWeight: 700,
    color: "var(--accent)",
    letterSpacing: "0.12em",
  },
  navTopRow: {
    display: "flex",
    alignItems: "center",
    justifyContent: "space-between",
    gap: 12,
  },
  navIconWrap: {
    width: 28,
    height: 28,
    borderRadius: 999,
    border: "1px solid color-mix(in srgb, var(--accent) 24%, var(--border))",
    background: "color-mix(in srgb, white 84%, var(--accent-soft))",
    color: "var(--accent)",
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
  },
  navTitle: {
    fontSize: 18,
    fontWeight: 700,
    color: "var(--ink)",
    lineHeight: 1.2,
  },
  navDesc: {
    fontSize: 13,
    color: "var(--muted)",
    lineHeight: 1.65,
  },
  navArrow: {
    display: "inline-flex",
    alignItems: "center",
    color: "var(--border-strong)",
    marginTop: 4,
  },
};
