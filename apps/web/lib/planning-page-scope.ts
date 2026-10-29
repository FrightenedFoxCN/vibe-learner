import type { PlanningIntent, PlanningPageRange } from "@vibe-learner/shared";

export function parsePhysicalPdfRanges(text: string): PlanningPageRange[] {
  if (!text.trim()) return [];
  const parts = text.split(/[,，;；\n]/u);
  if (parts.length > 64) throw new Error("最多填写 64 段 PDF 物理页范围。");
  const ranges = parts
    .map((part) => {
      const match = /^\s*([0-9]+)(?:\s*[-–—]\s*([0-9]+))?\s*$/u.exec(part);
      if (!match)
        throw new Error("请输入 PDF 物理页，例如 100–103, 110。不要填写印刷页标签。");
      const pageStart = Number(match[1]),
        pageEnd = Number(match[2] ?? match[1]);
      if (
        !Number.isSafeInteger(pageStart) ||
        !Number.isSafeInteger(pageEnd) ||
        pageStart < 1 ||
        pageEnd < pageStart
      ) {
        throw new Error("PDF 页码必须从 1 开始，结束页不能小于起始页。");
      }
      return { pageStart, pageEnd };
    })
    .sort((left, right) => left.pageStart - right.pageStart);
  if (
    ranges.some(
      (range, index) => index > 0 && range.pageStart <= ranges[index - 1].pageEnd,
    )
  )
    throw new Error("PDF 物理页范围不能重叠。");
  return ranges;
}

export function physicalPageIntent(
  ranges: PlanningPageRange[],
): PlanningIntent | undefined {
  if (!ranges.length) return undefined;
  return {
    schemaVersion: "planning-intent-v1",
    pdfPageRanges: { status: "user_explicit", value: ranges },
    outlineTargets: { status: "unknown", value: null },
    sessionCount: { status: "unknown", value: null },
    minutesPerSession: { status: "unknown", value: null },
    outputLanguage: { status: "unknown", value: null },
  };
}

export const formatPhysicalPdfRanges = (ranges: PlanningPageRange[]) =>
  ranges
    .map((range) =>
      range.pageStart === range.pageEnd
        ? String(range.pageStart)
        : `${range.pageStart}–${range.pageEnd}`,
    )
    .join(", ");
