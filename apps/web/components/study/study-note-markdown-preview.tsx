"use client";

import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import { normalizeMathDelimiters } from "../../lib/rich-text-normalize";
import "../ui/rich-text-message-vendor.css";

export default function StudyNoteMarkdownPreview({ source }: { source: string }) {
  if (!source.trim())
    return <p className="study-notes-muted">写下 Markdown，即可在这里预览。</p>;
  const normalizedSource = normalizeMathDelimiters(source);
  return (
    <ReactMarkdown
      skipHtml
      remarkPlugins={[remarkGfm, remarkMath]}
      rehypePlugins={[[rehypeKatex, { trust: false, strict: false }]]}
      components={{
        table: ({ children }) => (
          <div
            className="study-markdown-table"
            tabIndex={0}
            role="region"
            aria-label="Markdown 表格"
          >
            <table>{children}</table>
          </div>
        ),
        a: ({ href, children }) =>
          href ? (
            <a
              href={href}
              target={href.startsWith("#") ? undefined : "_blank"}
              rel="noopener noreferrer"
            >
              {children}
            </a>
          ) : (
            <span>{children}</span>
          ),
        // Imported notes are untrusted. A preview never fetches embedded URLs.
        img: ({ alt }) => (
          <span className="study-notes-muted">
            [图片不自动加载{alt ? "：" + alt : ""}]
          </span>
        ),
      }}
    >
      {normalizedSource}
    </ReactMarkdown>
  );
}
