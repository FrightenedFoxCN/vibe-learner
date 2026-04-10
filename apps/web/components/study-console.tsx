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
    <div style={styles.wrap}>
      {/* 章节选择行 */}
      <div style={styles.row}>
        {uniqueSections.length ? (
          <select
            style={styles.select}
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
        ) : (
          <span style={styles.placeholder}>{sectionTitle || "等待创建学习会话"}</span>
        )}
        {currentSection
          ? buildPageLinks(currentSection).map((link) => (
              <a
                key={`${link.page}-${link.label}`}
                href={`${textbookLinkBase}#page=${link.page}`}
                target="_blank"
                rel="noreferrer"
                style={styles.pageLink}
                onClick={(event) => {
                  if (!onOpenPage) return;
                  event.preventDefault();
                  onOpenPage(link.page);
                }}
              >
                {link.label}
              </a>
            ))
          : null}
      </div>

      {/* 输入行 */}
      <div style={styles.inputRow}>
        <textarea
          style={styles.textarea}
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          placeholder="输入导学请求…"
        />
        <button
          style={{
            ...styles.button,
            ...(isPending || disabled ? styles.buttonDisabled : {})
          }}
          disabled={isPending || disabled}
          onClick={() => onAsk(message)}
        >
          {isPending ? "生成中…" : "发送"}
        </button>
      </div>

      {/* 回复区：有内容才显示 */}
      {session?.reply ? (
        <div style={styles.reply}>
          <p style={styles.replyText}>{session.reply}</p>
          {session.citations.length ? (
            <div style={styles.citations}>
              {session.citations.map((citation, index) => (
                <span
                  key={`${citation.sectionId}:${citation.pageStart}:${citation.pageEnd}:${index}`}
                  style={styles.citation}
                >
                  {citation.title} · p.{citation.pageStart}–{citation.pageEnd}
                </span>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

const styles: Record<string, CSSProperties> = {
  wrap: {
    display: "grid",
    gap: 0
  },
  row: {
    display: "flex",
    alignItems: "center",
    gap: 8,
    paddingBottom: 10,
    flexWrap: "wrap"
  },
  select: {
    height: 32,
    border: "1px solid var(--border)",
    borderRadius: 3,
    padding: "0 8px",
    background: "transparent",
    color: "var(--ink)",
    fontSize: 13,
    maxWidth: 300
  },
  placeholder: {
    color: "var(--muted)",
    fontSize: 13
  },
  pageLink: {
    display: "inline-flex",
    alignItems: "center",
    height: 28,
    padding: "0 8px",
    border: "1px solid var(--border)",
    borderRadius: 3,
    color: "var(--accent)",
    fontSize: 12,
    whiteSpace: "nowrap"
  },
  inputRow: {
    display: "flex",
    gap: 10,
    alignItems: "flex-start"
  },
  textarea: {
    flex: 1,
    minHeight: 72,
    border: "1px solid var(--border)",
    borderRadius: 3,
    padding: "8px 10px",
    background: "var(--panel)",
    resize: "vertical",
    fontSize: 14,
    lineHeight: 1.6,
    color: "var(--ink)"
  },
  button: {
    border: "none",
    borderRadius: 3,
    height: 34,
    padding: "0 18px",
    background: "var(--accent)",
    color: "white",
    fontWeight: 600,
    cursor: "pointer",
    fontSize: 13,
    whiteSpace: "nowrap",
    flexShrink: 0,
    alignSelf: "flex-end"
  },
  buttonDisabled: {
    opacity: 0.45,
    cursor: "not-allowed"
  },
  reply: {
    paddingTop: 16,
    display: "grid",
    gap: 10
  },
  replyText: {
    margin: 0,
    lineHeight: 1.75,
    fontSize: 14
  },
  citations: {
    display: "flex",
    gap: 6,
    flexWrap: "wrap"
  },
  citation: {
    padding: "2px 8px",
    border: "1px solid var(--border)",
    borderRadius: 3,
    fontSize: 12,
    color: "var(--teal)"
  }
};

function formatSectionOptionLabel(section: DocumentSection) {
  const pageLabel = formatPageRange(section.pageStart, section.pageEnd);
  return `${section.title} · ${pageLabel}`;
}

function formatPageRange(pageStart: number, pageEnd: number) {
  if (pageStart === pageEnd) return `p.${pageStart}`;
  return `p.${pageStart}-${pageEnd}`;
}

function buildPageLinks(section: DocumentSection): Array<{ page: number; label: string }> {
  if (section.pageStart === section.pageEnd) {
    return [{ page: section.pageStart, label: `p.${section.pageStart}` }];
  }
  return [
    { page: section.pageStart, label: `p.${section.pageStart}` },
    { page: section.pageEnd, label: `p.${section.pageEnd}` }
  ];
}
