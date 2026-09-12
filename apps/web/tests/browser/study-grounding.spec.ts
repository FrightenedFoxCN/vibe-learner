import { test, expect } from "@playwright/test";
import { populatedLearning } from "./learning-fixture";

test("Study Dialog exposes exact-memory syntax and preserves the source draft", async ({ page }, info) => {
  await populatedLearning(page);
  await page.goto("/study");
  const help = page.getByText("如何保存原文记忆", { exact: true });
  await expect(help).toBeVisible();
  await help.click();
  await expect(page.locator("pre").filter({ hasText: "/remember-verbatim my_note" })).toBeVisible();
  const source = "/remember-verbatim archive\n“Don’t rewrite 007.”\n这是引文。\n/end-remember";
  const input = page.getByRole("textbox", { name: /提问/ });
  await input.fill(source);
  await expect(input).toHaveValue(source);
  await info.attach("study-grounding.png", { body: await page.screenshot({ fullPage: true }), contentType: "image/png" });
});
