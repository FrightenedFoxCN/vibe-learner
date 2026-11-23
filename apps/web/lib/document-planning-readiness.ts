import type { DocumentRecord } from "@vibe-learner/shared";

export function documentPlanningTextBlockReason({
  chunkCount,
  ocrStatus,
}: {
  chunkCount: number;
  ocrStatus: DocumentRecord["ocrStatus"] | null;
}): string {
  if (chunkCount !== 0) return "";
  const reason = ocrStatus === "unavailable" ? "OCR 不可用，" : "";
  return (
    reason +
    "未从教材提取到可用文本，无法生成教材计划。请重新导出含文本层的 PDF，或选择「仅学习目标」。"
  );
}
