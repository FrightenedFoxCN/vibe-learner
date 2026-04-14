import type { CSSProperties, ReactNode } from "react";

export type MaterialIconName =
  | "home"
  | "description"
  | "chat"
  | "person"
  | "account_tree"
  | "landscape"
  | "visibility"
  | "settings"
  | "bar_chart"
  | "chevron_left"
  | "chevron_right"
  | "expand_more"
  | "drag_indicator"
  | "close"
  | "arrow_upward"
  | "arrow_downward"
  | "lock"
  | "lock_open"
  | "auto_awesome"
  | "undo"
  | "add"
  | "delete"
  | "library_add"
  | "create_new_folder"
  | "subdirectory_arrow_right"
  | "replay"
  | "adjust"
  | "upload"
  | "arrow_forward";

interface MaterialIconProps {
  name: MaterialIconName;
  size?: number;
  style?: CSSProperties;
  title?: string;
}

export function MaterialIcon({
  name,
  size = 18,
  style,
  title,
}: MaterialIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden={title ? undefined : "true"}
      role={title ? "img" : undefined}
      style={{ display: "block", flexShrink: 0, ...style }}
    >
      {title ? <title>{title}</title> : null}
      {renderIcon(name)}
    </svg>
  );
}

function renderIcon(name: MaterialIconName): ReactNode {
  switch (name) {
    case "home":
      return (
        <>
          <path d="M4 10.5 12 4l8 6.5" />
          <path d="M6 9.5V20h4.75v-5.5h2.5V20H18V9.5" />
        </>
      );
    case "description":
      return (
        <>
          <path d="M7 3.5h7l4 4V20.5H7z" />
          <path d="M14 3.5v4h4" />
          <path d="M9.5 11h5" />
          <path d="M9.5 14.5h5" />
          <path d="M9.5 18h3.5" />
        </>
      );
    case "chat":
      return (
        <>
          <path d="M5 6.5h14v9H10l-5 4z" />
          <path d="M9 10.5h6" />
          <path d="M9 13.5h4.5" />
        </>
      );
    case "person":
      return (
        <>
          <circle cx="12" cy="8" r="3.25" />
          <path d="M5.5 19.5a6.5 6.5 0 0 1 13 0" />
        </>
      );
    case "account_tree":
      return (
        <>
          <circle cx="12" cy="6.5" r="2" />
          <circle cx="7" cy="17.5" r="2" />
          <circle cx="17" cy="17.5" r="2" />
          <path d="M12 8.5v4" />
          <path d="M7 12.5h10" />
          <path d="M7 12.5v3" />
          <path d="M17 12.5v3" />
        </>
      );
    case "landscape":
      return (
        <>
          <rect x="4" y="5" width="16" height="14" rx="1.5" />
          <circle cx="9" cy="10" r="1.25" />
          <path d="m6.5 17 4.25-4.5 3.25 3 3.5-4.5 1.5 2" />
        </>
      );
    case "visibility":
      return (
        <>
          <path d="M3.5 12s3.25-5 8.5-5 8.5 5 8.5 5-3.25 5-8.5 5-8.5-5-8.5-5Z" />
          <circle cx="12" cy="12" r="2.75" />
        </>
      );
    case "settings":
      return (
        <>
          <circle cx="12" cy="12" r="3" />
          <path d="M12 3.75v2.1" />
          <path d="M12 18.15v2.1" />
          <path d="M3.75 12h2.1" />
          <path d="M18.15 12h2.1" />
          <path d="m6.16 6.16 1.5 1.5" />
          <path d="m16.34 16.34 1.5 1.5" />
          <path d="m17.84 6.16-1.5 1.5" />
          <path d="m7.66 16.34-1.5 1.5" />
        </>
      );
    case "bar_chart":
      return (
        <>
          <path d="M5 19.5V11" />
          <path d="M12 19.5V7" />
          <path d="M19 19.5V4" />
          <path d="M3.5 19.5h17" />
        </>
      );
    case "chevron_left":
      return <path d="m14.5 6-6 6 6 6" />;
    case "chevron_right":
      return <path d="m9.5 6 6 6-6 6" />;
    case "expand_more":
      return <path d="m6 9 6 6 6-6" />;
    case "drag_indicator":
      return (
        <>
          <circle cx="9" cy="8" r="1.1" fill="currentColor" stroke="none" />
          <circle cx="15" cy="8" r="1.1" fill="currentColor" stroke="none" />
          <circle cx="9" cy="12" r="1.1" fill="currentColor" stroke="none" />
          <circle cx="15" cy="12" r="1.1" fill="currentColor" stroke="none" />
          <circle cx="9" cy="16" r="1.1" fill="currentColor" stroke="none" />
          <circle cx="15" cy="16" r="1.1" fill="currentColor" stroke="none" />
        </>
      );
    case "close":
      return (
        <>
          <path d="m7 7 10 10" />
          <path d="M17 7 7 17" />
        </>
      );
    case "arrow_upward":
      return (
        <>
          <path d="M12 19V7" />
          <path d="m7.5 11.5 4.5-4.5 4.5 4.5" />
        </>
      );
    case "arrow_downward":
      return (
        <>
          <path d="M12 5v12" />
          <path d="m16.5 12.5-4.5 4.5-4.5-4.5" />
        </>
      );
    case "lock":
      return (
        <>
          <rect x="6" y="11" width="12" height="9" rx="1.5" />
          <path d="M8.5 11V8.5a3.5 3.5 0 0 1 7 0V11" />
        </>
      );
    case "lock_open":
      return (
        <>
          <rect x="6" y="11" width="12" height="9" rx="1.5" />
          <path d="M8.5 11V9a3.5 3.5 0 0 1 6.1-2.3" />
        </>
      );
    case "auto_awesome":
      return (
        <>
          <path d="m12 5 1.6 4.4L18 11l-4.4 1.6L12 17l-1.6-4.4L6 11l4.4-1.6Z" />
          <path d="m18.5 4 .6 1.4 1.4.6-1.4.6-.6 1.4-.6-1.4-1.4-.6 1.4-.6Z" />
          <path d="m5.5 15 .8 1.8 1.7.7-1.7.7-.8 1.8-.7-1.8-1.8-.7 1.8-.7Z" />
        </>
      );
    case "undo":
      return (
        <>
          <path d="M9 8H5V4" />
          <path d="M5.5 8.5A8 8 0 1 1 6.75 18" />
        </>
      );
    case "add":
      return (
        <>
          <path d="M12 5v14" />
          <path d="M5 12h14" />
        </>
      );
    case "delete":
      return (
        <>
          <path d="M5 7h14" />
          <path d="M9 7V5h6v2" />
          <rect x="7" y="7" width="10" height="12" rx="1.5" />
          <path d="M10.5 10.5v5" />
          <path d="M13.5 10.5v5" />
        </>
      );
    case "library_add":
      return (
        <>
          <rect x="5" y="5" width="10" height="14" rx="1.5" />
          <path d="M9 3.5h10v14" />
          <path d="M10 12h6" />
          <path d="M13 9v6" />
        </>
      );
    case "create_new_folder":
      return (
        <>
          <path d="M4.5 8.5h15v8.25A1.75 1.75 0 0 1 17.75 18.5H6.25A1.75 1.75 0 0 1 4.5 16.75Z" />
          <path d="M4.5 8.5V7.25A1.75 1.75 0 0 1 6.25 5.5H9l1.75 2h7A1.75 1.75 0 0 1 19.5 9.25V10" />
          <path d="M12 11.5v4" />
          <path d="M10 13.5h4" />
        </>
      );
    case "subdirectory_arrow_right":
      return (
        <>
          <path d="M6 6v4c0 1.1.9 2 2 2h10" />
          <path d="m14 8 4 4-4 4" />
        </>
      );
    case "replay":
      return (
        <>
          <path d="M19.5 4.5v5h-5" />
          <path d="M19.5 9.5a7.5 7.5 0 1 0 1.9 5" />
        </>
      );
    case "adjust":
      return (
        <>
          <circle cx="12" cy="12" r="6.5" />
          <circle cx="12" cy="12" r="2.5" fill="currentColor" stroke="none" />
        </>
      );
    case "upload":
      return (
        <>
          <path d="M12 16V6" />
          <path d="m8 10 4-4 4 4" />
          <path d="M5 18.5h14" />
        </>
      );
    case "arrow_forward":
      return (
        <>
          <path d="M5 12h14" />
          <path d="m13 7 5 5-5 5" />
        </>
      );
    default:
      return null;
  }
}
