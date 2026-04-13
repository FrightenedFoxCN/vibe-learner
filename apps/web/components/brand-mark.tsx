import type { CSSProperties, SVGProps } from "react";

interface BrandMarkProps extends SVGProps<SVGSVGElement> {
  size?: number;
}

export function BrandMark({ size = 32, style, ...props }: BrandMarkProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 128 128"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      aria-hidden="true"
      style={style}
      {...props}
    >
      <defs>
        <linearGradient id="brand-mark-bg" x1="16" y1="12" x2="112" y2="116" gradientUnits="userSpaceOnUse">
          <stop stopColor="#0A5560" />
          <stop offset="0.55" stopColor="#0A6772" />
          <stop offset="1" stopColor="#15909B" />
        </linearGradient>
        <linearGradient id="brand-mark-sheen" x1="26" y1="18" x2="96" y2="88" gradientUnits="userSpaceOnUse">
          <stop stopColor="rgba(255,255,255,0.24)" />
          <stop offset="1" stopColor="rgba(255,255,255,0)" />
        </linearGradient>
      </defs>

      <rect x="8" y="8" width="112" height="112" rx="30" fill="url(#brand-mark-bg)" />
      <rect x="16" y="16" width="96" height="96" rx="24" fill="url(#brand-mark-sheen)" />

      <path
        d="M34 38.5C45 36.25 54.5 38.5 62.5 44.25V83.5C54.75 78.25 45.25 76.5 34 78.75V38.5Z"
        fill="rgba(247,243,233,0.18)"
        stroke="#F7F3E9"
        strokeWidth="4.5"
        strokeLinejoin="round"
      />
      <path
        d="M94 38.5C83 36.25 73.5 38.5 65.5 44.25V83.5C73.25 78.25 82.75 76.5 94 78.75V38.5Z"
        fill="rgba(247,243,233,0.18)"
        stroke="#F7F3E9"
        strokeWidth="4.5"
        strokeLinejoin="round"
      />

      <path
        d="M43 74L54 62L67 65L82 49"
        stroke="#F7F3E9"
        strokeWidth="7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle cx="43" cy="74" r="5.5" fill="#F7F3E9" />
      <circle cx="54" cy="62" r="5.5" fill="#F7F3E9" />
      <circle cx="67" cy="65" r="5.5" fill="#F7F3E9" />
      <circle cx="82" cy="49" r="7.5" fill="#F29B63" stroke="#FFE7CF" strokeWidth="3" />

      <path
        d="M64 45V84"
        stroke="rgba(247,243,233,0.56)"
        strokeWidth="3"
        strokeLinecap="round"
      />
      <path
        d="M34 87.5C45 84.75 54.5 85 62.5 89C70.5 85 80 84.75 94 87.5"
        stroke="rgba(247,243,233,0.72)"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export const brandMarkStyle: CSSProperties = {
  display: "block",
};
