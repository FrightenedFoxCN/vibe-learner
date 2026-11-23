"use client";

import dynamic from "next/dynamic";
import { Suspense, type CSSProperties } from "react";

const RichTextMessageRenderer = dynamic(() => import("./rich-text-message-client"));

interface RichTextMessageProps {
  content: string;
  style?: CSSProperties;
  className?: string;
  inline?: boolean;
}

export function RichTextMessage({
  content,
  style,
  className,
  inline = false,
}: RichTextMessageProps) {
  const WrapperTag = inline ? "span" : "div";
  return (
    <WrapperTag style={style} className={className}>
      <Suspense
        fallback={
          <WrapperTag className="study-markdown-root whitespace-pre-wrap wrap-anywhere">
            {content}
          </WrapperTag>
        }
      >
        <RichTextMessageRenderer content={content} inline={inline} />
      </Suspense>
    </WrapperTag>
  );
}
