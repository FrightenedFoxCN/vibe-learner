import { test, expect } from "@playwright/test";

test("closed Debug still records a real Persona generate/save/reload chain without protected content", async ({ page, request }) => {
  await page.addInitScript(() => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: "http://127.0.0.1:18998", isDesktop: false, platform: "unknown", secretStorageMode: "plain_text", vaultState: "unconfigured", vaultPath: "", storageRoot: "", startupError: "" };
  });
  const sent: { path: string; headers: Record<string, string> }[] = [];
  page.on("request", item => {
    if (item.url().startsWith("http://127.0.0.1:18998")) sent.push({ path: new URL(item.url()).pathname, headers: item.headers() });
  });
  await page.goto("/persona-spectrum");
  await expect(page.getByRole("button", { name: "新建人格草稿", exact: true })).toBeVisible();
  await page.getByRole("button", { name: "新建人格草稿", exact: true }).click();
  await page.getByRole("textbox", { name: "名称", exact: true }).fill("Diagnostic browser persona");
  await page.getByPlaceholder("例如：冷静学术、学院派导师、侦探式推理").fill("PRIVATE_DIAGNOSTIC_PROMPT_SENTINEL");
  const generated = page.waitForResponse(response => response.url().endsWith("/persona-cards/generate") && response.request().method() === "POST");
  await page.getByRole("button", { name: "根据关键词生成人格卡片", exact: true }).click();
  expect((await generated).status()).toBe(200);
  const savedResponse = page.waitForResponse(response => response.url().endsWith("/personas") && response.request().method() === "POST");
  await page.getByRole("button", { name: "创建人格", exact: true }).click();
  const saved = await (await savedResponse).json();
  await expect(page.getByRole("button", { name: "更新人格", exact: true })).toBeEnabled();
  const reload = page.waitForResponse(response => response.url().endsWith("/personas") && response.request().method() === "GET");
  await page.getByRole("button", { name: "重新载入人格", exact: true }).click();
  expect((await reload).status()).toBe(200);
  const flow = sent.find(item => item.path === "/persona-cards/generate")?.headers["x-debug-flow-id"];
  expect(flow).toBeTruthy();
  let events: any[] = [];
  await expect.poll(async () => {
    const response = await request.get(`http://127.0.0.1:18998/diagnostics/events?flow_id=${flow}`);
    events = (await response.json()).items.map((item: any) => item.event);
    return events.filter(item => item.source === "browser" && item.name === "request_finished").length;
  }).toBeGreaterThanOrEqual(4);
  expect(events.some(item => item.harness?.attempt_id)).toBe(true);
  expect(events.some(item => item.resource?.resource_id === saved.id)).toBe(true);
  expect(new Set(events.filter(item => item.source === "server" && item.name === "request_finished").map(item => item.request_id)).size).toBeGreaterThanOrEqual(4);
  expect(new Set(events.filter(item => item.source === "browser").map(item => item.action_id)).size).toBe(3);
  expect(JSON.stringify(events)).not.toContain("PRIVATE_DIAGNOSTIC_PROMPT_SENTINEL");
  expect(JSON.stringify(events)).not.toContain("Diagnostic browser persona");
  expect(events.every(item => item.category && item.severity && item.outcome)).toBe(true);
});
