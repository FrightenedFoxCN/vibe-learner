import { test, expect } from "@playwright/test";
import { observeRequests } from "./api-fixture";

test("Scene draft survives immediate navigation and a full reload", async ({ page }) => {
  await observeRequests(page);
  await page.goto("/scene-setup");
  const name = page.getByRole("textbox", { name: "场景名称", exact: true });
  await name.fill("快速离页仍保留");
  await page.locator('a[href="/settings"]').first().click();
  await expect(page).toHaveURL(/\/settings$/);
  await page.locator('a[href="/scene-setup"]').first().click();
  await expect(name).toHaveValue("快速离页仍保留");
  await page.reload();
  await expect(name).toHaveValue("快速离页仍保留");
});
