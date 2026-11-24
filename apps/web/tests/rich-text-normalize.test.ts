import assert from "node:assert/strict";
import { test } from "node:test";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";
import rehypeKatex from "rehype-katex";
import {
  normalizeMathDelimiters,
  normalizeRichTextContent,
} from "../lib/rich-text-normalize.ts";

function renderMarkdown(markdown: string, inline = false) {
  const normalized = normalizeRichTextContent(markdown, { inline });
  const html = renderToStaticMarkup(
    React.createElement(
      ReactMarkdown,
      {
        remarkPlugins: [remarkGfm, remarkMath],
        rehypePlugins: [[rehypeKatex, { trust: false, strict: false }]],
      },
      normalized,
    ),
  );
  return {
    normalized,
    html,
    katexCount: (html.match(/class="katex"/g) || []).length,
    displayCount: (html.match(/class="katex-display"/g) || []).length,
    errorCount: (html.match(/katex-error/g) || []).length,
  };
}

test("numbered list items with minus or star inside math stay intact", () => {
  const source = [
    "推导步骤如下：",
    "1. 先计算 $a - b$ 的结果",
    "2. 再展开 $(x - y)^2 = x^2 - 2xy + y^2$",
    "3. 检验 $f : -x \\mapsto y$ 以及 $u \\; - v = 0$ 与 $A : * \\to *$",
  ].join("\n");
  const { normalized, html, katexCount, errorCount } = renderMarkdown(source);
  assert.equal(errorCount, 0);
  assert.equal(katexCount, 5);
  assert.ok(!html.includes("<ul>"), "should not split math minus into nested <ul>");
  assert.ok(normalized.includes("$a - b$"));
  assert.ok(normalized.includes("$(x - y)^2 = x^2 - 2xy + y^2$"));
  assert.ok(normalized.includes("$u \\; - v = 0$"));
  assert.ok(normalized.includes("$A : * \\to *$"));
});

test("backslash LaTeX delimiters render as inline and block KaTeX", () => {
  const source = [
    "特征方程 \\(\\det(A - \\lambda I) = 0\\) 对应分布：",
    "\\[",
    "\\frac{1}{\\sqrt{2\\pi\\sigma^2}} \\exp\\left(-\\frac{(x - \\mu)^2}{2\\sigma^2}\\right)",
    "\\]",
  ].join("\n");
  const { normalized, html, katexCount, displayCount, errorCount } =
    renderMarkdown(source);
  assert.equal(errorCount, 0);
  assert.equal(katexCount, 2);
  assert.equal(displayCount, 1);
  const withoutMathMl = html.replace(/<span class="katex-mathml">.*?<\/span>/gs, "");
  assert.ok(!withoutMathMl.includes("\\det"));
  assert.ok(!withoutMathMl.includes("\\frac"));
  assert.ok(normalized.includes("$\\det(A - \\lambda I) = 0$"));
});

test("single-line double-dollar equations upgrade to display math outside tables and inline mode", () => {
  const standalone = renderMarkdown("结论：\n$$E = mc^2$$\n继续说明。");
  assert.equal(standalone.katexCount, 1);
  assert.equal(standalone.displayCount, 1);
  assert.equal(standalone.errorCount, 0);

  const midParagraph = renderMarkdown("结论：$$E = mc^2$$ 这很重要。");
  assert.equal(midParagraph.katexCount, 1);
  assert.equal(midParagraph.displayCount, 1);
  assert.equal(midParagraph.errorCount, 0);

  const inTable = renderMarkdown(
    "| 项 | 公式 |\n| --- | --- |\n| 质能 | $$E = mc^2$$ |",
  );
  assert.equal(inTable.katexCount, 1);
  assert.equal(inTable.errorCount, 0);
  assert.ok(inTable.html.includes("<table>"));

  for (const row of ["质能 | $$E = mc^2$$", "| 质能 | $$E = mc^2$$"]) {
    const table = renderMarkdown("项 | 公式\n--- | ---\n" + row);
    assert.match(table.html, /<table>/);
    assert.equal(table.katexCount, 1);
    assert.equal(table.displayCount, 0);
  }

  const inlineOption = renderMarkdown("A. \\(x - y = 0\\) 与 $$a + b$$", true);
  assert.equal(inlineOption.katexCount, 2);
  assert.equal(inlineOption.displayCount, 0);
  assert.equal(inlineOption.errorCount, 0);
});

test("fenced code blocks, inline code spans, and nested bullet lists are preserved", () => {
  const source = [
    "代码保持原样：",
    "```python",
    "x = a",
    "- b",
    "* c",
    "1. d",
    "$not_math$",
    "\\(also_not_math\\)",
    "```",
    "",
    "行内代码 `$x - y$` 与 `\\(z\\)` 也不转换。",
    "",
    "- 第一层 $a$",
    "  - 第二层 $b$",
    "    - 第三层 $c$",
  ].join("\n");
  const { normalized, html, katexCount, errorCount } = renderMarkdown(source);
  assert.equal(errorCount, 0);
  assert.equal(katexCount, 3);
  assert.ok(
    normalized.includes("\n- b\n* c\n1. d\n$not_math$\n\\(also_not_math\\)\n```"),
  );
  assert.ok(normalized.includes("`$x - y$`"));
  assert.ok(normalized.includes("`\\(z\\)`"));
  assert.ok(normalized.includes("- 第一层 $a$\n  - 第二层 $b$\n    - 第三层 $c$"));
  assert.ok(html.includes("<code>$x - y$</code>"));
});

test("tilde fence opened on a list marker protects its body", () => {
  const source =
    "- ~~~text\n  \\(not math\\)\n  $$still code$$\n  ~~~\n\nOutside \\(x\\)";
  const { html, katexCount } = renderMarkdown(source);
  assert.equal(katexCount, 1);
  assert.match(html, /\$\$still code\$\$/);
  assert.ok(html.includes("\\(not math\\)"));
});

test("normalizeMathDelimiters leaves note Markdown structure untouched while supporting backslash delimiters", () => {
  const note = "1. 步骤 $a - b$\n- 清单 \\(x^2\\)\n\\[y = kx + b\\]";
  const normalized = normalizeMathDelimiters(note);
  assert.equal(normalized, "1. 步骤 $a - b$\n- 清单 $x^2$\n$$\ny = kx + b\n$$");
});

test("escaped backslashes and dollars do not falsely open math", () => {
  const res = renderMarkdown("价格 \\$100 到 \\$200，字面量 \\\\(not math\\\\)。");
  assert.equal(res.katexCount, 0);
  assert.equal(res.errorCount, 0);
});

test("historic inline heading repair still works outside math and code", () => {
  const res = renderMarkdown("总结如下： ### 1. 核心结论：先看定义。 ### 2. 下一步");
  assert.ok(res.normalized.includes("**1. 核心结论：**"));
  assert.ok(res.normalized.includes("**2.**"));
});

test("only parser-recognized indented code is shielded from normalization", () => {
  const code = "    \\(not math\\)\n\t$$also not math$$";
  const source = "Before\n    still prose \\(x\\)\n\n" + code + "\n\nAfter \\(y\\)";
  for (const normalize of [normalizeMathDelimiters, normalizeRichTextContent]) {
    assert.equal(
      normalize(source),
      "Before\n    still prose $x$\n\n" + code + "\n\nAfter $y$",
    );
  }
  const { html, katexCount, errorCount } = renderMarkdown(source);
  assert.ok(
    html.includes("<pre><code>\\(not math\\)\n$$also not math$$\n</code></pre>"),
  );
  assert.equal(katexCount, 2);
  assert.equal(errorCount, 0);
});

test("link resources keep their dollar delimiters while label and prose math still render", () => {
  const destination = '(https://example.com/a(b)/$$sku$$ "标题： - $$title$$")';
  const secondLink = "[other](<https://example.com/$$other$$>)";
  const source =
    "[label \\(x\\) and $$y$$]" + destination + " / " + secondLink + " \\(z\\)";
  for (const normalize of [normalizeMathDelimiters, normalizeRichTextContent]) {
    assert.equal(
      normalize(source),
      "[label $x$ and $$y$$]" + destination + " / " + secondLink + " $z$",
    );
  }
  assert.equal(
    normalizeMathDelimiters("\uFEFF" + source),
    "\uFEFF[label $x$ and $$y$$]" + destination + " / " + secondLink + " $z$",
  );
  const { html, katexCount, displayCount, errorCount } = renderMarkdown(source);
  assert.ok(html.includes('href="https://example.com/a(b)/$$sku$$"'));
  assert.ok(html.includes('title="标题： - $$title$$"'));
  assert.ok(html.includes('href="https://example.com/$$other$$"'));
  assert.equal(katexCount, 3);
  assert.equal(displayCount, 0);
  assert.equal(errorCount, 0);
});

test("unclosed fences end at their quote depth without swallowing outside LaTeX", () => {
  const fenced = "> > ```text\n> > \\(not math\\)\n> > $$still code$$";
  const source = fenced + "\n> Outer \\(x\\)\n\nAfter \\[y\\]";
  for (const normalize of [normalizeMathDelimiters, normalizeRichTextContent]) {
    const normalized = normalize(source);
    assert.ok(normalized.startsWith(fenced + "\n> Outer $x$"));
    assert.ok(normalized.endsWith("\n\n$$\ny\n$$"));
  }
  const { html, katexCount, displayCount, errorCount } = renderMarkdown(source);
  assert.ok(html.includes("\\(not math\\)\n$$still code$$"));
  assert.equal(katexCount, 2);
  assert.equal(displayCount, 1);
  assert.equal(errorCount, 0);
});
