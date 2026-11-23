import type { ComponentPropsWithRef } from "react";

export type ButtonVariant = "primary" | "secondary" | "danger";

export type ButtonProps = ComponentPropsWithRef<"button"> & {
  variant?: ButtonVariant;
};

const variantClasses: Record<ButtonVariant, string> = {
  primary:
    "border-accent bg-accent text-bg enabled:hover:border-accent-hover enabled:hover:bg-accent-hover",
  secondary: "border-border-strong bg-bg text-ink enabled:hover:bg-panel",
  danger:
    "border-danger bg-danger text-bg enabled:hover:bg-[color-mix(in_srgb,var(--danger),var(--ink)_12%)]",
};

export function Button({
  className,
  type = "button",
  variant = "secondary",
  ...props
}: ButtonProps) {
  return (
    <button
      {...props}
      type={type}
      className={[
        "inline-flex min-h-11 min-w-11 appearance-none items-center justify-center gap-2 border border-solid px-3 py-2 text-sm font-semibold",
        "cursor-pointer focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent disabled:cursor-not-allowed disabled:opacity-50",
        variantClasses[variant],
        className,
      ]
        .filter(Boolean)
        .join(" ")}
    />
  );
}
