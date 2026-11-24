export type MarkdownAction =
  | "heading"
  | "bold"
  | "italic"
  | "strike"
  | "quote"
  | "bullet"
  | "numbered"
  | "task"
  | "link"
  | "code"
  | "fence"
  | "table"
  | "math";

export interface MarkdownEdit {
  from: number;
  to: number;
  text: string;
  selectionStart: number;
  selectionEnd: number;
}

export function formatStudyMarkdown(
  source: string,
  start: number,
  end: number,
  action: MarkdownAction,
): MarkdownEdit {
  const selected = source.slice(start, end);
  function edit(
    from: number,
    to: number,
    text: string,
    offset = 0,
    length = text.length,
  ) {
    return {
      from,
      to,
      text,
      selectionStart: from + offset,
      selectionEnd: from + offset + length,
    };
  }
  function wrap(left: string, right: string, placeholder: string) {
    if (
      selected &&
      source.slice(start - left.length, start) === left &&
      source.slice(end, end + right.length) === right
    ) {
      return edit(start - left.length, end + right.length, selected);
    }
    const inner = selected || placeholder;
    return edit(start, end, left + inner + right, left.length, inner.length);
  }
  function block(body: string, cursor?: { offset: number; length: number }) {
    const left = source.slice(0, start);
    const right = source.slice(end);
    const before =
      !left || left.endsWith("\n\n") ? "" : left.endsWith("\n") ? "\n" : "\n\n";
    const after = !right
      ? "\n"
      : right.startsWith("\n\n")
        ? ""
        : right.startsWith("\n")
          ? "\n"
          : "\n\n";
    return edit(
      start,
      end,
      before + body + after,
      before.length + (cursor?.offset ?? body.length),
      cursor?.length ?? 0,
    );
  }
  switch (action) {
    case "bold":
      return wrap("**", "**", "粗体");
    // A different marker from bold also makes nested emphasis unambiguous.
    case "italic":
      return wrap("_", "_", "斜体");
    case "strike":
      return wrap("~~", "~~", "删除线");
    case "math":
      return wrap("$", "$", "x^2");
    case "code": {
      const ticks = "`".repeat(
        1 + Math.max(0, ...(selected.match(/`+/g) ?? []).map((run) => run.length)),
      );
      const padding = /^[` ]|[` ]$/.test(selected) ? " " : "";
      return wrap(ticks + padding, padding + ticks, "代码");
    }
    case "link": {
      const label =
        selected.replace(/[\\\[\]]/g, "\\$&").replace(/\r?\n/g, " ") || "链接文字";
      const url = "https://example.com";
      return edit(start, end, `[${label}](${url})`, label.length + 3, url.length);
    }
    case "fence": {
      const fence = "`".repeat(
        Math.max(
          3,
          1 + Math.max(0, ...(selected.match(/`+/g) ?? []).map((run) => run.length)),
        ),
      );
      const code = selected || "代码";
      return block(fence + "\n" + code + "\n" + fence, {
        offset: fence.length + 1,
        length: code.length,
      });
    }
    case "table": {
      const heading = "列一";
      return block("| 列一 | 列二 |\n| --- | --- |\n| 内容 | 内容 |", {
        offset: 2,
        length: heading.length,
      });
    }
    default: {
      const from = start === 0 ? 0 : source.lastIndexOf("\n", start - 1) + 1;
      // A selection ending at the next line's start does not include that line.
      const nextBreak = source.indexOf(
        "\n",
        end > start && source[end - 1] === "\n" ? end - 1 : end,
      );
      const to = nextBreak < 0 ? source.length : nextBreak;
      const lines = source.slice(from, to);
      const prefix = (index: number) =>
        action === "heading"
          ? "## "
          : action === "quote"
            ? "> "
            : action === "task"
              ? "- [ ] "
              : action === "numbered"
                ? `${index + 1}. `
                : "- ";
      const body = lines
        .split("\n")
        .map((line, index) => prefix(index) + line)
        .join("\n");
      return edit(
        from,
        to,
        body,
        start === end ? start - from + prefix(0).length : 0,
        start === end ? 0 : body.length,
      );
    }
  }
}

export function studyMarkdownFilename(title: string): string {
  const safe = title
    .replace(/[<>:"/\\|?*\u0000-\u001f]/g, "-")
    .replace(/^[.\s]+|[.\s]+$/g, "")
    .replace(/\.md$/i, "");
  return (safe || "study-note") + ".md";
}
