import assert from "node:assert/strict";
import { test } from "node:test";
import {
  formatStudyMarkdown,
  studyMarkdownFilename,
  type MarkdownAction,
} from "../lib/study-note-markdown.ts";

function apply(source: string, start: number, end: number, action: MarkdownAction) {
  const edit = formatStudyMarkdown(source, start, end, action);
  const result = source.slice(0, edit.from) + edit.text + source.slice(edit.to);
  return [
    result,
    result.slice(edit.selectionStart, edit.selectionEnd),
    edit.selectionStart,
  ];
}

test("inline formats preserve surrounding text and use DOM offsets", () => {
  assert.deepEqual(apply("学🚀习", 1, 3, "bold"), ["学**🚀**习", "🚀", 3]);
  assert.deepEqual(apply("学**🚀**习", 3, 5, "bold"), ["学🚀习", "🚀", 1]);
  assert.deepEqual(apply("", 0, 0, "math"), ["$x^2$", "x^2", 1]);
});

test("line tools exclude the following line and preserve blank first lines correctly", () => {
  assert.deepEqual(apply("a\nb\nc", 0, 4, "numbered"), [
    "1. a\n2. b\nc",
    "1. a\n2. b",
    0,
  ]);
  assert.deepEqual(apply("\nsecond", 0, 0, "task"), ["- [ ] \nsecond", "", 6]);
  assert.deepEqual(apply("before\nafter", 8, 8, "quote"), ["before\n> after", "", 10]);
});

test("code picks backtick delimiters and tables begin on their own block", () => {
  assert.deepEqual(apply("a`b", 0, 3, "code"), ["``a`b``", "a`b", 2]);
  assert.deepEqual(apply("```", 0, 3, "fence"), ["````\n```\n````\n", "```", 5]);
  assert.deepEqual(apply("A\nB", 2, 2, "table"), [
    "A\n\n| 列一 | 列二 |\n| --- | --- |\n| 内容 | 内容 |\n\nB",
    "列一",
    5,
  ]);
});

test("links escape label punctuation and select their replacement URL", () => {
  assert.deepEqual(apply("[text]", 0, 6, "link"), [
    "[\\[text\\]](https://example.com)",
    "https://example.com",
    11,
  ]);
});

test("the Markdown download name has one extension and no path delimiters", () => {
  assert.equal(studyMarkdownFilename("../教材:条件概率.MD"), "-教材-条件概率.md");
  assert.equal(studyMarkdownFilename("..."), "study-note.md");
});
