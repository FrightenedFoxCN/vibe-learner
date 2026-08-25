import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

const pageSource = readFileSync(
  new URL("../components/study-dialog-page.tsx", import.meta.url),
  "utf8",
);

test("Study Dialog replaces its disabled console with a focusable Plan CTA", () => {
  const mainStageStart = pageSource.indexOf('<section style={styles.mainStage}>');
  const previewStart = pageSource.indexOf("{isHydrated ?", mainStageStart);
  const mainStage = pageSource.slice(mainStageStart, previewStart);

  assert.ok(mainStageStart >= 0 && previewStart > mainStageStart);
  assert.ok(mainStage.includes("isHydrated && !planHistoryItems.length ?"));
  assert.ok(mainStage.includes("先创建或选择学习计划"));
  assert.ok(mainStage.includes('AppLink path="/plan"'));
  assert.ok(mainStage.includes("前往计划工作区"));
  assert.match(mainStage, /\) : \(\s*<StudyConsole/);
  assert.ok(pageSource.includes("minHeight: 44"));
});
