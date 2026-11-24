/**
 * Repairs common layout mistakes from otherwise-valid model Markdown and
 * normalizes LaTeX math delimiters without mutating code or math spans.
 *
 * The source text remains untrusted prose: this only normalizes math
 * delimiters and structural line breaks, and never enables raw HTML.
 */

export interface NormalizeMathOptions {
  inline?: boolean;
}

type Segment = { kind: "prose"; text: string } | { kind: "protected"; text: string };

/**
 * Normalizes LaTeX math delimiters (`\(...\)`, `\[...\]`, and single-line
 * `$$...$$`) outside fenced/inline code blocks so `remark-math` v6 +
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
 * Normalizes model-generated chat Markdown while shielding fenced code blocks,
 * inline code spans, and math expressions from prose layout heuristics.
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

function tokenizeMarkdown(source: string, inline: boolean): Segment[] {
  const segments: Segment[] = [];
  let proseStart = 0;
  let i = 0;

  const flushProse = (end: number) => {
    if (end > proseStart) {
      segments.push({ kind: "prose", text: source.slice(proseStart, end) });
    }
  };

  while (i < source.length) {
    // 1. Fenced code block at start of line (including inside blockquotes or list items).
    if (i === 0 || source[i - 1] === "\n") {
      const fenceEnd = matchFencedCodeBlock(source, i);
      if (fenceEnd > i) {
        flushProse(i);
        segments.push({ kind: "protected", text: source.slice(i, fenceEnd) });
        i = fenceEnd;
        proseStart = i;
        continue;
      }
    }

    const ch = source[i];

    // 2. Inline code span (`...`).
    if (ch === "`") {
      const codeEnd = matchInlineCodeSpan(source, i);
      if (codeEnd > i) {
        flushProse(i);
        segments.push({ kind: "protected", text: source.slice(i, codeEnd) });
        i = codeEnd;
        proseStart = i;
        continue;
      }
      // Unclosed backtick run: consume the whole run as prose.
      while (i < source.length && source[i] === "`") i += 1;
      continue;
    }

    // 3. Backslash sequences: check \(...\) and \[...\] before skipping other escapes.
    if (ch === "\\") {
      const next = source[i + 1];
      if (next === "[") {
        const closeIndex = findUnescapedClose(source, i + 2, "\\]", true);
        if (closeIndex !== -1) {
          const inner = source.slice(i + 2, closeIndex);
          flushProse(i);
          segments.push({
            kind: "protected",
            text: formatDisplayMath(source, i, closeIndex + 2, inner, inline, true),
          });
          i = closeIndex + 2;
          proseStart = i;
          continue;
        }
      } else if (next === "(") {
        const closeIndex = findUnescapedClose(source, i + 2, "\\)", false);
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
      i += next !== undefined ? 2 : 1;
      continue;
    }

    // 4. Dollar math: $$...$$ (display) or $...$ (inline).
    if (ch === "$") {
      if (source[i + 1] === "$") {
        const closeIndex = findUnescapedClose(source, i + 2, "$$", true);
        if (closeIndex !== -1) {
          const inner = source.slice(i + 2, closeIndex);
          flushProse(i);
          segments.push({
            kind: "protected",
            text: formatDisplayMath(source, i, closeIndex + 2, inner, inline, false),
          });
          i = closeIndex + 2;
          proseStart = i;
          continue;
        }
        i += 2;
        continue;
      }

      const closeIndex = findInlineDollarClose(source, i + 1);
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

function matchFencedCodeBlock(source: string, lineStart: number): number {
  const lineEnd = source.indexOf("\n", lineStart);
  const firstLine = source.slice(lineStart, lineEnd === -1 ? source.length : lineEnd);
  const openMatch = firstLine.match(/^([ \t]*(?:>[ \t]*)*)(`{3,}|~{3,})(.*)$/);
  if (!openMatch) {
    return -1;
  }
  const fence = openMatch[2];
  const fenceChar = fence[0];
  const infoString = openMatch[3];
  // CommonMark: backtick fence info strings cannot contain backticks.
  if (fenceChar === "`" && infoString.includes("`")) {
    return -1;
  }
  const closeRe = new RegExp(
    `^[ \\t]*(?:>[ \\t]*)*${escapeRegExp(fenceChar)}{${fence.length},}[ \\t]*$`,
  );

  let pos = lineEnd === -1 ? source.length : lineEnd + 1;
  while (pos < source.length) {
    const nextEnd = source.indexOf("\n", pos);
    const line = source.slice(pos, nextEnd === -1 ? source.length : nextEnd);
    if (closeRe.test(line)) {
      return nextEnd === -1 ? source.length : nextEnd + 1;
    }
    if (nextEnd === -1) {
      return source.length;
    }
    pos = nextEnd + 1;
  }
  return source.length;
}

function matchInlineCodeSpan(source: string, start: number): number {
  let openLen = 0;
  while (start + openLen < source.length && source[start + openLen] === "`") {
    openLen += 1;
  }
  let pos = start + openLen;
  while (pos < source.length) {
    if (source[pos] === "`") {
      let runLen = 0;
      while (pos + runLen < source.length && source[pos + runLen] === "`") {
        runLen += 1;
      }
      if (runLen === openLen) {
        return pos + runLen;
      }
      pos += runLen;
      continue;
    }
    pos += 1;
  }
  return -1;
}

function findUnescapedClose(
  source: string,
  from: number,
  delimiter: string,
  allowBlankLines: boolean,
): number {
  let pos = from;
  while (pos < source.length) {
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

function findInlineDollarClose(source: string, from: number): number {
  let pos = from;
  while (pos < source.length) {
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
  const isInTableRow =
    isSingleLine &&
    /^[ \t]*(?:>[ \t]*)*\|/.test(beforeOnLine) &&
    afterOnLine.includes("|");

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
