"use client";

import dynamic from "next/dynamic";
import type { CSSProperties } from "react";

interface RichTextMessageProps {
  content: string;
  style?: CSSProperties;
  inline?: boolean;
}

const RichTextMessageRenderer = dynamic(() => import("./rich-text-message-client"), {
  ssr: false,
  loading: () => null,
});

export function RichTextMessage({ content, style, inline = false }: RichTextMessageProps) {
  const WrapperTag = inline ? "span" : "div";
  return (
    <WrapperTag style={style}>
      <RichTextMessageRenderer content={content} inline={inline} />
    </WrapperTag>
  );
}
