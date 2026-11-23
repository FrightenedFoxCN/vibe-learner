"use client";

import dynamic from "next/dynamic";
import { Suspense, type CSSProperties } from "react";

const RichTextMessageRenderer = dynamic(() => import("./rich-text-message-client"));
const pendingTextStyle: CSSProperties = {
  whiteSpace: "pre-wrap",
  overflowWrap: "anywhere",
};

interface RichTextMessageProps {
  content: string;
  style?: CSSProperties;
  inline?: boolean;
}

export function RichTextMessage({
  content,
  style,
  inline = false,
}: RichTextMessageProps) {
  const WrapperTag = inline ? "span" : "div";
  return (
    <WrapperTag style={style}>
      <Suspense
        fallback={
          <WrapperTag className="study-markdown-root" style={pendingTextStyle}>
            {content}
          </WrapperTag>
        }
      >
        <RichTextMessageRenderer content={content} inline={inline} />
      </Suspense>
    </WrapperTag>
  );
}
