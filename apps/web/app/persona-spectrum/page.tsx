import type { CSSProperties } from "react";

import { TopNav } from "../../components/top-nav";

export default function PersonaSpectrumPage() {
  return (
    <main className="with-app-nav" style={styles.page}>
      <TopNav currentPath="/persona-spectrum" />

      <div style={styles.topbar}>
        <span style={styles.topbarTitle}>人格色谱</span>
        <span style={styles.topbarSub}>教师人格配置、情绪区间与叙事模式。</span>
      </div>

      <div style={styles.placeholder}>
        <span style={styles.blockTitle}>待实现能力</span>
        <ul style={styles.list}>
          <li style={styles.listItem}>人格参数编辑器（教学风格、鼓励策略、纠错策略）</li>
          <li style={styles.listItem}>情绪与动作色谱调试面板</li>
          <li style={styles.listItem}>配置版本管理与回放</li>
          <li style={styles.listItem}>与章节对话联动的实时人格预览</li>
        </ul>
      </div>
    </main>
  );
}

const styles: Record<string, CSSProperties> = {
  page: {
    minHeight: "100vh",
    maxWidth: 860,
    margin: "0 auto",
    padding: "20px 24px 34px",
    display: "grid",
    gap: 16,
    alignContent: "start"
  },
  topbar: {
    display: "flex",
    alignItems: "baseline",
    gap: 12,
    borderBottom: "1px solid var(--border)",
    paddingBottom: 12
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
  placeholder: {
    paddingTop: 14,
    display: "grid",
    gap: 8,
    borderBottom: "1px solid var(--border)",
    paddingBottom: 14
  },
  blockTitle: {
    margin: 0,
    fontSize: 14,
    fontWeight: 700
  },
  list: {
    margin: 0,
    paddingLeft: 0,
    listStyle: "none",
    display: "grid",
    gap: 0
  },
  listItem: {
    padding: "8px 0",
    borderTop: "1px solid var(--border)",
    fontSize: 13,
    color: "var(--muted)",
    lineHeight: 1.6
  }
};
