import { DOCUMENT_INPUT_LIMITS } from "@vibe-learner/shared/document-input-limits";

export function documentUploadError(file: { size: number }): string {
  return file.size > DOCUMENT_INPUT_LIMITS.upload_max_bytes
    ? "PDF 文件超过 64 MiB，请拆分或压缩后重新选择。"
    : "";
}
