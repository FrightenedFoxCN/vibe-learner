"use client";

import type { CSSProperties } from "react";
import RichTextMessageRenderer from "./rich-text-message-client";

interface RichTextMessageProps {
  content: string;
  style?: CSSProperties;
  inline?: boolean;
}

export function RichTextMessage({ content, style, inline = false }: RichTextMessageProps) {
  const WrapperTag = inline ? "span" : "div";
  return (
    <WrapperTag style={style}>
      <RichTextMessageRenderer content={content} inline={inline} />
    </WrapperTag>
  );
}
