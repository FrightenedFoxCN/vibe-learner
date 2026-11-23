import type { ComponentPropsWithRef } from "react";

export type CardProps = ComponentPropsWithRef<"div">;

export function Card({ className, ...props }: CardProps) {
  return (
    <div
      {...props}
      className={[
        "min-w-0 border border-solid border-border bg-bg p-3 text-ink",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    />
  );
}
