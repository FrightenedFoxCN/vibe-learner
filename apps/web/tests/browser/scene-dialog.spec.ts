import { test, expect } from "@playwright/test";
import { observeRequests } from "./api-fixture";

test("Scene deletion traps keyboard focus, makes the background inert and restores focus on cancel", async ({ page }) => {
  await observeRequests(page);
  await page.goto("/scene-setup");
  const trigger = page.getByRole("button", { name: "删除当前层级", exact: true }).filter({ visible: true }).nth(1);
  await trigger.click();
  const dialog = page.getByRole("dialog", { name: "确认删除层级？" });
  const cancel = dialog.getByRole("button", { name: "取消", exact: true });
  const confirm = dialog.getByRole("button", { name: "确认删除", exact: true });
  await expect(cancel).toBeFocused();
  await page.keyboard.press("Shift+Tab"); await expect(confirm).toBeFocused();
  await page.keyboard.press("Tab"); await expect(cancel).toBeFocused();
  await page.keyboard.press("Tab"); await expect(confirm).toBeFocused();
  await page.keyboard.press("Tab"); await expect(cancel).toBeFocused();
  await page.locator('a[href="/settings"]').first().evaluate(element => (element as HTMLElement).focus());
  await expect(cancel).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toHaveCount(0);
  await expect(trigger).toBeFocused();
  await trigger.click();
  await dialog.getByRole("button", { name: "取消", exact: true }).click();
  await expect(trigger).toBeFocused();
});

test("confirming deletion removes the subtree and focuses the surviving Scene heading", async ({ page }) => {
  await observeRequests(page);
  await page.goto("/scene-setup");
  const triggers = page.getByRole("button", { name: "删除当前层级", exact: true });
  const initialCount = await triggers.count();
  await triggers.nth(1).click();
  await page.getByRole("dialog").getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "场景搭建", exact: true })).toBeFocused();
  expect(await triggers.count()).toBeLessThan(initialCount);
});
