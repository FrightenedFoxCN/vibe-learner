"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";

const RichTextMessageRenderer = dynamic(() => import("./rich-text-message-client"));

interface RichTextMessageProps {
  content: string;
  className?: string;
  inline?: boolean;
}

export function RichTextMessage({
  content,
  className,
  inline = false,
}: RichTextMessageProps) {
  const WrapperTag = inline ? "span" : "div";
  return (
    <WrapperTag className={className}>
      <Suspense
        fallback={
          <WrapperTag className="min-w-0 whitespace-pre-wrap wrap-anywhere">
            {content}
          </WrapperTag>
        }
      >
        <RichTextMessageRenderer content={content} inline={inline} />
      </Suspense>
    </WrapperTag>
  );
}
