import { readFile } from "node:fs/promises";
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

test("production Debug shows only the current page adapter across client navigation", async ({ page, request }) => {
  const response = await request.patch("http://127.0.0.1:18998/runtime-settings", { data: { show_debug_info: true } });
  expect(response.ok()).toBe(true);
  await page.addInitScript(() => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: "http://127.0.0.1:18998", isDesktop: false, platform: "unknown", secretStorageMode: "plain_text", vaultState: "unconfigured", vaultPath: "", storageRoot: "", startupError: "" };
  });
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/persona-spectrum");
  await page.getByRole("button", { name: /Debug/ }).click();
  await expect(page.getByRole("dialog").getByText("人格页调试面板", { exact: true })).toBeVisible();
  await page.keyboard.press("Escape");
  await page.locator('a[href="/settings"]').click();
  await page.getByRole("button", { name: /Debug/ }).click();
  await expect(page.getByRole("dialog").getByText("设置页调试面板", { exact: true })).toBeVisible();
  await expect(page.getByRole("dialog").getByText("人格页调试面板", { exact: true })).toHaveCount(0);
  await page.keyboard.press("Escape");
  await page.locator('a[href="/model-usage"]').click();
  await page.getByRole("button", { name: /Debug/ }).click();
  await expect(page.getByRole("dialog").getByText("用量审计调试面板", { exact: true })).toBeVisible();
  await expect(page.getByRole("dialog").getByText("设置页调试面板", { exact: true })).toHaveCount(0);
  // The stored open preference survives the initial settings-loading state.
  await page.reload();
  await expect(page.getByRole("dialog").getByText("用量审计调试面板", { exact: true })).toBeVisible();
  expect(errors).toEqual([]);
});

test("global timeline loads on demand, expands canonical links and reports unavailable reads", async ({ page, request }) => {
  await request.patch("http://127.0.0.1:18998/runtime-settings", { data: { show_debug_info: true } });
  await page.addInitScript(() => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: "http://127.0.0.1:18998", isDesktop: false, platform: "unknown", secretStorageMode: "plain_text", vaultState: "unconfigured", vaultPath: "", storageRoot: "", startupError: "" };
  });
  const reads: string[] = [];
  page.on("request", item => { if (item.method() === "GET" && item.url().includes("/diagnostics/")) reads.push(item.url()); });
  await page.goto("/persona-spectrum");
  await page.getByRole("button", { name: /Debug/ }).click();
  await expect(page.getByRole("dialog").getByText("人格页调试面板", { exact: true })).toBeVisible();
  expect(reads).toEqual([]);
  await page.getByRole("button", { name: "全局诊断", exact: true }).click();
  const timeline = page.getByRole("region", { name: "全局诊断时间线" });
  await expect(timeline.getByRole("button", { name: "刷新诊断" })).toBeEnabled();
  await timeline.getByLabel("流程", { exact: true }).selectOption("persona");
  await timeline.getByRole("button", { name: "应用筛选" }).click();
  await timeline.getByRole("button", { name: "展开 operation 关联" }).first().click();
  const linked = page.getByRole("region", { name: "Operation 关联详情" });
  await expect(linked.getByText("Harness 阶段与尝试", { exact: true })).toBeVisible();
  await expect.poll(() => reads.some(url => url.includes("operation-links"))).toBe(true);
  await expect.poll(() => reads.some(url => url.includes("harness-index"))).toBe(true);
  const requestDetails = linked.locator("details").filter({ has: page.locator("button").filter({ hasText: "查看关联请求事件" }) }).first();
  await requestDetails.locator("summary").click();
  await requestDetails.getByRole("button", { name: "查看关联请求事件" }).click();
  await expect.poll(() => reads.some(url => url.includes("/diagnostics/events?") && new URL(url).searchParams.has("request_id"))).toBe(true);
  await timeline.getByRole("button", { name: "收起 operation 关联" }).click();
  // Resolve a resource from the real canonical projection, then exercise the
  // production UI/query path without fabricating a resource from a URL.
  let indexed: any;
  await expect.poll(async () => {
    const result = await request.get("http://127.0.0.1:18998/diagnostics/harness-index?workflow=persona");
    indexed = (await result.json()).items.find((item: any) => item.resources?.context_subjects.length);
    return Boolean(indexed);
  }).toBe(true);
  const resource = indexed.resources.context_subjects[0];
  await timeline.getByLabel("资源类型", { exact: true }).selectOption(resource.resource_type);
  await timeline.getByLabel("resource_id", { exact: true }).fill(resource.resource_id);
  await timeline.getByRole("button", { name: "应用筛选" }).click();
  await timeline.getByRole("button", { name: "Harness 索引", exact: true }).click();
  await timeline.getByLabel("资源关联来源", { exact: true }).selectOption("context_subjects");
  await expect(timeline.getByRole("button", { name: "展开 operation 关联" })).toHaveCount(1);
  await expect.poll(() => reads.some(url => url.includes("/harness-index?") && new URL(url).searchParams.get("resource_id") === resource.resource_id && new URL(url).searchParams.get("resource_role") === "context_subjects")).toBe(true);
  await page.setViewportSize({ width: 390, height: 844 });
  await timeline.getByLabel("资源关联来源", { exact: true }).scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/unified-debug-resource-index.png" });
  await timeline.getByLabel("资源类型", { exact: true }).selectOption("");
  await timeline.getByLabel("resource_id", { exact: true }).fill("");
  await timeline.getByRole("button", { name: "应用筛选" }).click();
  await timeline.getByRole("button", { name: "采集覆盖", exact: true }).click();
  await expect(timeline.getByRole("region", { name: "采集覆盖" })).toContainText("计数为已观察下限");
  await expect.poll(() => reads.some(url => url.includes("/diagnostics/writers?"))).toBe(true);
  await timeline.getByRole("button", { name: "存储状态", exact: true }).click();
  const storage = timeline.getByRole("region", { name: "诊断存储状态" });
  await expect(storage).toContainText("事件数据库");
  await expect(storage).toContainText("诊断拒绝不等于业务提交失败");
  await page.setViewportSize({ width: 390, height: 844 });
  await storage.getByRole("heading", { name: "诊断存储状态", exact: true }).scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/unified-debug-storage.png" });
  await expect.poll(() => reads.some(url => url.includes("/diagnostics/storage"))).toBe(true);
  await timeline.getByRole("button", { name: "统计与导出", exact: true }).click();
  await timeline.getByRole("button", { name: "生成诊断快照" }).click();
  await expect(timeline.getByRole("button", { name: "下载诊断包" })).toBeEnabled();
  const downloading = page.waitForEvent("download");
  await timeline.getByRole("button", { name: "下载诊断包" }).click();
  const download = await downloading;
  expect(download.suggestedFilename()).toBe("vibe-learner-diagnostics.json");
  const contents = await readFile((await download.path())!, "utf8");
  const exported = JSON.parse(contents);
  expect(exported.schema_version).toBe("diagnostic-export-v1");
  expect(exported.storage_observation.installation_disk_limit_certified).toBe(false);
  expect(exported.filters.workflow).toBe("persona");
  expect(exported.events.length).toBeGreaterThan(0);
  expect(exported.audit.observations.length).toBeGreaterThan(0);
  expect(exported.audit.commit_claim).toBe("none");
  expect(contents).not.toContain("PRIVATE_DIAGNOSTIC_PROMPT_SENTINEL");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await timeline.getByRole("heading", { name: "诊断统计与导出", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: "/tmp/unified-debug-audit.png" });
  const metric = timeline.getByRole("region", { name: "诊断统计与导出" }).locator("details").filter({ hasText: "P95" }).first();
  await metric.locator("summary").click();
  await metric.scrollIntoViewIfNeeded();
  await expect(metric).toContainText("P95");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/unified-debug-audit-metrics.png" });
  await timeline.getByRole("button", { name: "事件时间线", exact: true }).click();
  await expect(timeline.getByRole("button", { name: "刷新诊断" })).toBeEnabled();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("dialog")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await timeline.getByRole("heading", { name: "全局诊断时间线", exact: true }).scrollIntoViewIfNeeded();
  await page.screenshot({ path: "/tmp/unified-debug-timeline.png" });
  await page.keyboard.press("Escape");
  const count = reads.length;
  await page.waitForTimeout(250);
  expect(reads.length).toBe(count);
  await page.route("**/diagnostics/events?**", route => route.fulfill({ status: 503, contentType: "application/json", body: '{"detail":"PRIVATE_DIAGNOSTIC_SERVER_ERROR"}' }));
  await page.getByRole("button", { name: /Debug/ }).click();
  await expect(page.getByRole("dialog").getByRole("alert")).toContainText("诊断读取失败");
  await expect(page.getByRole("dialog")).not.toContainText("PRIVATE_DIAGNOSTIC_SERVER_ERROR");
});


test("Scene generation, candidate application and saves share flow with committed resource references", async ({ page, request }) => {
  await request.patch("http://127.0.0.1:18998/runtime-settings", { data: { show_debug_info: false } });
  await page.addInitScript(() => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: "http://127.0.0.1:18998", isDesktop: false, platform: "unknown", secretStorageMode: "plain_text", vaultState: "unconfigured", vaultPath: "", storageRoot: "", startupError: "" };
  });
  const sent: { path: string; headers: Record<string, string> }[] = [];
  page.on("request", item => { if (item.method() === "POST" || item.method() === "PUT") sent.push({ path: new URL(item.url()).pathname, headers: item.headers() }); });
  await page.goto("/scene-setup");
  await page.getByPlaceholder("输入关键词，例如：赛博校园, 物理实验, 夜间自习, 钟楼广播").fill("PRIVATE_SCENE_DIAGNOSTIC_SENTINEL");
  await page.getByRole("button", { name: "根据关键词生成场景树", exact: true }).click();
  await page.getByRole("button", { name: "应用到编辑区", exact: true }).click();
  const creating = page.waitForResponse(response => response.url().endsWith("/scene-library") && response.request().method() === "POST");
  await page.getByRole("button", { name: "保存到场景库", exact: true }).click();
  const createdResponse = await creating; expect(createdResponse.status()).toBe(200);
  const created = await createdResponse.json();
  const updating = page.waitForResponse(response => response.url().endsWith(`/scene-library/${created.scene_id}`) && response.request().method() === "PUT");
  await page.getByRole("button", { name: "更新已保存场景", exact: true }).click();
  const updatedResponse = await updating; expect(updatedResponse.status()).toBe(200);
  const updated = await updatedResponse.json();
  const calls = sent.filter(item => item.path === "/scene-setup/generate" || item.path.startsWith("/scene-library"));
  expect(calls).toHaveLength(3);
  const flow = calls[0].headers["x-debug-flow-id"];
  expect(flow).toBeTruthy();
  expect(new Set(calls.map(item => item.headers["x-debug-flow-id"])).size).toBe(1);
  expect(new Set(calls.map(item => item.headers["x-debug-action-id"])).size).toBe(3);
  let events: any[] = [];
  await expect.poll(async () => {
    const response = await request.get(`http://127.0.0.1:18998/diagnostics/events?flow_id=${flow}`);
    events = (await response.json()).items.map((item: any) => item.event);
    return events.filter(item => item.source === "browser" && item.name === "request_finished").length;
  }).toBe(3);
  expect(events.filter(item => item.resource?.resource_type === "scene").map(item => item.resource)).toEqual([
    { resource_type: "scene", resource_id: created.scene_id, revision: created.revision },
    { resource_type: "scene", resource_id: updated.scene_id, revision: updated.revision },
  ]);
  expect(events.some(item => item.harness?.workflow === "scene")).toBe(true);
  expect(JSON.stringify(events)).not.toContain("PRIVATE_SCENE_DIAGNOSTIC_SENTINEL");
  const conflict = await request.put(`http://127.0.0.1:18998/scene-library/${created.scene_id}`, { data: {
    contract_version: "scene-committed-save-v1", expected_revision: created.revision,
    scene_name: created.scene_name, scene_summary: created.scene_summary, scene_layers: created.scene_layers,
    selected_layer_id: created.selected_layer_id, collapsed_layer_ids: created.collapsed_layer_ids,
  }, headers: { "X-Debug-Flow-Id": flow } });
  expect(conflict.status()).toBe(409);
  const references = await request.get(`http://127.0.0.1:18998/diagnostics/events?resource_type=scene&resource_id=${created.scene_id}`);
  expect((await references.json()).items).toHaveLength(2);
});


test("document upload, parsing, plan stream and initial Session share one real diagnostic action", async ({ page, request }) => {
  await request.patch("http://127.0.0.1:18998/runtime-settings", { data: { show_debug_info: false } });
  await page.addInitScript(() => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: "http://127.0.0.1:18998", isDesktop: false, platform: "unknown", secretStorageMode: "plain_text", vaultState: "unconfigured", vaultPath: "", storageRoot: "", startupError: "" };
  });
  const sent: { path: string; headers: Record<string, string> }[] = [];
  page.on("request", item => {
    if (item.method() === "POST" && item.url().startsWith("http://127.0.0.1:18998")) sent.push({ path: new URL(item.url()).pathname, headers: item.headers() });
  });
  await page.goto("/plan");
  await page.getByLabel("教材文件（PDF）", { exact: true }).setInputFiles({
    name: "diagnostic-document.pdf", mimeType: "application/pdf",
    buffer: await readFile(new URL("./fixtures/diagnostic-document.pdf", import.meta.url)),
  });
  await page.getByRole("textbox", { name: "学习目标", exact: true }).fill("PRIVATE_PLAN_DIAGNOSTIC_SENTINEL learn observation and evidence");
  const sessionResponse = page.waitForResponse(response => response.url().endsWith("/study-sessions") && response.request().method() === "POST");
  await page.getByRole("button", { name: "生成计划", exact: true }).click();
  expect((await sessionResponse).status()).toBe(200);
  const chain = sent.filter(item => item.path === "/documents" || item.path.endsWith("/process/stream") || item.path === "/learning-plans/stream" || item.path === "/study-sessions");
  expect(chain).toHaveLength(4);
  const flow = chain[0].headers["x-debug-flow-id"];
  expect(flow).toBeTruthy();
  expect(new Set(chain.map(item => item.headers["x-debug-flow-id"])).size).toBe(1);
  expect(new Set(chain.map(item => item.headers["x-debug-action-id"])).size).toBe(1);
  let events: any[] = [];
  await expect.poll(async () => {
    events = []; let after = 0;
    for (let index = 0; index < 10; index++) {
      const response = await request.get(`http://127.0.0.1:18998/diagnostics/events?flow_id=${flow}&after=${after}`);
      const result = await response.json(); events.push(...result.items.map((item: any) => item.event));
      if (!result.has_more) break;
      after = result.next_cursor;
    }
    return events.filter(item => item.source === "browser" && item.name === "request_finished").length;
  }).toBe(4);
  expect(new Set(events.filter(item => item.source === "server" && item.name === "request_finished").map(item => item.request_id)).size).toBe(4);
  expect(events.some(item => item.harness?.workflow === "document_parse")).toBe(true);
  expect(events.some(item => item.harness?.workflow === "planning")).toBe(true);
  expect(JSON.stringify(events)).not.toContain("PRIVATE_PLAN_DIAGNOSTIC_SENTINEL");
  expect(JSON.stringify(events)).not.toContain("diagnostic-document.pdf");
  expect(JSON.stringify(events)).not.toContain("Observe a sample");
});
