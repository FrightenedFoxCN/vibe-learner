import type { OcrStatus } from "@vibe-learner/shared";

const OCR_STATUS_LABELS: Record<OcrStatus, string> = {
  pending: "等待处理",
  not_required: "不需要 OCR",
  completed: "OCR 已完成",
  fallback_used: "已使用 OCR 补充",
  forced: "强制 OCR 已完成",
  required: "需要 OCR，尚未完成",
  partial: "部分页面 OCR 降级",
  unavailable: "OCR 不可用",
  failed: "OCR 失败"
};

export function formatOcrStatus(status: OcrStatus): string {
  return OCR_STATUS_LABELS[status];
}
