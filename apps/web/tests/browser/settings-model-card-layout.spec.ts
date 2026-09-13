import { expect, test } from "@playwright/test";

import { observeRequests } from "./api-fixture";

const api = "http://127.0.0.1:18999";

test("Settings model-card headings keep one font metric and baseline", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await observeRequests(page);
  await page.route(`${api}/runtime-settings`, route => route.fulfill({
    json: {
      plan_provider: "litellm",
      openai_plan_model: "MiniMax-M3",
      openai_chat_model: "MiniMax-M3",
      openai_setting_model: "MiniMax-M3"
    }
  }));

  await page.goto("/settings", { waitUntil: "networkidle" });

  const cards = page.locator("[data-model-scope]");
  await expect(cards).toHaveCount(3);
  await expect(cards.nth(0).getByRole("heading", { name: "计划生成" })).toBeVisible();
  await expect(cards.nth(1).getByRole("heading", { name: "学习对话" })).toBeVisible();
  await expect(cards.nth(2).getByRole("heading", { name: "设定辅助" })).toBeVisible();

  const metrics = await cards.evaluateAll(nodes => nodes.map(node => {
    const header = node.firstElementChild as HTMLElement;
    const title = header.querySelector("h3") as HTMLElement;
    const description = header.querySelector("p") as HTMLElement;
    const titleStyle = getComputedStyle(title);
    const descriptionStyle = getComputedStyle(description);
    const titleRect = title.getBoundingClientRect();
    const descriptionRect = description.getBoundingClientRect();
    return {
      scope: node.getAttribute("data-model-scope"),
      cardAlignContent: getComputedStyle(node).alignContent,
      cardWidth: node.getBoundingClientRect().width,
      headerWidth: header.getBoundingClientRect().width,
      titleFontSize: titleStyle.fontSize,
      titleLineHeight: titleStyle.lineHeight,
      descriptionFontSize: descriptionStyle.fontSize,
      descriptionLineHeight: descriptionStyle.lineHeight,
      titleTop: titleRect.top,
      titleHeight: titleRect.height,
      descriptionTop: descriptionRect.top,
      descriptionHeight: descriptionRect.height,
      headerHeight: header.getBoundingClientRect().height
    };
  }));

  for (const metric of metrics) {
    expect(metric.cardAlignContent).toBe("start");
  }
  for (const key of [
    "titleTop",
    "titleHeight",
    "descriptionTop",
    "descriptionHeight",
    "headerHeight"
  ] as const) {
    const values = metrics.map(metric => metric[key]);
    expect(
      Math.max(...values) - Math.min(...values),
      `${key}: ${JSON.stringify(metrics)}`
    ).toBeLessThan(0.25);
  }
});
