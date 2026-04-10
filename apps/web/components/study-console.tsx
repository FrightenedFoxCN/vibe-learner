"use client";

import type { CSSProperties } from "react";
import { useState } from "react";
import type { DocumentSection, StudyChatResponse } from "@gal-learner/shared";

const AI_BASE_URL = process.env.NEXT_PUBLIC_AI_BASE_URL ?? "http://127.0.0.1:8000";

interface StudyConsoleProps {
  isPending: boolean;
  onAsk: (message: string) => void;
  onChangeSection: (sectionId: string) => void;
  onOpenPage?: (page: number) => void;
  sectionId: string;
  sectionTitle?: string;
  sections: DocumentSection[];
  session: StudyChatResponse | null;
  disabled?: boolean;
}

export function StudyConsole({
  isPending,
  onAsk,
  onChangeSection,
  onOpenPage,
  sectionId,
  sectionTitle,
  sections,
  session,
  disabled
}: StudyConsoleProps) {
  const [message, setMessage] = useState("请解释这一章的核心概念，并给我一个复述练习。");
  const uniqueSections = sections.filter(
    (section, index) => sections.findIndex((candidate) => candidate.id === section.id) === index
  );
  const currentSectionId = sectionId || uniqueSections[0]?.id || "";
  const currentSection =
    uniqueSections.find((section) => section.id === currentSectionId) ?? uniqueSections[0] ?? null;
  const textbookLinkBase = currentSection
    ? `${AI_BASE_URL}/documents/${currentSection.documentId}/file`
    : "";

  return (
    <article style={styles.panel}>
      <div style={styles.row}>
        <div>
          <p style={styles.sectionLabel}>章节会话</p>
          <h2 style={styles.title}>{sectionTitle || "等待创建学习会话"}</h2>
          {sectionId ? <p style={styles.sectionMeta}>section id: {sectionId}</p> : null}
          {uniqueSections.length ? (
            <label style={styles.sectionPickerLabel}>
              当前章节
              <select
                style={styles.sectionPicker}
                value={currentSectionId}
                onChange={(event) => onChangeSection(event.target.value)}
                disabled={isPending || disabled}
              >
                {uniqueSections.map((section) => (
                  <option key={section.id} value={section.id}>
                    {formatSectionOptionLabel(section)}
                  </option>
                ))}
              </select>
              {currentSection ? (
                <div style={styles.pageLinkRow}>
                  {buildPageLinks(currentSection).map((link) => (
                    <a
                      key={`${link.page}-${link.label}`}
                      href={`${textbookLinkBase}#page=${link.page}`}
                      target="_blank"
                      rel="noreferrer"
                      style={styles.pageLink}
                      onClick={(event) => {
                        if (!onOpenPage) {
                          return;
                        }
                        event.preventDefault();
                        onOpenPage(link.page);
                      }}
                    >
                      {link.label}
                    </a>
                  ))}
                </div>
              ) : null}
            </label>
          ) : null}
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
            session?.citations.map((citation, index) => (
              <span
                key={`${citation.sectionId}:${citation.pageStart}:${citation.pageEnd}:${index}`}
                style={styles.citation}
              >
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
    borderRadius: 24,
    border: "1px solid var(--border)",
    background: "var(--panel-strong)",
    boxShadow: "var(--shadow)"
  },
  row: {
    display: "flex",
    justifyContent: "space-between",
    gap: 16,
    alignItems: "flex-start",
    flexWrap: "wrap"
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
    fontSize: 24,
    fontFamily: "var(--font-display), sans-serif"
  },
  sectionMeta: {
    margin: "6px 0 0",
    color: "var(--muted)",
    fontSize: 13
  },
  sectionPickerLabel: {
    marginTop: 10,
    display: "grid",
    gap: 6,
    color: "var(--muted)",
    fontSize: 12,
    maxWidth: 420
  },
  sectionPicker: {
    minHeight: 40,
    borderRadius: 10,
    border: "1px solid var(--border)",
    padding: "8px 10px",
    background: "rgba(255,255,255,0.98)",
    color: "var(--ink)"
  },
  pageLinkRow: {
    marginTop: 8,
    display: "flex",
    gap: 8,
    flexWrap: "wrap"
  },
  pageLink: {
    display: "inline-flex",
    alignItems: "center",
    minHeight: 32,
    borderRadius: 10,
    padding: "6px 10px",
    background: "rgba(63,140,133,0.1)",
    border: "1px solid rgba(63,140,133,0.2)",
    color: "var(--accent)",
    fontSize: 12,
    fontWeight: 600
  },
  button: {
    border: 0,
    borderRadius: 12,
    minHeight: 44,
    padding: "0 16px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 700,
    boxShadow: "0 6px 14px rgba(13, 110, 114, 0.24)",
    cursor: "pointer"
  },
  textarea: {
    width: "100%",
    minHeight: 120,
    marginTop: 14,
    borderRadius: 12,
    padding: 14,
    border: "1px solid var(--border)",
    background: "rgba(255,255,255,0.98)",
    resize: "vertical"
  },
  responseCard: {
    marginTop: 14,
    padding: 16,
    borderRadius: 12,
    background: "rgba(248,252,253,0.96)",
    border: "1px solid var(--border)",
    boxShadow: "var(--shadow-soft)"
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
    borderRadius: 10,
    background: "var(--accent-soft)",
    fontSize: 13
  },
  emptyCitation: {
    color: "var(--muted)",
    fontSize: 13
  }
};

function formatSectionOptionLabel(section: DocumentSection) {
  const pageLabel = formatPageRange(section.pageStart, section.pageEnd);
  return `${section.title} · ${pageLabel}`;
}

function formatPageRange(pageStart: number, pageEnd: number) {
  if (pageStart === pageEnd) {
    return `p.${pageStart}`;
  }
  return `p.${pageStart}-${pageEnd}`;
}

function buildPageLinks(section: DocumentSection): Array<{ page: number; label: string }> {
  if (section.pageStart === section.pageEnd) {
    return [
      {
        page: section.pageStart,
        label: `打开课本 ${formatPageRange(section.pageStart, section.pageEnd)}`
      }
    ];
  }

  return [
    {
      page: section.pageStart,
      label: `打开起始页 p.${section.pageStart}`
    },
    {
      page: section.pageEnd,
      label: `打开结束页 p.${section.pageEnd}`
    }
  ];
}
