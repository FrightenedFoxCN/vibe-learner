import type { CSSProperties } from "react";

import { TopNav } from "../components/top-nav";

export default function HomePage() {
  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/" />

      <div style={styles.topbar}>
        <span style={styles.topbarTitle}>学习导航</span>
        <span style={styles.topbarSub}>将计划生成、章节对话、人格配置拆分为并行页面。</span>
      </div>

      <nav className="home-nav-grid">
        <a href="/plan" style={styles.navItem}>
          <span style={styles.navTitle}>计划生成页</span>
          <span style={styles.navDesc}>上传教材、解析章节、生成与刷新学习计划。</span>
        </a>
        <a href="/study" style={styles.navItem}>
          <span style={styles.navTitle}>章节对话页</span>
          <span style={styles.navDesc}>左侧对话，右侧 PDF 联动，按章节进行深入学习。</span>
        </a>
        <a href="/persona-spectrum" style={styles.navItem}>
          <span style={styles.navTitle}>人格色谱页</span>
          <span style={styles.navDesc}>教师人格配置、风格调参与预览。</span>
        </a>
      </nav>
    </main>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    maxWidth: 1280,
    margin: "0 auto",
    padding: "20px 32px 48px",
    display: "grid",
    gap: 20,
    alignContent: "start"
  },
  topbar: {
    display: "flex",
    alignItems: "baseline",
    gap: 12,
    paddingBottom: 16
  },
  topbarTitle: {
    fontSize: 16,
    fontWeight: 700,
    color: "var(--ink)"
  },
  topbarSub: {
    fontSize: 13,
    color: "var(--muted)"
  },
  nav: {
    display: "grid",
    gridTemplateColumns: "repeat(3, minmax(0, 1fr))",
    gap: 1,
    background: "var(--border)"
  },
  navItem: {
    display: "grid",
    gap: 6,
    padding: "24px 28px",
    background: "var(--bg)",
    textDecoration: "none"
  },
  navTitle: {
    fontSize: 15,
    fontWeight: 600,
    color: "var(--ink)"
  },
  navDesc: {
    fontSize: 13,
    color: "var(--muted)",
    lineHeight: 1.6
  }
};