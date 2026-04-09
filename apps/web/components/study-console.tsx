"use client";

import type { CSSProperties } from "react";
import { useState } from "react";
import type { StudyChatResponse } from "@gal-learner/shared";

interface StudyConsoleProps {
  isPending: boolean;
  onAsk: (message: string) => void;
  sectionId: string;
  sectionTitle?: string;
  session: StudyChatResponse | null;
  disabled?: boolean;
}

export function StudyConsole({
  isPending,
  onAsk,
  sectionId,
  sectionTitle,
  session,
  disabled
}: StudyConsoleProps) {
  const [message, setMessage] = useState("请解释这一章的核心概念，并给我一个复述练习。");

  return (
    <article style={styles.panel}>
      <div style={styles.row}>
        <div>
          <p style={styles.sectionLabel}>章节会话</p>
          <h2 style={styles.title}>{sectionTitle || "等待创建学习会话"}</h2>
          {sectionId ? <p style={styles.sectionMeta}>section id: {sectionId}</p> : null}
        </div>
        <button
          style={styles.button}
          disabled={isPending || disabled}
          onClick={() => onAsk(message)}
        >
          {isPending ? "生成中..." : disabled ? "先创建学习会话" : "发送导学请求"}
        </button>
      </div>

      <textarea
        style={styles.textarea}
        value={message}
        onChange={(event) => setMessage(event.target.value)}
      />

      <div style={styles.responseCard}>
        <p style={styles.responseLabel}>结构化回复</p>
        <p style={styles.responseText}>
          {session?.reply ?? "回复尚未生成。这里会同时展示文本回答和教材引用，角色事件则在右侧角色层消费。"}
        </p>
        <div style={styles.citations}>
          {(session?.citations ?? []).length ? (
            session?.citations.map((citation) => (
              <span key={citation.sectionId} style={styles.citation}>
                {citation.title} · p.{citation.pageStart}-{citation.pageEnd}
              </span>
            ))
          ) : (
            <span style={styles.emptyCitation}>暂无教材引用。</span>
          )}
        </div>
      </div>
    </article>
  );
}

const styles: Record<string, CSSProperties> = {
  panel: {
    padding: 24,
    borderRadius: 28,
    border: "1px solid var(--border)",
    background: "var(--panel)",
    boxShadow: "var(--shadow)"
  },
  row: {
    display: "flex",
    justifyContent: "space-between",
    gap: 16,
    alignItems: "center"
  },
  sectionLabel: {
    margin: 0,
    fontSize: 12,
    letterSpacing: "0.12em",
    textTransform: "uppercase",
    color: "var(--muted)"
  },
  title: {
    margin: "8px 0 0",
    fontSize: 28,
    fontFamily: "var(--font-display), sans-serif"
  },
  sectionMeta: {
    margin: "6px 0 0",
    color: "var(--muted)",
    fontSize: 13
  },
  button: {
    border: 0,
    borderRadius: 999,
    padding: "14px 18px",
    background: "var(--accent)",
    color: "white",
    cursor: "pointer"
  },
  textarea: {
    width: "100%",
    minHeight: 120,
    marginTop: 18,
    borderRadius: 22,
    padding: 18,
    border: "1px solid var(--border)",
    background: "rgba(255,255,255,0.8)",
    resize: "vertical"
  },
  responseCard: {
    marginTop: 18,
    padding: 20,
    borderRadius: 22,
    background: "rgba(255,255,255,0.76)",
    border: "1px solid var(--border)"
  },
  responseLabel: {
    margin: 0,
    color: "var(--muted)",
    fontSize: 13
  },
  responseText: {
    margin: "10px 0 0",
    lineHeight: 1.7
  },
  citations: {
    display: "flex",
    gap: 8,
    flexWrap: "wrap",
    marginTop: 14
  },
  citation: {
    padding: "8px 12px",
    borderRadius: 999,
    background: "var(--accent-soft)",
    fontSize: 13
  },
  emptyCitation: {
    color: "var(--muted)",
    fontSize: 13
  }
};
