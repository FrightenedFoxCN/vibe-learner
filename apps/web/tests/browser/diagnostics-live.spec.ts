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
  await expect(storage.getByRole("heading", { name: "诊断目录合计", exact: true })).toBeVisible();
  await expect(storage).toContainText("不跟随链接、不读取内容、不删除文件");
  await expect(storage).toContainText("诊断拒绝不等于业务提交失败");
  await page.setViewportSize({ width: 390, height: 844 });
  await storage.getByRole("heading", { name: "诊断存储状态", exact: true }).scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/unified-debug-storage.png" });
  await storage.getByRole("heading", { name: "诊断目录合计", exact: true }).scrollIntoViewIfNeeded();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
  await page.screenshot({ path: "/tmp/unified-debug-directory.png" });
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
  const directory = exported.storage_observation.directory;
  expect(directory.scope).toBe("diagnostics_directory_regular_file_lengths");
  expect(directory.max_bytes).toBe(200 * 1024 * 1024);
  expect(directory.database_bytes + directory.spool_bytes + directory.other_bytes).toBe(directory.total_bytes);
  expect(directory.scanned_entries).toBeLessThanOrEqual(directory.scan_limit);
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
    { resource_type: "scene", resource_id: created.scene_id, revision: created.revision, sequence: null, parent_resource_id: null },
    { resource_type: "scene", resource_id: updated.scene_id, revision: updated.revision, sequence: null, parent_resource_id: null },
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
  for (const type of ["document", "learning_plan", "study_session"]) expect(events.some(item => item.resource?.resource_type === type)).toBe(true);
  expect(events.filter(item => ["document", "learning_plan"].includes(item.resource?.resource_type)).every(item => item.resource.revision === null)).toBe(true);
  expect(JSON.stringify(events)).not.toContain("PRIVATE_PLAN_DIAGNOSTIC_SENTINEL");
  expect(JSON.stringify(events)).not.toContain("diagnostic-document.pdf");
  expect(JSON.stringify(events)).not.toContain("Observe a sample");
});


test("committed Study reply lost in transport is queried after reload with the original flow", async ({ page, request }) => {
  await request.patch("http://127.0.0.1:18998/runtime-settings", { data: { show_debug_info: false } });
  await page.addInitScript(() => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: "http://127.0.0.1:18998", isDesktop: false, platform: "unknown", secretStorageMode: "plain_text", vaultState: "unconfigured", vaultPath: "", storageRoot: "", startupError: "" };
  });
  const sentinel = "PRIVATE_STUDY_DIAGNOSTIC_SENTINEL explain the observation";
  let originalHeaders: Record<string, string> = {}, clientRequestId = "", sessionId = "", receipt: any;
  const queries: Record<string, string>[] = [];
  page.on("request", item => {
    if (clientRequestId && item.url().includes(`/chat-operations/${clientRequestId}`)) queries.push(item.headers());
  });
  await page.route("**/study-sessions/*/chat", async route => {
    const input = route.request().postDataJSON();
    if (input.message !== sentinel) { await route.continue(); return; }
    originalHeaders = route.request().headers(); clientRequestId = input.client_request_id;
    sessionId = new URL(route.request().url()).pathname.split("/")[2];
    const upstream = await route.fetch();
    expect(upstream.status()).toBe(200);
    receipt = await upstream.json(); expect(receipt.status).toBe("committed");
    await route.abort("failed");
  });
  await page.goto("/study");
  await expect(page.getByRole("button", { name: "发送", exact: true })).toBeEnabled();
  await page.getByPlaceholder("输入本节学习问题…").fill(sentinel);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByRole("button", { name: "查询本次请求结果", exact: true })).toBeVisible();
  expect(originalHeaders["x-debug-flow-id"]).toBeTruthy();
  await page.reload();
  await expect.poll(() => queries.length).toBeGreaterThan(0);
  await expect(page.getByRole("button", { name: "查询本次请求结果", exact: true })).toHaveCount(0);
  expect(queries[0]["x-debug-flow-id"]).toBe(originalHeaders["x-debug-flow-id"]);
  expect(queries[0]["x-debug-action-id"]).not.toBe(originalHeaders["x-debug-action-id"]);
  expect(queries[0]["x-debug-page-view-id"]).not.toBe(originalHeaders["x-debug-page-view-id"]);
  const persisted = await (await request.get(`http://127.0.0.1:18998/study-sessions/${sessionId}`)).json();
  expect(persisted.turns.filter((turn: any) => turn.learner_message === sentinel)).toHaveLength(1);
  const diagnostics = await request.get(`http://127.0.0.1:18998/diagnostics/events?flow_id=${originalHeaders["x-debug-flow-id"]}`);
  const events = (await diagnostics.json()).items.map((item: any) => item.event);
  expect(events.some((event: any) => event.harness?.workflow === "study_chat")).toBe(true);
  expect(events.some((event: any) => event.resource?.resource_type === "study_session" && event.resource.resource_id === sessionId)).toBe(true);
  expect(JSON.stringify(events)).not.toContain("PRIVATE_STUDY_DIAGNOSTIC_SENTINEL");
});


test("Tavern turn and recovery reads share action without repeating a committed user message", async ({ page, request }) => {
  await request.patch("http://127.0.0.1:18998/runtime-settings", { data: { show_debug_info: false } });
  await page.addInitScript(() => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: "http://127.0.0.1:18998", isDesktop: false, platform: "unknown", secretStorageMode: "plain_text", vaultState: "unconfigured", vaultPath: "", storageRoot: "", startupError: "" };
  });
  await page.goto("/tavern");
  const setup = page.getByRole("region", { name: "创建房间", exact: true });
  await setup.getByRole("textbox", { name: "标题", exact: true }).fill("Diagnostic Tavern");
  await setup.getByRole("checkbox").first().check();
  const creating = page.waitForResponse(response => response.url().endsWith("/tavern/rooms") && response.request().method() === "POST");
  await setup.getByRole("button", { name: "创建并进入", exact: true }).click();
  const room = (await (await creating).json()).room;
  await expect(page.getByPlaceholder("输入消息。Enter 发送，Shift + Enter 换行。")).toBeVisible();
  const calls: { path: string; method: string; headers: Record<string, string> }[] = [];
  page.on("request", item => { if (item.url().includes("/tavern/rooms")) calls.push({ path: new URL(item.url()).pathname, method: item.method(), headers: item.headers() }); });
  for (const lost of [false, true]) {
    const message = `PRIVATE_TAVERN_DIAGNOSTIC_SENTINEL-${lost}`;
    if (lost) await page.route("**/tavern/rooms/*/turns", async route => {
      const result = await route.fetch(); expect(result.status()).toBe(200);
      expect((await result.json()).run.status).toBe("completed");
      await route.abort("failed");
    });
    calls.length = 0;
    await page.getByPlaceholder("输入消息。Enter 发送，Shift + Enter 换行。").fill(message);
    await page.getByRole("button", { name: "发送并回应", exact: true }).click();
    await expect.poll(() => calls.some(call => call.path.endsWith("/turns"))).toBe(true);
    await expect(page.getByRole("button", { name: "生成中…", exact: true })).toHaveCount(0);
    const post = calls.find(call => call.path.endsWith("/turns"))!;
    const reads = calls.filter(call => call.method === "GET");
    expect(reads.length).toBeGreaterThanOrEqual(lost ? 4 : 2);
    expect(post.headers["x-debug-flow-id"]).toBeTruthy();
    expect(reads.every(call => call.headers["x-debug-flow-id"] === post.headers["x-debug-flow-id"] && call.headers["x-debug-action-id"] === post.headers["x-debug-action-id"])).toBe(true);
    expect(calls.filter(call => call.path.endsWith("/turns"))).toHaveLength(1);
    const persisted = await (await request.get(`http://127.0.0.1:18998/tavern/rooms/${room.id}`)).json();
    expect(persisted.messages.filter((item: any) => item.author_kind === "user" && item.content === message)).toHaveLength(1);
    const response = await request.get(`http://127.0.0.1:18998/diagnostics/events?flow_id=${post.headers["x-debug-flow-id"]}`);
    const events = (await response.json()).items.map((item: any) => item.event);
    expect(events.some((event: any) => event.harness?.workflow === "tavern")).toBe(true);
    const resourceMessages = events.filter((event: any) => event.resource?.resource_type === "tavern_message");
    expect(resourceMessages.length).toBeGreaterThan(0);
    for (const event of resourceMessages) {
      const message = persisted.messages.find((item: any) => item.id === event.resource.resource_id);
      expect(message).toBeTruthy(); expect(event.resource.sequence).toBe(message.sequence);
      expect(event.resource.parent_resource_id).toBe(room.id); expect(event.resource.revision).toBeNull();
    }
    expect(JSON.stringify(events)).not.toContain("PRIVATE_TAVERN_DIAGNOSTIC_SENTINEL");
  }
});


test("Study attachments persist through the real multipart path and rejected media has no saved-resource claim", async ({ page, request }) => {
  await request.patch("http://127.0.0.1:18998/runtime-settings", { data: { show_debug_info: false } });
  await page.addInitScript(() => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: "http://127.0.0.1:18998", isDesktop: false, platform: "unknown", secretStorageMode: "plain_text", vaultState: "unconfigured", vaultPath: "", storageRoot: "", startupError: "" };
  });
  await page.goto("/study");
  await expect(page.getByRole("button", { name: "发送", exact: true })).toBeEnabled();
  const filename = "PRIVATE_DIAGNOSTIC_ATTACHMENT_NAME.txt";
  const contents = "PRIVATE_DIAGNOSTIC_ATTACHMENT_CONTENT";
  const message = "PRIVATE_DIAGNOSTIC_ATTACHMENT_MESSAGE";
  await page.locator('input[type="file"]').setInputFiles({ name: filename, mimeType: "text/plain", buffer: Buffer.from(contents) });
  await page.getByPlaceholder("输入本节学习问题…").fill(message);
  const sending = page.waitForResponse(response => response.url().endsWith("/chat-with-attachments") && response.request().method() === "POST");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  const response = await sending;
  expect(response.status()).toBe(200);
  const receipt = await response.json(); expect(receipt.status).toBe("committed");
  const headers = response.request().headers();
  const sessionId = new URL(response.url()).pathname.split("/")[2];
  await expect(page.getByRole("button", { name: "发送", exact: true })).toBeEnabled();
  const persisted = await (await request.get(`http://127.0.0.1:18998/study-sessions/${sessionId}`)).json();
  const turn = persisted.turns.find((turn: any) => turn.learner_message === message);
  expect(turn.learner_attachments).toHaveLength(1);
  expect(turn.learner_attachments[0].name).toBe(filename);
  expect(turn.learner_attachments[0].text_excerpt).toContain(contents);
  expect(turn.learner_attachments[0]).not.toHaveProperty("stored_path");
  let events: any[] = [];
  await expect.poll(async () => {
    events = (await (await request.get(`http://127.0.0.1:18998/diagnostics/events?flow_id=${headers["x-debug-flow-id"]}`)).json()).items.map((item: any) => item.event);
    return events.some(event => event.resource?.resource_type === "study_session" && event.resource.resource_id === sessionId);
  }).toBe(true);
  expect(events.some(event => event.harness?.workflow === "study_chat")).toBe(true);
  for (const secret of [filename, contents, message]) expect(JSON.stringify(events)).not.toContain(secret);
  await page.locator('input[type="file"]').setInputFiles({ name: "PRIVATE_DIAGNOSTIC_UNSUPPORTED.bin", mimeType: "application/octet-stream", buffer: Buffer.from("PRIVATE_UNSUPPORTED_CONTENT") });
  await page.getByPlaceholder("输入本节学习问题…").fill("PRIVATE_UNSUPPORTED_MESSAGE");
  const rejected = page.waitForResponse(item => item.url().endsWith("/chat-with-attachments") && item.request().method() === "POST");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  const failure = await rejected; expect(failure.status()).toBe(200);
  const rejectedReceipt = await failure.json();
  expect(rejectedReceipt.status).toBe("not_committed");
  expect(rejectedReceipt.committed_session_revision).toBeNull();
  expect(rejectedReceipt.error_code).toBe("study_chat_not_committed_chat_attachment_unsupported_media_type");
  const failedHeaders = failure.request().headers();
  const after = await (await request.get(`http://127.0.0.1:18998/study-sessions/${sessionId}`)).json();
  expect(after.revision).toBe(persisted.revision);
  let failed: any[] = [];
  await expect.poll(async () => {
    failed = (await (await request.get(`http://127.0.0.1:18998/diagnostics/events?flow_id=${failedHeaders["x-debug-flow-id"]}`)).json()).items.map((item: any) => item.event);
    return failed.some(event => event.name === "request_finished" && event.status_code === 200);
  }).toBe(true);
  expect(failed.some(event => event.resource)).toBe(false);
  for (const secret of ["PRIVATE_DIAGNOSTIC_UNSUPPORTED", "PRIVATE_UNSUPPORTED_CONTENT", "PRIVATE_UNSUPPORTED_MESSAGE"]) expect(JSON.stringify(failed)).not.toContain(secret);
});


test("interactive question CAS conflict and retry use persisted read-back while diagnostics exclude grading material", async ({ page, request }) => {
  await request.patch("http://127.0.0.1:18998/runtime-settings", { data: { show_debug_info: false } });
  await page.addInitScript(() => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: "http://127.0.0.1:18998", isDesktop: false, platform: "unknown", secretStorageMode: "plain_text", vaultState: "unconfigured", vaultPath: "", storageRoot: "", startupError: "" };
  });
  const sent: { path: string; method: string; headers: Record<string, string> }[] = [];
  page.on("request", item => {
    if (item.url().includes("/study-sessions/")) sent.push({ path: new URL(item.url()).pathname, method: item.method(), headers: item.headers() });
  });
  await page.goto("/study");
  await expect(page.getByRole("button", { name: "发送", exact: true })).toBeEnabled();
  await page.getByPlaceholder("输入本节学习问题…").fill("PRIVATE_DIAGNOSTIC_QUESTION_TRIGGER");
  const generated = page.waitForResponse(item => item.url().endsWith("/chat") && item.request().postDataJSON()?.message === "PRIVATE_DIAGNOSTIC_QUESTION_TRIGGER");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  const generation = await generated; expect(generation.status()).toBe(200);
  const sessionId = new URL(generation.url()).pathname.split("/")[2];
  const before = await (await request.get(`http://127.0.0.1:18998/study-sessions/${sessionId}`)).json();
  const questionTurn = before.turns.find((turn: any) => turn.learner_message === "PRIVATE_DIAGNOSTIC_QUESTION_TRIGGER");
  expect(questionTurn.interactive_question.result).toBeNull();
  const publicQuestion = JSON.stringify(questionTurn.interactive_question);
  for (const secret of ["grading_spec", "answer_key", "correct_option_key", "PRIVATE_DIAGNOSTIC_GRADING_EXPLANATION"]) expect(publicQuestion).not.toContain(secret);
  await expect(page.getByRole("button", { name: "A. Diagnostic first choice", exact: true })).toBeEnabled();
  await page.getByRole("button", { name: "A. Diagnostic first choice", exact: true }).click();
  let firstAttempt = true;
  await page.route(`**/study-sessions/${sessionId}/attempt`, async route => {
    if (!firstAttempt) { await route.continue(); return; }
    firstAttempt = false;
    const stale = { ...route.request().postDataJSON(), expected_session_revision: 0 };
    const upstream = await route.fetch({ postData: stale });
    await route.fulfill({ response: upstream });
  });
  const conflicting = page.waitForResponse(item => item.url().endsWith(`/${sessionId}/attempt`));
  await page.getByRole("button", { name: "提交答案", exact: true }).click();
  const conflict = await conflicting; expect(conflict.status()).toBe(409);
  await expect(page.getByRole("button", { name: "重新提交答案", exact: true })).toBeEnabled();
  const afterConflict = await (await request.get(`http://127.0.0.1:18998/study-sessions/${sessionId}`)).json();
  expect(afterConflict.revision).toBe(before.revision);
  expect(afterConflict.turns.find((turn: any) => turn.id === questionTurn.id).interactive_question.result).toBeNull();
  const saving = page.waitForResponse(item => item.url().endsWith(`/${sessionId}/attempt`));
  const callback = page.waitForResponse(item => item.url().endsWith(`/${sessionId}/chat`) && item.request().postDataJSON()?.message_kind === "interactive_callback");
  await page.getByRole("button", { name: "重新提交答案", exact: true }).click();
  const saved = await saving; expect(saved.status()).toBe(200);
  const attempt = await saved.json();
  const continued = await callback; expect(continued.status()).toBe(200);
  expect((await continued.json()).status).toBe("committed");
  await expect(page.getByText(/已记录/).first()).toBeVisible();
  const successful = saved.request().headers();
  expect(continued.request().headers()["x-debug-flow-id"]).toBe(successful["x-debug-flow-id"]);
  expect(continued.request().headers()["x-debug-action-id"]).not.toBe(successful["x-debug-action-id"]);
  const readBack = sent.find(item => item.method === "GET" && item.path === `/study-sessions/${sessionId}` && item.headers["x-debug-action-id"] === successful["x-debug-action-id"]);
  expect(readBack).toBeTruthy();
  expect(readBack!.headers["x-debug-flow-id"]).toBe(successful["x-debug-flow-id"]);
  const persisted = await (await request.get(`http://127.0.0.1:18998/study-sessions/${sessionId}`)).json();
  const result = persisted.turns.find((turn: any) => turn.id === questionTurn.id).interactive_question.result;
  expect(result.is_correct).toBe(true);
  expect(result.explanation).toBe("PRIVATE_DIAGNOSTIC_GRADING_EXPLANATION");
  expect(persisted.turns.filter((turn: any) => turn.learner_message_kind === "interactive_callback")).toHaveLength(1);
  let successfulEvents: any[] = [];
  await expect.poll(async () => {
    successfulEvents = (await (await request.get(`http://127.0.0.1:18998/diagnostics/events?flow_id=${successful["x-debug-flow-id"]}`)).json()).items.map((item: any) => item.event);
    return successfulEvents.some(event => event.resource?.resource_id === sessionId && event.resource.revision === attempt.committed_revision);
  }).toBe(true);
  const failedEvents = (await (await request.get(`http://127.0.0.1:18998/diagnostics/events?flow_id=${conflict.request().headers()["x-debug-flow-id"]}`)).json()).items.map((item: any) => item.event);
  expect(failedEvents.some((event: any) => event.resource)).toBe(false);
  expect(failedEvents.some((event: any) => event.status_code === 409)).toBe(true);
  let callbackEvents: any[] = [];
  await expect.poll(async () => {
    callbackEvents = (await (await request.get(`http://127.0.0.1:18998/diagnostics/events?flow_id=${continued.request().headers()["x-debug-flow-id"]}`)).json()).items.map((item: any) => item.event);
    return callbackEvents.some(event => event.resource?.resource_id === sessionId && event.request_id === continued.headers()["x-request-id"]);
  }).toBe(true);
  const generationEvents = (await (await request.get(`http://127.0.0.1:18998/diagnostics/events?flow_id=${generation.request().headers()["x-debug-flow-id"]}`)).json()).items.map((item: any) => item.event);
  expect(generationEvents.some((event: any) => event.harness?.workflow === "study_chat")).toBe(true);
  const all = JSON.stringify([...generationEvents, ...successfulEvents, ...failedEvents, ...callbackEvents]);
  for (const secret of ["PRIVATE_DIAGNOSTIC_QUESTION_TRIGGER", "PRIVATE_DIAGNOSTIC_QUESTION_PROMPT", "PRIVATE_DIAGNOSTIC_GRADING_EXPLANATION", "grading_spec", "answer_key", "correct_option_key", "accepted_answers"]) expect(all).not.toContain(secret);
});

test("committed automatic question callback recovers after reload with the answer flow", async ({ page, request }) => {
  await page.addInitScript(() => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: "http://127.0.0.1:18998", isDesktop: false, platform: "unknown", secretStorageMode: "plain_text", vaultState: "unconfigured", vaultPath: "", storageRoot: "", startupError: "" };
  });
  let callbackHeaders: Record<string, string> = {}, clientRequestId = "", sessionId = "", receipt: any;
  let callbackPosts = 0;
  const queries: Record<string, string>[] = [];
  page.on("request", item => {
    if (clientRequestId && item.url().includes(`/chat-operations/${clientRequestId}`)) queries.push(item.headers());
  });
  await page.route("**/study-sessions/*/chat", async route => {
    const input = route.request().postDataJSON();
    if (input.message_kind !== "interactive_callback") { await route.continue(); return; }
    callbackPosts += 1;
    callbackHeaders = route.request().headers(); clientRequestId = input.client_request_id;
    sessionId = new URL(route.request().url()).pathname.split("/")[2];
    const upstream = await route.fetch();
    expect(upstream.status()).toBe(200);
    receipt = await upstream.json(); expect(receipt.status).toBe("committed");
    await route.abort("failed");
  });
  await page.goto("/study");
  await expect(page.getByRole("button", { name: "发送", exact: true })).toBeEnabled();
  await page.getByPlaceholder("输入本节学习问题…").fill("PRIVATE_DIAGNOSTIC_QUESTION_TRIGGER");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByRole("button", { name: "A. Diagnostic first choice", exact: true }).last()).toBeEnabled();
  await page.getByRole("button", { name: "A. Diagnostic first choice", exact: true }).last().click();
  const saving = page.waitForResponse(item => item.url().endsWith("/attempt"));
  await page.getByRole("button", { name: "提交答案", exact: true }).last().click();
  const saved = await saving; expect(saved.status()).toBe(200);
  const answerHeaders = saved.request().headers();
  await expect(page.getByRole("button", { name: "查询本次请求结果", exact: true })).toBeVisible();
  expect(answerHeaders["x-debug-flow-id"]).toBeTruthy();
  expect(callbackHeaders["x-debug-flow-id"]).toBe(answerHeaders["x-debug-flow-id"]);
  expect(callbackHeaders["x-debug-action-id"]).not.toBe(answerHeaders["x-debug-action-id"]);
  await page.reload();
  await expect.poll(() => queries.length).toBeGreaterThan(0);
  await expect(page.getByRole("button", { name: "查询本次请求结果", exact: true })).toHaveCount(0);
  expect(queries[0]["x-debug-flow-id"]).toBe(answerHeaders["x-debug-flow-id"]);
  expect(queries[0]["x-debug-action-id"]).not.toBe(callbackHeaders["x-debug-action-id"]);
  expect(queries[0]["x-debug-page-view-id"]).not.toBe(callbackHeaders["x-debug-page-view-id"]);
  expect(callbackPosts).toBe(1);
  const persisted = await (await request.get(`http://127.0.0.1:18998/study-sessions/${sessionId}`)).json();
  const turns = persisted.turns.filter((turn: any) => turn.id === receipt.committed_turn_id);
  expect(turns).toHaveLength(1);
  expect(turns[0].learner_message_kind).toBe("interactive_callback");
});

test("Plan Workspace parse failure stops planning and a corrected submission owns a new flow", async ({ page, request }) => {
  await page.addInitScript(() => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: "http://127.0.0.1:18998", isDesktop: false, platform: "unknown", secretStorageMode: "plain_text", vaultState: "unconfigured", vaultPath: "", storageRoot: "", startupError: "" };
  });
  const posts: { path: string; headers: Record<string, string> }[] = [];
  page.on("request", item => {
    if (item.method() === "POST" && item.url().startsWith("http://127.0.0.1:18998")) posts.push({ path: new URL(item.url()).pathname, headers: item.headers() });
  });
  await page.goto("/plan");
  await page.getByLabel("教材文件（PDF）", { exact: true }).setInputFiles({ name: "PRIVATE_BAD_PDF.pdf", mimeType: "application/pdf", buffer: Buffer.from("PRIVATE_BROKEN_PDF_CONTENT") });
  await page.getByRole("textbox", { name: "学习目标", exact: true }).fill("PRIVATE_RETRY_OBJECTIVE learn evidence");
  const failing = page.waitForResponse(item => item.url().endsWith("/process/stream"));
  await page.getByRole("button", { name: "生成计划", exact: true }).click();
  const failed = await failing; expect(failed.status()).toBe(200);
  expect(JSON.parse((await failed.text()).trim().split("\n").at(-1)!).stage).toBe("stream_error");
  await expect(page.getByRole("button", { name: "生成计划", exact: true })).toBeEnabled();
  const failedChain = posts.filter(item => item.path === "/documents" || item.path.endsWith("/process/stream") || item.path === "/learning-plans/stream" || item.path === "/study-sessions");
  expect(failedChain).toHaveLength(2);
  const flow = failedChain[0].headers["x-debug-flow-id"];
  expect(flow).toBeTruthy();
  expect(failedChain[1].headers["x-debug-flow-id"]).toBe(flow);
  const failedDocumentId = new URL(failed.url()).pathname.split("/")[2];
  expect((await (await request.get(`http://127.0.0.1:18998/documents/${failedDocumentId}/status`)).json()).status).toBe("failed");
  await expect(page.getByText(/教材处理失败：/)).toBeVisible();
  await page.getByLabel(/^更换教材文件（PDF）/).setInputFiles({ name: "PRIVATE_CORRECTED_PDF.pdf", mimeType: "application/pdf", buffer: await readFile(new URL("./fixtures/diagnostic-document.pdf", import.meta.url)) });
  const succeeding = page.waitForResponse(item => item.url().endsWith("/study-sessions") && item.request().method() === "POST");
  await page.getByRole("button", { name: "生成计划", exact: true }).click();
  expect((await succeeding).status()).toBe(200);
  const corrected = posts.filter(item => item.path === "/documents" || item.path.endsWith("/process/stream") || item.path === "/learning-plans/stream" || item.path === "/study-sessions").slice(2);
  expect(corrected).toHaveLength(4);
  expect(corrected[0].headers["x-debug-flow-id"]).not.toBe(flow);
  expect(new Set(corrected.map(item => item.headers["x-debug-flow-id"])).size).toBe(1);
  let failedEvents: any[] = [];
  await expect.poll(async () => {
    failedEvents = (await (await request.get(`http://127.0.0.1:18998/diagnostics/events?flow_id=${flow}`)).json()).items.map((item: any) => item.event);
    return failedEvents.some(event => event.harness?.stage === "document_parse");
  }).toBe(true);
  const processEvents = failedEvents.filter(event => event.request_id === failed.headers()["x-request-id"]);
  expect(processEvents.length).toBeGreaterThan(0);
  expect(processEvents.some(event => event.resource)).toBe(false);
  for (const secret of ["PRIVATE_BAD_PDF", "PRIVATE_BROKEN_PDF_CONTENT", "PRIVATE_RETRY_OBJECTIVE"]) expect(JSON.stringify(failedEvents)).not.toContain(secret);
});

test("Tavern partial replay and explicit child retry correlate their own browser actions", async ({ page, request }) => {
  await page.addInitScript(() => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: "http://127.0.0.1:18998", isDesktop: false, platform: "unknown", secretStorageMode: "plain_text", vaultState: "unconfigured", vaultPath: "", storageRoot: "", startupError: "" };
  });
  await page.goto("/tavern");
  await page.getByRole("button", { name: "新建酒馆", exact: true }).click();
  const setup = page.getByRole("region", { name: "创建房间", exact: true });
  await setup.getByRole("textbox", { name: "标题", exact: true }).fill("Diagnostic partial Tavern");
  await setup.getByRole("checkbox").nth(0).check();
  await setup.getByRole("checkbox").nth(1).check();
  const creating = page.waitForResponse(item => item.url().endsWith("/tavern/rooms") && item.request().method() === "POST");
  await setup.getByRole("button", { name: "创建并进入", exact: true }).click();
  const room = (await (await creating).json()).room;
  const calls: { path: string; method: string; headers: Record<string, string> }[] = [];
  page.on("request", item => {
    if (item.url().includes("/tavern/rooms")) calls.push({ path: new URL(item.url()).pathname, method: item.method(), headers: item.headers() });
  });
  await page.getByRole("checkbox", { name: /^Lyra / }).check();
  await page.getByPlaceholder("输入消息。Enter 发送，Shift + Enter 换行。").fill("PRIVATE_TAVERN_PARTIAL_TRIGGER");
  const replaying = page.waitForResponse(item => item.url().endsWith("/turns") && item.status() === 200);
  await page.getByRole("button", { name: "发送并回应", exact: true }).click();
  const replay = await replaying;
  const partial = await replay.json();
  expect(partial.run.status).toBe("partial");
  expect(partial.generated_messages).toHaveLength(1);
  await expect(page.getByRole("button", { name: "生成中…", exact: true })).toHaveCount(0);
  const posts = calls.filter(item => item.path.endsWith("/turns"));
  expect(posts).toHaveLength(2);
  const originalFlow = posts[0].headers["x-debug-flow-id"];
  expect(originalFlow).toBeTruthy();
  expect(posts[1].headers["x-debug-flow-id"]).toBe(originalFlow);
  expect(posts[1].headers["x-debug-action-id"]).toBe(posts[0].headers["x-debug-action-id"]);
  calls.length = 0;
  const retrying = page.waitForResponse(item => item.url().endsWith(`/${partial.run.id}/retry`));
  await page.getByRole("button", { name: "仅重试未完成角色", exact: true }).first().click();
  const retry = await retrying; expect(retry.status()).toBe(200);
  const child = await retry.json();
  expect(child.run.status).toBe("completed");
  expect(child.run.parent_run_id).toBe(partial.run.id);
  expect(child.generated_messages).toHaveLength(1);
  expect(child.input_message).toBeNull();
  await expect(page.getByText(/^剩余角色已完成回应 · revision/)).toBeVisible();
  await expect.poll(() => calls.filter(item => item.method === "GET").length).toBeGreaterThanOrEqual(2);
  const retryHeaders = retry.request().headers();
  expect(retryHeaders["x-debug-flow-id"]).toBeTruthy();
  expect(retryHeaders["x-debug-flow-id"]).not.toBe(originalFlow);
  expect(calls.every(item => item.headers["x-debug-flow-id"] === retryHeaders["x-debug-flow-id"] && item.headers["x-debug-action-id"] === retryHeaders["x-debug-action-id"])).toBe(true);
  const persisted = (await (await request.get(`http://127.0.0.1:18998/tavern/rooms/${room.id}`)).json()).messages;
  expect(persisted.filter((item: any) => item.author_kind === "user")).toHaveLength(1);
  expect(persisted.filter((item: any) => item.author_kind === "persona")).toHaveLength(2);
  expect(persisted.find((item: any) => item.id === partial.generated_messages[0].id)).toEqual(partial.generated_messages[0]);
  for (const [flowId, expectedRun] of [[originalFlow, partial.run], [retryHeaders["x-debug-flow-id"], child.run]] as const) {
    let events: any[] = [];
    await expect.poll(async () => {
      events = (await (await request.get(`http://127.0.0.1:18998/diagnostics/events?flow_id=${flowId}`)).json()).items.map((item: any) => item.event);
      return events.some(event => event.resource?.resource_id === expectedRun.id);
    }).toBe(true);
    expect(events.some(event => event.harness?.workflow === "tavern")).toBe(true);
    for (const secret of ["PRIVATE_TAVERN_PARTIAL_TRIGGER", "PRIVATE_TAVERN_PARTIAL_FAILURE"]) expect(JSON.stringify(events)).not.toContain(secret);
  }
});

test("Tavern browser cancel inherits the active flow and fences the waiting actor", async ({ page, request }) => {
  await page.addInitScript(() => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: "http://127.0.0.1:18998", isDesktop: false, platform: "unknown", secretStorageMode: "plain_text", vaultState: "unconfigured", vaultPath: "", storageRoot: "", startupError: "" };
  });
  await page.goto("/tavern");
  await page.getByRole("button", { name: "新建酒馆", exact: true }).click();
  const setup = page.getByRole("region", { name: "创建房间", exact: true });
  await setup.getByRole("textbox", { name: "标题", exact: true }).fill("Diagnostic canceled Tavern");
  await setup.getByRole("checkbox").first().check();
  const creating = page.waitForResponse(item => item.url().endsWith("/tavern/rooms") && item.request().method() === "POST");
  await setup.getByRole("button", { name: "创建并进入", exact: true }).click();
  const room = (await (await creating).json()).room;
  const calls: { path: string; method: string; headers: Record<string, string> }[] = [];
  page.on("request", item => { if (item.url().includes("/tavern/rooms")) calls.push({ path: new URL(item.url()).pathname, method: item.method(), headers: item.headers() }); });
  const turning = page.waitForResponse(item => item.url().endsWith(`/${room.id}/turns`));
  await page.getByPlaceholder("输入消息。Enter 发送，Shift + Enter 换行。").fill("PRIVATE_TAVERN_CANCEL_TRIGGER");
  await page.getByRole("button", { name: "发送并回应", exact: true }).click();
  await expect(page.getByRole("button", { name: "取消接收结果", exact: true })).toBeEnabled();
  const canceling = page.waitForResponse(item => item.url().endsWith("/cancel") && item.request().method() === "POST");
  await page.getByRole("button", { name: "取消接收结果", exact: true }).click();
  const canceled = await canceling; expect(canceled.status()).toBe(200);
  const saved = await canceled.json(); expect(saved.run.status).toBe("canceled");
  expect(saved.generated_messages).toHaveLength(0);
  const late = await turning; expect(late.status()).toBe(409);
  await expect(page.getByRole("button", { name: "取消接收结果", exact: true })).toHaveCount(0);
  const turn = calls.find(item => item.path.endsWith("/turns"))!;
  const cancelHeaders = canceled.request().headers();
  expect(turn.headers["x-debug-flow-id"]).toBeTruthy();
  expect(cancelHeaders["x-debug-flow-id"]).toBe(turn.headers["x-debug-flow-id"]);
  expect(cancelHeaders["x-debug-action-id"]).not.toBe(turn.headers["x-debug-action-id"]);
  const reads = calls.filter(item => item.method === "GET" && item.headers["x-debug-action-id"] === cancelHeaders["x-debug-action-id"]);
  expect(reads.length).toBeGreaterThanOrEqual(3);
  expect(reads.every(item => item.headers["x-debug-flow-id"] === cancelHeaders["x-debug-flow-id"])).toBe(true);
  const persisted = await (await request.get(`http://127.0.0.1:18998/tavern/rooms/${room.id}`)).json();
  expect(persisted.messages).toHaveLength(1);
  expect(persisted.messages[0].author_kind).toBe("user");
  let events: any[] = [];
  await expect.poll(async () => {
    events = (await (await request.get(`http://127.0.0.1:18998/diagnostics/events?flow_id=${cancelHeaders["x-debug-flow-id"]}`)).json()).items.map((item: any) => item.event);
    return events.some(event => event.request_id === late.headers()["x-request-id"] && event.status_code === 409);
  }).toBe(true);
  expect(events.some(event => event.harness?.workflow === "tavern")).toBe(true);
  expect(events.some(event => event.request_id === canceled.headers()["x-request-id"] && event.resource?.resource_id === saved.run.id)).toBe(true);
  expect(events.filter(event => event.resource?.resource_type === "tavern_message").every(event => event.resource.resource_id === persisted.messages[0].id)).toBe(true);
  expect(JSON.stringify(events)).not.toContain("PRIVATE_TAVERN_CANCEL_TRIGGER");
});
