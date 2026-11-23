import type { ComponentPropsWithRef, ReactNode } from "react";

export type CollapsibleProps = Omit<
  ComponentPropsWithRef<"details">,
  "dangerouslySetInnerHTML"
> & {
  /** Visible label for the native disclosure; do not nest interactive controls here. */
  summary: ReactNode;
  summaryClassName?: string;
  contentClassName?: string;
};

export function Collapsible({
  children,
  className,
  contentClassName,
  summary,
  summaryClassName,
  ...props
}: CollapsibleProps) {
  return (
    <details
      {...props}
      className={[
        "min-w-0 border border-solid border-border bg-panel text-ink",
        "open:[&>summary>span:first-child>span:first-child]:hidden open:[&>summary>span:first-child>span:last-child]:inline",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    >
      <summary
        className={[
          "flex min-h-11 cursor-pointer list-none items-center gap-2 px-3 py-2 text-sm font-semibold wrap-anywhere hover:bg-panel-strong",
          "focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-accent [&::-webkit-details-marker]:hidden",
          summaryClassName,
        ]
          .filter(Boolean)
          .join(" ")}
      >
        <span aria-hidden="true" className="w-4 shrink-0 text-center text-accent">
          <span>+</span>
          <span className="hidden">−</span>
        </span>
        <span className="min-w-0">{summary}</span>
      </summary>
      <div
        className={["min-w-0 px-3 pb-3", contentClassName].filter(Boolean).join(" ")}
      >
        {children}
      </div>
    </details>
  );
}
