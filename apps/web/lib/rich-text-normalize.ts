/**
 * Repairs common layout mistakes from otherwise-valid model Markdown and
 * normalizes LaTeX math delimiters without mutating code or math spans.
 *
 * The source text remains untrusted prose: this only normalizes math
 * delimiters and structural line breaks, and never enables raw HTML.
 */

import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

export interface NormalizeMathOptions {
  inline?: boolean;
}

type Segment = { kind: "prose"; text: string } | { kind: "protected"; text: string };

/**
 * Normalizes LaTeX math delimiters (`\(...\)`, `\[...\]`, and single-line
 * `$$...$$`) outside Markdown code and link syntax so `remark-math` v6 +
 * `rehype-katex` render them reliably.
 */
export function normalizeMathDelimiters(
  content: string,
  options: NormalizeMathOptions = {},
): string {
  const normalized = content.replace(/\r\n/g, "\n");
  return tokenizeMarkdown(normalized, Boolean(options.inline))
    .map((segment) => segment.text)
    .join("");
}

/**
 * Normalizes model-generated chat Markdown while shielding code, link syntax,
 * and math expressions from prose layout heuristics.
 */
export function normalizeRichTextContent(
  content: string,
  options: NormalizeMathOptions = {},
): string {
  const normalized = content.replace(/\r\n/g, "\n");
  const segments = tokenizeMarkdown(normalized, Boolean(options.inline));

  // Choose a collision-free placeholder prefix absent from the input.
  let sentinel = "\uE000RT";
  while (normalized.includes(sentinel)) {
    sentinel += "_";
  }

  const protectedValues: string[] = [];
  let proseWithPlaceholders = "";
  for (const segment of segments) {
    if (segment.kind === "protected") {
      const index = protectedValues.length;
      protectedValues.push(segment.text);
      proseWithPlaceholders += `${sentinel}${index}\uE001`;
    } else {
      proseWithPlaceholders += segment.text;
    }
  }

  const repaired = repairProseLayout(proseWithPlaceholders);
  if (!protectedValues.length) {
    return repaired;
  }

  const placeholderRe = new RegExp(`${escapeRegExp(sentinel)}(\\d+)\\uE001`, "g");
  return repaired.replace(
    placeholderRe,
    (_, indexText: string) => protectedValues[Number(indexText)] ?? "",
  );
}

function repairProseLayout(prose: string): string {
  return (
    prose
      // Some providers append numbered headings to the preceding sentence.
      // Render the identifiable heading label as an emphasized section lead
      // instead of exposing a literal `###` in persisted historic messages.
      .replace(
        /([。！？:：])\s+#{1,6}\s+(\d+\.\s+[^。\n]{1,120}?[：:？?])\s*/g,
        "$1\n\n**$2** ",
      )
      .replace(/([。！？:：])\s+#{1,6}\s+(\d+\.)\s*/g, "$1\n\n**$2** ")
      .replace(/([。！？:：])\s+#{1,6}\s+/g, "$1\n\n")
      .replace(/([:：])\s+(?=\d+\.\s+)/g, "$1\n\n")
      .replace(/([。！？])\s+(?=\d+\.\s+)/g, "$1\n\n")
      .replace(/([:：])\s+[*-]\s+/g, "$1\n\n- ")
      .replace(/([。；;])\s+[*-]\s+/g, "$1\n- ")
      .replace(/(\n\d+\.\s[^\n]*?[。！？；;：:])\s+[*-]\s+/g, "$1\n\n   - ")
      .replace(/([^\n])\n(\d+\.\s+)/g, "$1\n\n$2")
      .replace(/\n{3,}/g, "\n\n")
  );
}

interface SourceRange {
  start: number;
  end: number;
}

interface MarkdownNode {
  type: string;
  position?: { start: { offset?: number }; end: { offset?: number } };
  children?: readonly MarkdownNode[];
  referenceType?: string;
}

function collectMarkdownRanges(source: string) {
  const literal: SourceRange[] = [];
  const inlineLabels: SourceRange[] = [];
  // Micromark discards a leading BOM before counting source offsets.
  const bomLength = source.charCodeAt(0) === 0xfeff ? 1 : 0;
  const sourceOffset = (offset?: number) =>
    offset === undefined ? undefined : offset + bomLength;
  const add = (ranges: SourceRange[], start: number, end: number) => {
    if (start < end) ranges.push({ start, end });
  };

  const visit = (node: MarkdownNode) => {
    const start = sourceOffset(node.position?.start.offset);
    const end = sourceOffset(node.position?.end.offset);
    if (start !== undefined && end !== undefined) {
      switch (node.type) {
        case "code":
        case "inlineCode":
        case "definition":
        case "image":
        case "imageReference":
          add(literal, start, end);
          return;
        case "link":
        case "linkReference": {
          const first = sourceOffset(node.children?.[0]?.position?.start.offset);
          const last = sourceOffset(node.children?.at(-1)?.position?.end.offset);
          if (
            source[start] !== "[" || // An autolink has no independent label.
            (node.type === "linkReference" && node.referenceType !== "full") ||
            first === undefined ||
            last === undefined
          ) {
            add(literal, start, end);
            return;
          }
          // MDAST exposes offsets for the link and its label children, not for
          // the destination/title individually. Protect everything around the
          // actual label without guessing at parentheses or escapes in URLs.
          add(literal, start, first);
          add(inlineLabels, first, last);
          node.children?.forEach(visit);
          add(literal, last, end);
          return;
        }
      }
    }
    node.children?.forEach(visit);
  };

  // Reuse the renderer's parser and syntax extensions via its public sync
  // remark hook. Consume only source positions; give rehype an empty document.
  ReactMarkdown({
    children: source,
    remarkPlugins: [
      remarkGfm,
      remarkMath,
      () => (tree) => {
        visit(tree);
        tree.children = [];
      },
    ],
  });
  return { literal, inlineLabels };
}

function tokenizeMarkdown(source: string, inline: boolean): Segment[] {
  const { literal, inlineLabels } = collectMarkdownRanges(source);
  const segments: Segment[] = [];
  let proseStart = 0;
  let i = 0;
  let literalIndex = 0;
  let labelIndex = 0;

  const flushProse = (end: number) => {
    if (end > proseStart) {
      segments.push({ kind: "prose", text: source.slice(proseStart, end) });
    }
  };

  while (i < source.length) {
    const range = literal[literalIndex];
    if (range && i >= range.start) {
      flushProse(range.start);
      segments.push({ kind: "protected", text: source.slice(range.start, range.end) });
      i = range.end;
      proseStart = i;
      literalIndex += 1;
      continue;
    }
    const limit = range?.start ?? source.length;
    while (inlineLabels[labelIndex] && inlineLabels[labelIndex].end <= i)
      labelIndex += 1;
    const compact = inline || (inlineLabels[labelIndex]?.start ?? source.length) <= i;
    const ch = source[i];

    // Backslash sequences: check \(...\) and \[...\] before skipping other escapes.
    if (ch === "\\") {
      const next = i + 1 < limit ? source[i + 1] : undefined;
      if (next === "[") {
        const closeIndex = findUnescapedClose(source, i + 2, limit, "\\]", true);
        if (closeIndex !== -1) {
          const inner = source.slice(i + 2, closeIndex);
          flushProse(i);
          segments.push({
            kind: "protected",
            text: formatDisplayMath(source, i, closeIndex + 2, inner, compact, true),
          });
          i = closeIndex + 2;
          proseStart = i;
          continue;
        }
      } else if (next === "(") {
        const closeIndex = findUnescapedClose(source, i + 2, limit, "\\)", false);
        if (closeIndex !== -1) {
          const inner = source.slice(i + 2, closeIndex).trim();
          if (inner) {
            flushProse(i);
            segments.push({ kind: "protected", text: `$${inner}$` });
            i = closeIndex + 2;
            proseStart = i;
            continue;
          }
        }
      }
      // Skip escaped character pair (e.g. \\, \$, \(, \[ when unclosed).
      i = Math.min(i + 2, limit);
      continue;
    }

    // Dollar math: $$...$$ (display) or $...$ (inline).
    if (ch === "$") {
      if (i + 1 < limit && source[i + 1] === "$") {
        const closeIndex = findUnescapedClose(source, i + 2, limit, "$$", true);
        if (closeIndex !== -1) {
          const inner = source.slice(i + 2, closeIndex);
          flushProse(i);
          segments.push({
            kind: "protected",
            text: formatDisplayMath(source, i, closeIndex + 2, inner, compact, false),
          });
          i = closeIndex + 2;
          proseStart = i;
          continue;
        }
        i += 2;
        continue;
      }

      const closeIndex = findInlineDollarClose(source, i + 1, limit);
      if (closeIndex !== -1) {
        flushProse(i);
        segments.push({ kind: "protected", text: source.slice(i, closeIndex + 1) });
        i = closeIndex + 1;
        proseStart = i;
        continue;
      }
    }

    i += 1;
  }

  flushProse(source.length);
  return segments;
}

function findUnescapedClose(
  source: string,
  from: number,
  limit: number,
  delimiter: string,
  allowBlankLines: boolean,
): number {
  let pos = from;
  while (pos + delimiter.length <= limit) {
    if (!allowBlankLines && source[pos] === "\n" && source[pos + 1] === "\n") {
      return -1;
    }
    if (source.startsWith(delimiter, pos)) {
      return pos;
    }
    if (source[pos] === "\\") {
      pos += pos + 1 < source.length ? 2 : 1;
      continue;
    }
    pos += 1;
  }
  return -1;
}

function findInlineDollarClose(source: string, from: number, limit: number): number {
  let pos = from;
  while (pos < limit) {
    if (source[pos] === "\n" && source[pos + 1] === "\n") {
      return -1;
    }
    if (source[pos] === "\\") {
      pos += pos + 1 < source.length ? 2 : 1;
      continue;
    }
    if (source[pos] === "$") {
      if (source[pos + 1] === "$") {
        // Double dollar is not a valid single-dollar close.
        return -1;
      }
      if (pos === from) {
        return -1;
      }
      return pos;
    }
    pos += 1;
  }
  return -1;
}

function formatDisplayMath(
  source: string,
  openIndex: number,
  afterCloseIndex: number,
  inner: string,
  inline: boolean,
  fromBracket: boolean,
): string {
  const lineStart = source.lastIndexOf("\n", openIndex - 1) + 1;
  const lineEndIndex = source.indexOf("\n", afterCloseIndex);
  const lineEnd = lineEndIndex === -1 ? source.length : lineEndIndex;
  const beforeOnLine = source.slice(lineStart, openIndex);
  const afterOnLine = source.slice(afterCloseIndex, lineEnd);

  const isSingleLine = !inner.includes("\n");
  // GFM rows can omit either outer pipe. Avoid inserting block breaks on
  // lines that may be table rows, but ignore escaped pipes and the math body.
  const hasUnescapedPipe = (text: string) => /(?:^|[^\x5c])(?:\\)*\|/.test(text);
  const isInTableRow =
    isSingleLine && (hasUnescapedPipe(beforeOnLine) || hasUnescapedPipe(afterOnLine));

  if (inline || isInTableRow) {
    const compact = inner.trim();
    return compact ? `$$${compact}$$` : source.slice(openIndex, afterCloseIndex);
  }

  const onlyPrefixBefore = /^[ \t]*(?:>[ \t]*)*$/.test(beforeOnLine);
  const onlySpaceAfter = /^[ \t]*$/.test(afterOnLine);

  // Already a valid multiline `$$...$$` mathFlow block — preserve verbatim.
  if (!fromBracket && !isSingleLine && onlyPrefixBefore && onlySpaceAfter) {
    return source.slice(openIndex, afterCloseIndex);
  }

  const body = inner.replace(/^\n+|\n+$/g, "").trim();
  if (!body) {
    return source.slice(openIndex, afterCloseIndex);
  }

  const containerPrefix = inferContinuationPrefix(beforeOnLine);
  const formattedBody = body
    .split("\n")
    .map((line) => {
      if (!containerPrefix) return line;
      if (line.startsWith(containerPrefix)) return line;
      if (containerPrefix.includes(">")) {
        return containerPrefix + line.replace(/^[ \t]*(?:>[ \t]*)*/, "");
      }
      return containerPrefix + line;
    })
    .join("\n");

  const lead = onlyPrefixBefore
    ? ""
    : `\n${containerPrefix.trimEnd() ? `${containerPrefix.trimEnd()}\n` : "\n"}${containerPrefix}`;
  const trail = onlySpaceAfter
    ? ""
    : `\n${containerPrefix.trimEnd() ? `${containerPrefix.trimEnd()}\n` : "\n"}${containerPrefix}`;

  return `${lead}$$\n${formattedBody}\n${containerPrefix}$$${trail}`;
}

function inferContinuationPrefix(beforeOnLine: string): string {
  const quotePrefixMatch = beforeOnLine.match(/^([ \t]*(?:>[ \t]*)+)/);
  if (quotePrefixMatch) {
    const raw = quotePrefixMatch[1];
    return raw.endsWith(" ") ? raw : `${raw} `;
  }
  const listPrefixMatch = beforeOnLine.match(/^([ \t]*)(?:[-*+]|\d+\.)[ \t]+/);
  if (listPrefixMatch) {
    return " ".repeat(listPrefixMatch[0].length);
  }
  const indentMatch = beforeOnLine.match(/^([ \t]*)$/);
  if (indentMatch) {
    return indentMatch[1];
  }
  return "";
}

function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}
