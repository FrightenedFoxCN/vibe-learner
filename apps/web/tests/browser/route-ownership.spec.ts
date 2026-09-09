import { test, expect } from "@playwright/test";
import type { Page } from "@playwright/test";
import { ROUTE_REQUESTS } from "./route-request-contract";

async function observeRequests(page: Page) {
  const requests: { method: string; path: string }[] = [];
  await page.addInitScript(() => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: "http://127.0.0.1:18999", isDesktop: false, platform: "unknown", secretStorageMode: "plain_text", vaultState: "unconfigured", vaultPath: "", storageRoot: "", startupError: "" };
  });
  await page.route("http://127.0.0.1:18999/**", async route => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    requests.push({ method: request.method(), path });
    let json: unknown = { items: [] };
    if (path === "/personas") json = { items: [{
      id: "fixture-mentor", revision: 1, name: "Fixture Mentor", source: "builtin",
      summary: "Tutor", relationship: "Teacher", learner_address: "Student", system_prompt: "Teach",
      reference_hints: [], slots: [], available_emotions: ["calm"], available_actions: ["point"],
      default_speech_style: "clear",
    }] };
    if (path === "/runtime-settings") json = { plan_provider: "mock" };
    if (path === "/model-tools/config" || path === "/model-usage/stats") json = {};
    if (path === "/tavern/rooms") json = { contract_version: "tavern-room-list-v1", items: [], next_cursor: null };
    await route.fulfill({ json });
  });
  return requests;
}

for (const [path, allowed] of Object.entries(ROUTE_REQUESTS)) {
  test(`${path} initializes only its owned resources`, async ({ page }, info) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    const requests = await observeRequests(page);
    await page.goto(path);
    await page.waitForLoadState("networkidle");
    expect([...new Set(requests.map(item => item.path))].sort()).toEqual([...allowed].sort());
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await page.waitForLoadState("networkidle");
    expect(requests.every(item => item.method === "GET" && allowed.includes(item.path))).toBe(true);
    for (const resource of allowed) {
      expect(requests.filter(item => item.path === resource).length).toBeLessThanOrEqual(2);
    }
    expect(errors).toEqual([]);
    await info.attach("api-requests.json", { body: JSON.stringify(requests, null, 2), contentType: "application/json" });
  });
}

test("Plan and Study share their owner; leaving it stops learning focus refresh", async ({ page }, info) => {
  const requests = await observeRequests(page);
  await page.goto("/plan");
  await page.waitForLoadState("networkidle");
  const initial = requests.length;
  await page.locator('a[href="/study"]').first().click();
  await expect(page).toHaveURL(/\/study$/);
  await page.waitForLoadState("networkidle");
  expect(requests.length).toBe(initial);
  await page.locator('a[href="/settings"]').first().click();
  await expect(page).toHaveURL(/\/settings$/);
  await page.waitForLoadState("networkidle");
  const afterLeaving = requests.length;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForLoadState("networkidle");
  expect(requests.length).toBe(afterLeaving);
  await info.attach("navigation-api-requests.json", { body: JSON.stringify(requests, null, 2), contentType: "application/json" });
});


test("Plan draft remains visible after navigating to Settings and back", async ({ page }) => {
  await observeRequests(page);
  await page.goto("/plan");
  await page.waitForLoadState("networkidle");
  await page.getByRole("textbox", { name: "学习目标", exact: true }).fill("保留跨路由草稿");
  await page.locator('input[type="file"]').setInputFiles({ name: "saved-textbook.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4 test") });
  await page.locator('a[href="/settings"]').first().click();
  await expect(page).toHaveURL(/\/settings$/);
  await page.locator('a[href="/plan"]').first().click();
  await expect(page).toHaveURL(/\/plan$/);
  await expect(page.getByRole("textbox", { name: "学习目标", exact: true })).toHaveValue("保留跨路由草稿");
  await expect(page.getByText("已保留：saved-textbook.pdf", { exact: true })).toBeVisible();
});
