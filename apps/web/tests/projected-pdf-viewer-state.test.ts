import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const source = readFileSync(
  new URL("../components/projected-pdf-viewer.tsx", import.meta.url),
  "utf8",
);

test("PDF preview exposes document, page, timeout and retry states", () => {
  assert.match(source, /onLoadError=.*PDF 加载失败/);
  assert.match(source, /onRenderError=.*当前页渲染失败/);
  assert.match(source, /PREVIEW_TIMEOUT_MS = 12_000/);
  assert.match(source, /role=\{loadState\.phase === "error" \? "alert" : "status"\}/);
  assert.match(source, />\s*重新加载\s*</);
});

test("PDF preview becomes ready only after the requested page renders", () => {
  assert.match(source, /onLoadSuccess=.*setLoadState\(\{ phase: "page_loading"/s);
  assert.match(source, /onRenderSuccess=\{\(\) => setLoadState\(\{ phase: "ready", message: "" \}\)\}/);
  assert.match(source, /key=\{`\$\{fileUrl\}:\$\{retryToken\}`\}/);
});
