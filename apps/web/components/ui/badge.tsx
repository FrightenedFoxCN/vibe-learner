import type { ComponentPropsWithRef } from "react";

export type BadgeVariant = "neutral" | "accent" | "positive" | "negative";

export type BadgeProps = ComponentPropsWithRef<"span"> & {
  variant?: BadgeVariant;
};

const variantClasses: Record<BadgeVariant, string> = {
  neutral: "border-border bg-panel text-ink-2",
  accent: "border-accent bg-accent-soft text-accent",
  positive: "border-positive bg-bg text-positive",
  negative: "border-negative bg-bg text-negative",
};

export function Badge({ className, variant = "neutral", ...props }: BadgeProps) {
  return (
    <span
      {...props}
      className={[
        "inline-flex max-w-full items-center border border-solid px-2 py-0.5 text-xs font-medium wrap-anywhere",
        variantClasses[variant],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    />
  );
}
