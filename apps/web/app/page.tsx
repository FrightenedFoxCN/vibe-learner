import type { CSSProperties } from "react";
import Link from "next/link";

import { TopNav } from "../components/top-nav";

const PAGES = [
  {
    num: "01",
    href: "/plan" as const,
    title: "计划生成",
    desc: "上传教材、解析章节结构，生成与刷新个性化学习计划。",
  },
  {
    num: "02",
    href: "/study" as const,
    title: "章节对话",
    desc: "左侧对话，右侧 PDF 联动，按章节与 AI 教师深入学习。",
  },
  {
    num: "03",
    href: "/persona-spectrum" as const,
    title: "人格层",
    desc: "配置 AI 教师人格、插槽权重、风格调参与导入导出。",
  },
  {
    num: "04",
    href: "/scene-setup" as const,
    title: "场景搭建",
    desc: "从世界到教室搭建层级场景，并为每一层补充可互动物体。",
  },
];

export default function HomePage() {
  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/" />

      <header style={styles.header}>
        <h1 style={styles.title}>学习工作台</h1>
        <p style={styles.subtitle}>AI 辅助学习系统 · 计划 · 对话 · 人格</p>
        <div style={styles.rule} />
      </header>

      <nav className="home-nav-grid">
        {PAGES.map((page) => (
          <Link
            key={page.href}
            href={page.href}
            className="home-nav-item"
            style={styles.navItem}
          >
            <span style={styles.navNum}>{page.num}</span>
            <span style={styles.navTitle}>{page.title}</span>
            <span style={styles.navDesc}>{page.desc}</span>
            <span style={styles.navArrow}>→</span>
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
    fontSize: 16,
    color: "var(--border-strong)",
    marginTop: 4,
  },
};
