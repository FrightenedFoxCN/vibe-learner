"use client";

import { isValidElement } from "react";
import type { ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { normalizeRichTextContent } from "../../lib/rich-text-normalize";
import { MermaidDiagram } from "./mermaid-diagram";
import "./rich-text-message-vendor.css";
import styles from "./rich-text-message.module.css";

interface RichTextMessageClientProps {
  content: string;
  inline?: boolean;
}

export default function RichTextMessageClient({
  content,
  inline = false,
}: RichTextMessageClientProps) {
  const normalizedContent = normalizeRichTextContent(content, { inline });
  const WrapperTag = inline ? "span" : "div";

  return (
    <WrapperTag className={styles.root}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[rehypeKatex]}
        components={{
          p: ({ children }) =>
            inline ? (
              <span className={styles.inlineParagraph}>{children}</span>
            ) : (
              <p className={styles.paragraph}>{children}</p>
            ),
          ul: ({ children }) => <ul className={styles.list}>{children}</ul>,
          ol: ({ children }) => <ol className={styles.orderedList}>{children}</ol>,
          li: ({ children }) => (
            <li className={styles.listItem}>
              <div className={styles.listItemContent}>{children}</div>
            </li>
          ),
          blockquote: ({ children }) => (
            <blockquote className={styles.blockquote}>{children}</blockquote>
          ),
          h1: ({ children }) => <h1 className={styles.h1}>{children}</h1>,
          h2: ({ children }) => <h2 className={styles.h2}>{children}</h2>,
          h3: ({ children }) => <h3 className={styles.h3}>{children}</h3>,
          hr: () => <hr className={styles.hr} />,
          table: ({ children }) => (
            <div className={styles.tableWrap}>
              <table className={styles.table}>{children}</table>
            </div>
          ),
          th: ({ children }) => <th className={styles.th}>{children}</th>,
          td: ({ children }) => <td className={styles.td}>{children}</td>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noreferrer" className={styles.link}>
              {children}
            </a>
          ),
          code: ({ className, children }) => (
            <code className={className ? `${styles.code} ${className}` : styles.code}>
              {children}
            </code>
          ),
          pre: ({ children }) => {
            const mermaidChart = extractMermaidChart(children);
            if (mermaidChart) {
              return <MermaidDiagram chart={mermaidChart} />;
            }
            return <pre className={styles.pre}>{children}</pre>;
          },
        }}
      >
        {normalizedContent}
      </ReactMarkdown>
    </WrapperTag>
  );
}

function extractMermaidChart(children: ReactNode) {
  if (!isValidElement<{ className?: string; children?: ReactNode }>(children)) {
    return "";
  }
  const className = String(children.props?.className ?? "");
  if (!className.includes("language-mermaid")) {
    return "";
  }
  return String(children.props?.children ?? "")
    .replace(/\n$/, "")
    .trim();
}
