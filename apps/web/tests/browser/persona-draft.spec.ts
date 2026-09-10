import { test, expect } from "@playwright/test";
import { observeRequests } from "./api-fixture";

test("Persona dirty draft stays on rejected navigation and leaves only after confirmation", async ({ page }) => {
  await observeRequests(page);
  await page.goto("/persona-spectrum");
  const name = page.getByRole("textbox", { name: "名称", exact: true });
  await expect(name).toHaveValue("Fixture Mentor");
  await name.fill("Unsaved persona");
  page.once("dialog", dialog => dialog.dismiss());
  await page.locator('a[href="/settings"]').first().click();
  await expect(page).toHaveURL(/\/persona-spectrum$/);
  await expect(name).toHaveValue("Unsaved persona");
  page.once("dialog", dialog => dialog.accept());
  await page.locator('a[href="/settings"]').first().click();
  await expect(page).toHaveURL(/\/settings$/);
});
