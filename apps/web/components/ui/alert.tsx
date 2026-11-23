import type { ComponentPropsWithRef } from "react";

export type AlertVariant = "info" | "positive" | "negative";

export type AlertProps = ComponentPropsWithRef<"div"> & {
  variant?: AlertVariant;
};

const variantClasses: Record<AlertVariant, string> = {
  info: "border-border-strong bg-panel text-ink",
  positive: "border-positive bg-bg text-positive",
  negative: "border-negative bg-bg text-negative",
};

export function Alert({ className, role, variant = "info", ...props }: AlertProps) {
  return (
    <div
      {...props}
      role={role ?? (variant === "negative" ? "alert" : undefined)}
      className={[
        "min-w-0 border border-solid px-3 py-2 text-sm wrap-anywhere",
        variantClasses[variant],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    />
  );
}
