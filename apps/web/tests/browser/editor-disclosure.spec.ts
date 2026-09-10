import { test, expect } from "@playwright/test";
import { observeRequests } from "./api-fixture";

test("Persona keeps the secondary library collapsed with explicit disclosure semantics", async ({ page }) => {
  await observeRequests(page);
  await page.goto("/persona-spectrum");
  const library = page.getByRole("button", { name: "人格库", exact: true });
  await expect(library).toHaveAttribute("aria-expanded", "false");
  await library.click();
  await expect(library).toHaveAttribute("aria-expanded", "true");
  await expect(page.getByPlaceholder(/搜索人格/)).toBeVisible();
});

test("Scene descendant disclosure persists across navigation and reload with a 44px control", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await observeRequests(page);
  await page.goto("/scene-setup");
  await expect(page.getByRole("button", { name: "可复用节点库", exact: true })).toHaveAttribute("aria-expanded", "false");
  const collapsed = page.getByRole("button", { name: /^展开.*的子层和物体$/ }).first();
  const label = await collapsed.getAttribute("aria-label");
  const expandedLabel = label!.replace(/^展开/, "收起");
  const box = await collapsed.boundingBox();
  expect(box!.width).toBeGreaterThanOrEqual(44);
  expect(box!.height).toBeGreaterThanOrEqual(44);
  await collapsed.click();
  const expanded = page.getByRole("button", { name: expandedLabel, exact: true });
  await expect(expanded).toHaveAttribute("aria-expanded", "true");
  await page.locator('a[href="/settings"]').first().click();
  await page.locator('a[href="/scene-setup"]').first().click();
  await expect(expanded).toHaveAttribute("aria-expanded", "true");
  await page.reload();
  await expect(expanded).toHaveAttribute("aria-expanded", "true");
});
