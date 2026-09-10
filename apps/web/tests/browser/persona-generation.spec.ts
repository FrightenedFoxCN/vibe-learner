import { test, expect } from "@playwright/test";
import { observeRequests } from "./api-fixture";

test("Persona exact card count exposes the 1–24 limit and optional semantics", async ({ page }) => {
  await observeRequests(page);
  await page.goto("/persona-spectrum");
  const count = page.getByRole("spinbutton", { name: "精确卡片数量（可选）", exact: true });
  await expect(count).toBeVisible();
  await expect(count).toHaveAttribute("min", "1");
  await expect(count).toHaveAttribute("max", "24");
  await expect(count).toHaveAttribute("step", "1");
  await expect(count).toHaveAttribute("placeholder", "留空由模型决定，填写后精确生成 1–24 张");
  await expect(count).toHaveValue("");
});
