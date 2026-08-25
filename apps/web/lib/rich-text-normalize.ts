/**
 * Repairs common layout mistakes from otherwise-valid model Markdown.
 *
 * The source text remains untrusted prose: this only adds structural line
 * breaks and never enables raw HTML.
 */
export function normalizeRichTextContent(content: string) {
  return content
    .replace(/\r\n/g, "\n")
    // Some providers append numbered headings to the preceding sentence.
    // Render the identifiable heading label as an emphasized section lead
    // instead of exposing a literal `###` in persisted historic messages.
    .replace(
      /([。！？:：])\s+#{1,6}\s+(\d+\.\s+[^。\n]{1,120}?[：:？?])\s*/g,
      "$1\n\n**$2** "
    )
    .replace(/([。！？:：])\s+#{1,6}\s+(\d+\.)\s*/g, "$1\n\n**$2** ")
    .replace(/([。！？:：])\s+#{1,6}\s+/g, "$1\n\n")
    .replace(/([:：])\s+(?=\d+\.\s+)/g, "$1\n\n")
    .replace(/([。！？])\s+(?=\d+\.\s+)/g, "$1\n\n")
    .replace(/([:：])\s+[*-]\s+/g, "$1\n\n   - ")
    .replace(/([。；;])\s+[*-]\s+/g, "$1\n   - ")
    .replace(/(\n\d+\.\s[^\n]*?)\s+[*-]\s+/g, "$1\n\n   - ")
    .replace(/\n\s*[*-]\s+/g, "\n   - ")
    .replace(/([^\n])\n(\d+\.\s+)/g, "$1\n\n$2")
    .replace(/\n{3,}/g, "\n\n");
}
