import { test, expect } from "@playwright/test";
import { observeRequests } from "./api-fixture";

test("Sensory filters, disclosure and scoped bulk saves preserve focused controls", async ({ page }) => {
  await observeRequests(page);
  const tools = Array.from({ length: 18 }, (_, index) => ({ name: `tool-${index}`, label: `工具 ${index}`, description: `用途 ${index}`, category: "read", category_label: "读取", enabled: false, available: index !== 17 }));
  const payload = { stages: [{ name: "study", label: "学习", description: "学习工具", stage_enabled: true, tools }] };
  const writes: unknown[] = [];
  await page.route("**/model-tools/config", async route => {
    if (route.request().method() === "PATCH") {
      const body = route.request().postDataJSON(); writes.push(body);
      for (const toggle of body.toggles) tools.find(tool => tool.name === toggle.tool_name)!.enabled = toggle.enabled;
    }
    await route.fulfill({ json: payload });
  });
  await page.goto("/sensory-tools");
  await expect(page.getByText("找到 18 个工具", { exact: true })).toBeVisible();
  await expect(page.getByText("用途 0", { exact: true })).not.toBeVisible();
  const toggle = page.getByRole("checkbox", { name: "工具 12", exact: true });
  await toggle.focus();
  const scroll = await page.evaluate(() => window.scrollY);
  await toggle.press("Space");
  await expect(page.getByText("工具配置已保存。", { exact: true })).toBeVisible();
  await expect(toggle).toBeFocused();
  expect(await page.evaluate(() => window.scrollY)).toBe(scroll);
  await page.getByRole("searchbox", { name: "搜索工具" }).fill("工具 1");
  await expect(page.getByText("找到 9 个工具", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "可用性" }).selectOption("unavailable");
  await expect(page.getByText("找到 1 个工具", { exact: true })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: "工具 17", exact: true })).toBeDisabled();
  await page.getByRole("combobox", { name: "可用性" }).selectOption("available");
  await page.getByRole("button", { name: "批量管理", exact: true }).click();
  await page.getByRole("button", { name: "启用筛选结果", exact: true }).click();
  await expect.poll(() => writes.length).toBe(2);
  expect((writes[1] as { toggles: { tool_name: string }[] }).toggles.map(item => item.tool_name)).toEqual(["tool-1", "tool-10", "tool-11", "tool-13", "tool-14", "tool-15", "tool-16"]);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "/tmp/sensory-density-mobile.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("Persona source filter and Scene saved search have explicit empty states", async ({ page }) => {
  await observeRequests(page);
  await page.goto("/persona-spectrum");
  await page.getByRole("button", { name: "人格库", exact: true }).click();
  await page.getByRole("combobox", { name: "筛选人格来源" }).selectOption("user");
  await expect(page.getByText("没有匹配的人格，请调整搜索或筛选。")).toBeVisible();
  await page.getByRole("combobox", { name: "筛选人格来源" }).selectOption("builtin");
  await expect(page.getByText("1 个人格", { exact: true })).toBeVisible();
  await page.screenshot({ path: "/tmp/persona-density-desktop.png", fullPage: true });
  await page.goto("/scene-setup");
  await page.getByRole("button", { name: "已保存场景", exact: true }).click();
  await page.getByRole("searchbox", { name: "搜索已保存场景" }).fill("不存在");
  await expect(page.getByText("没有匹配的场景。", { exact: true })).toBeVisible();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: "/tmp/scene-density-mobile.png", fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
});

test("Sensory failed saves announce the error without stealing a later search focus", async ({ page }) => {
  await observeRequests(page);
  let fail: (() => void) | undefined;
  await page.route("**/model-tools/config", async route => {
    if (route.request().method() === "PATCH") {
      await new Promise<void>(resolve => { fail = resolve; });
      await route.fulfill({ status: 503, json: { detail: "暂时无法保存" } });
      return;
    }
    await route.fulfill({ json: { stages: [{ name: "study", label: "学习", stage_enabled: true, tools: [{ name: "read", label: "阅读工具", category: "read", enabled: false, available: true }] }] } });
  });
  await page.goto("/sensory-tools");
  await page.getByRole("checkbox", { name: "阅读工具", exact: true }).click();
  await expect.poll(() => Boolean(fail)).toBe(true);
  const search = page.getByRole("searchbox", { name: "搜索工具" });
  await search.fill("阅读");
  fail!();
  await expect(page.getByRole("alert").filter({ hasText: "配置操作失败" })).toContainText("配置操作失败");
  await expect(search).toBeFocused();
  await expect(page.getByRole("checkbox", { name: "阅读工具", exact: true })).not.toBeChecked();
});
