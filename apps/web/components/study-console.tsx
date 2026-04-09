"use client";

import type { CSSProperties } from "react";
import { useState } from "react";
import type { StudyChatResponse } from "@gal-learner/shared";

interface StudyConsoleProps {
  isPending: boolean;
  onAsk: (message: string) => void;
  sectionId: string;
  session: StudyChatResponse | null;
}

export function StudyConsole({
  isPending,
  onAsk,
  sectionId,
  session
}: StudyConsoleProps) {
  const [message, setMessage] = useState("请解释这一章的核心概念，并给我一个复述练习。");

  return (
    <article style={styles.panel}>
      <div style={styles.row}>
        <div>
          <p style={styles.sectionLabel}>章节会话</p>
          <h2 style={styles.title}>{sectionId}</h2>
        </div>
        <button style={styles.button} disabled={isPending} onClick={() => onAsk(message)}>
          {isPending ? "生成中..." : "发送导学请求"}
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
          {session?.reply ?? "回复尚未生成。这里消费的是 reply + citations + characterEvents，而不是纯文本。"}
        </p>
        <div style={styles.citations}>
          {(session?.citations ?? []).map((citation) => (
            <span key={citation.sectionId} style={styles.citation}>
              {citation.title} · p.{citation.pageStart}-{citation.pageEnd}
            </span>
          ))}
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
  }
};
