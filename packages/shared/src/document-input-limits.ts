/** Browser mirror of document-input-limits-v1; Python owns server enforcement. */
export const DOCUMENT_INPUT_LIMITS = Object.freeze({
  contract_version: "document-input-limits-v1",
  upload_max_bytes: 64 * 1024 * 1024,
  multipart_overhead_bytes: 1024 * 1024,
  max_physical_pages: 512,
  max_text_unit_chars: 65_536,
  oversized_unit_policy: "preserve_until_hard_limit",
} as const);
