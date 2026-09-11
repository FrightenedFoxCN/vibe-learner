import { test, expect } from "@playwright/test";
import { observeRequests } from "./api-fixture";

test("independent: repeated keyboard cancellation preserves content and restores its origin", async ({ page }) => {
  const requests = await observeRequests(page);
  await page.goto("/scene-setup");
  const triggers = page.getByRole("button", { name: "删除当前层级", exact: true }).and(page.locator(":enabled"));
  const before = await triggers.count();
  expect(before).toBeGreaterThan(0);
  for (const cycle of [0, 1, 2]) {
    const origin = triggers.first();
    await origin.focus();
    await page.keyboard.press("Enter");
    const dialog = page.getByRole("dialog", { name: "确认删除层级？" });
    const cancel = dialog.getByRole("button", { name: "取消", exact: true });
    await expect(cancel).toBeFocused();
    for (let i = 0; i < 8; i++) {
      await page.keyboard.press(i < 4 ? "Tab" : "Shift+Tab");
      expect(await dialog.evaluate(el => el.contains(document.activeElement))).toBe(true);
    }
    if (cycle === 1) await page.keyboard.press("Enter");
    else await page.keyboard.press("Escape");
    await expect(dialog).toHaveCount(0);
    await expect(origin).toBeFocused();
    await expect(triggers).toHaveCount(before);
  }
  expect(requests.filter(r => r.method !== "GET" && !r.path.startsWith("/diagnostics"))).toEqual([]);
});

test("independent: native modal blocks background pointer and focus at narrow viewport", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await observeRequests(page);
  await page.goto("/scene-setup");
  const background = page.locator('a[href="/settings"]').first();
  await page.getByRole("button", { name: "删除当前层级", exact: true }).nth(1).click();
  const dialog = page.getByRole("dialog", { name: "确认删除层级？" });
  await expect(dialog).toHaveAccessibleDescription(/即将删除.*所有子层级与物体/);
  expect(await dialog.evaluate(el => el.matches(":modal"))).toBe(true);
  const box = await dialog.boundingBox();
  expect(box).not.toBeNull();
  expect(box!.x).toBeGreaterThanOrEqual(0);
  expect(box!.x + box!.width).toBeLessThanOrEqual(390);
  for (const button of await dialog.getByRole("button").all()) {
    const rect = await button.boundingBox();
    expect(rect!.height).toBeGreaterThanOrEqual(44);
    expect(rect!.width).toBeGreaterThanOrEqual(44);
  }
  await background.evaluate(el => {
    el.setAttribute("data-independent-clicks", "0");
    el.addEventListener("click", () => el.setAttribute("data-independent-clicks", "1"));
    (el as HTMLElement).focus();
  });
  expect(await dialog.evaluate(el => el.contains(document.activeElement))).toBe(true);
  const backgroundBox = await background.boundingBox();
  expect(backgroundBox).not.toBeNull();
  await page.mouse.click(backgroundBox!.x + 2, backgroundBox!.y + 2);
  await expect(background).toHaveAttribute("data-independent-clicks", "0");
  await expect(page).toHaveURL(/\/scene-setup$/);
  await expect(dialog).toBeVisible();
  await page.keyboard.press("Escape");
  await background.focus();
  await expect(background).toBeFocused();
});

test("independent: keyboard subtree deletion restores surviving heading and releases modal", async ({ page }) => {
  const requests = await observeRequests(page);
  await page.goto("/scene-setup");
  const triggers = page.getByRole("button", { name: "删除当前层级", exact: true }).and(page.locator(":enabled"));
  const count = await triggers.count();
  await triggers.first().focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog");
  await expect(dialog.getByRole("button", { name: "取消", exact: true })).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog.getByRole("button", { name: "确认删除", exact: true })).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(dialog).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "场景搭建", exact: true })).toBeFocused();
  expect(await triggers.count()).toBeLessThan(count);
  const background = page.locator('a[href="/settings"]').first();
  await background.focus();
  await expect(background).toBeFocused();
  expect(requests.filter(r => r.method !== "GET" && !r.path.startsWith("/diagnostics"))).toEqual([]);
});
