import { expect, test } from "@playwright/test";

import { populatedLearning } from "./learning-fixture";

test("Plan Workspace uses wide space and exposes explicit form labels", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const fixture = await populatedLearning(page);
  fixture.plan.schedule[0].focus = "Definition 2.1 · PDF 100–103 · X ×_Y Y′ · ".repeat(18);
  await page.goto("/plan");
  await expect(page.getByText("Historical Course", { exact: true }).first()).toBeVisible();

  const layout = await page.locator(".plan-content-grid").evaluate((grid) => {
    const setup = grid.querySelector(".plan-setup-shell")!.getBoundingClientRect();
    const main = grid.querySelector(".plan-main-column")!.getBoundingClientRect();
    const whole = grid.getBoundingClientRect();
    return { wholeWidth: whole.width, setupWidth: setup.width, mainWidth: main.width, gap: main.left - setup.right };
  });
  expect(layout.wholeWidth).toBeGreaterThan(1000);
  expect(layout.mainWidth).toBeGreaterThan(layout.setupWidth * 1.5);
  expect(layout.gap).toBeGreaterThanOrEqual(20);

  const focus = page.getByText(/Definition 2\.1/).first();
  await expect(focus).toBeVisible();
  expect(await focus.evaluate((node) => ({
    wraps: getComputedStyle(node).whiteSpace === "pre-wrap",
    contained: node.scrollWidth <= node.clientWidth,
    selectable: getComputedStyle(node).userSelect === "text",
  }))).toEqual({ wraps: true, contained: true, selectable: true });

  for (const [id, label] of [
    ["plan-persona", "教师人格"],
    ["plan-scene", "计划场景"],
    ["plan-generation-mode", "创建方式"],
    ["plan-document-file", "教材文件（PDF）"],
    ["plan-objective", "学习目标"],
  ] as const) {
    const control = page.locator(`#${id}`);
    await expect(control).toHaveCount(1);
    await expect(page.locator(`label[for="${id}"]`, { hasText: label })).toHaveCount(1);
  }
  await expect(page.getByRole("textbox", { name: "学习目标", exact: true })).toBeVisible();
});

test("Plan Workspace shows a long PDF filename once with an inspectable full value", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await populatedLearning(page);
  await page.goto("/plan");
  const filename = `${"algebraic-geometry-reference-".repeat(8)}volume-one.pdf`;
  await page.locator("#plan-document-file").setInputFiles({
    name: filename,
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 test"),
  });

  const filenameNode = page.locator(".plan-file-name");
  await expect(filenameNode).toHaveText(filename);
  await expect(filenameNode).toHaveAttribute("title", filename);
  await expect(page.getByText(filename, { exact: true })).toHaveCount(1);
  expect(await filenameNode.evaluate((node) => node.scrollWidth > node.clientWidth)).toBe(true);
});
