import assert from "node:assert/strict";
import test from "node:test";

import { normalizeRichTextContent } from "../lib/rich-text-normalize.ts";

test("repairs historic inline Markdown headings without exposing hash markers", () => {
  const content = [
    "先说明概念。 ### 1. 概念溯源：从句法范畴到音系范畴 在经典句法学中，",
    "我们讨论动词的选择限制。 ### 2. 形式化过程：局部对齐框架 在符号形态学中，",
    "继续观察。 ### 3. 支撑依据：为什么必须是次范畴化？ 教材给出三点依据。",
  ].join(" ");

  const normalized = normalizeRichTextContent(content);

  assert.doesNotMatch(normalized, /###/);
  assert.match(normalized, /\*\*1\. 概念溯源：\*\* 从句法范畴到音系范畴/);
  assert.match(normalized, /\*\*2\. 形式化过程：\*\* 局部对齐框架/);
  assert.match(normalized, /\*\*3\. 支撑依据：\*\* 为什么必须是次范畴化？/);
});

test("preserves already-valid Markdown headings", () => {
  const content = "### 1. 正确标题\n\n正文说明。\n\n- 第一项\n- 第二项";

  const normalized = normalizeRichTextContent(content);

  assert.match(normalized, /^### 1\. 正确标题/m);
  assert.doesNotMatch(normalized, /\*\*1\. 正确标题\*\*/);
});
