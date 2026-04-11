"use client";

import type { CSSProperties } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

interface RichTextMessageClientProps {
  content: string;
  style?: CSSProperties;
  inline?: boolean;
}

export default function RichTextMessageClient({ content, style, inline = false }: RichTextMessageClientProps) {
  const normalizedContent = normalizeRichTextContent(content);
  const WrapperTag = inline ? "span" : "div";

  return (
    <WrapperTag className="study-markdown-root" style={style}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          p: ({ children }) => (
            inline ? <span style={styles.inlineParagraph}>{children}</span> : <p style={styles.paragraph}>{children}</p>
          ),
          ul: ({ children }) => <ul style={styles.list}>{children}</ul>,
          ol: ({ children }) => <ol style={styles.orderedList}>{children}</ol>,
          li: ({ children }) => (
            <li style={styles.listItem}>
              <div style={styles.listItemContent}>{children}</div>
            </li>
          ),
          blockquote: ({ children }) => <blockquote style={styles.blockquote}>{children}</blockquote>,
          h1: ({ children }) => <h1 style={styles.h1}>{children}</h1>,
          h2: ({ children }) => <h2 style={styles.h2}>{children}</h2>,
          h3: ({ children }) => <h3 style={styles.h3}>{children}</h3>,
          hr: () => <hr style={styles.hr} />,
          table: ({ children }) => (
            <div style={styles.tableWrap}>
              <table style={styles.table}>{children}</table>
            </div>
          ),
          th: ({ children }) => <th style={styles.th}>{children}</th>,
          td: ({ children }) => <td style={styles.td}>{children}</td>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer" style={styles.link}>
              {children}
            </a>
          ),
          code: ({ className, children, ...props }: any) => {
            const isBlock = Boolean(className);
            if (isBlock) {
              return (
                <code className={className} style={styles.codeBlock} {...props}>
                  {children}
                </code>
              );
            }
            return (
              <code style={styles.inlineCode} {...props}>
                {children}
              </code>
            );
          },
          pre: ({ children }) => <pre style={styles.pre}>{children}</pre>,
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </WrapperTag>
  );
}

function normalizeRichTextContent(content: string) {
  return content
    .replace(/\r\n/g, "\n")
    .replace(/([:：])\s+(?=\d+\.\s+)/g, "$1\n\n")
    .replace(/([。！？])\s+(?=\d+\.\s+)/g, "$1\n\n")
    .replace(/([:：])\s+[*-]\s+/g, "$1\n\n   - ")
    .replace(/([。；;])\s+[*-]\s+/g, "$1\n   - ")
    .replace(/(\n\d+\.\s[^\n]*?)\s+[*-]\s+/g, "$1\n\n   - ")
    .replace(/\n\s*[*-]\s+/g, "\n   - ")
    .replace(/([^\n])\n(\d+\.\s+)/g, "$1\n\n$2")
    .replace(/\n{3,}/g, "\n\n");
}

const styles: Record<string, CSSProperties> = {
  paragraph: {
    margin: "0 0 10px",
  },
  inlineParagraph: {
    margin: 0,
    display: "inline",
  },
  list: {
    margin: "0 0 10px",
    paddingLeft: 20,
    whiteSpace: "normal",
  },
  orderedList: {
    margin: "0 0 10px",
    paddingLeft: 22,
    whiteSpace: "normal",
  },
  listItem: {
    lineHeight: 1.75,
    margin: "0 0 6px",
  },
  listItemContent: {
    minWidth: 0,
    whiteSpace: "normal",
    wordBreak: "break-word",
  },
  blockquote: {
    margin: "0 0 10px",
    padding: "8px 12px",
    borderLeft: "2px solid var(--border-strong)",
    background: "var(--panel)",
    color: "var(--ink-2)",
  },
  h1: {
    margin: "2px 0 10px",
    fontSize: 20,
    lineHeight: 1.3,
  },
  h2: {
    margin: "2px 0 10px",
    fontSize: 18,
    lineHeight: 1.35,
  },
  h3: {
    margin: "2px 0 8px",
    fontSize: 16,
    lineHeight: 1.4,
  },
  hr: {
    border: "none",
    borderTop: "1px solid var(--border)",
    margin: "12px 0",
  },
  tableWrap: {
    overflowX: "auto",
    marginBottom: 10,
  },
  table: {
    width: "100%",
    borderCollapse: "collapse",
    fontSize: 13,
  },
  th: {
    textAlign: "left",
    border: "1px solid var(--border)",
    padding: "8px 10px",
    background: "var(--panel)",
  },
  td: {
    border: "1px solid var(--border)",
    padding: "8px 10px",
    verticalAlign: "top",
  },
  link: {
    color: "var(--accent)",
    textDecoration: "underline",
    textUnderlineOffset: 2,
  },
  inlineCode: {
    padding: "1px 5px",
    border: "1px solid var(--border)",
    background: "var(--panel)",
    fontFamily: "var(--font-mono)",
    fontSize: "0.92em",
  },
  pre: {
    margin: "0 0 10px",
    padding: "10px 12px",
    border: "1px solid var(--border)",
    background: "#f8fbfc",
    overflowX: "auto",
  },
  codeBlock: {
    fontFamily: "var(--font-mono)",
    fontSize: 12,
    lineHeight: 1.7,
    whiteSpace: "pre",
  },
};
