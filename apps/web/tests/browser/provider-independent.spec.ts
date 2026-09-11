import { test, expect } from "@playwright/test";
import { observeRequests } from "./api-fixture";
import { populatedLearning } from "./learning-fixture";

const api = "http://127.0.0.1:18999";
test("independent: late learning snapshot after Manual navigation cannot reanimate owner", async ({ page }, info) => {
  const requests = await observeRequests(page);
  let release!: () => void;
  const gate = new Promise<void>(resolve => { release = resolve; });
  let started = false;
  await page.route(`${api}/documents`, async route => { started = true; await gate; await route.fulfill({ json: { items: [] } }); });
  await page.goto("/plan", { waitUntil: "domcontentloaded" });
  await expect.poll(() => started).toBe(true);
  await page.locator('a[href="/"]').first().click();
  await page.locator('a[href="/manual"]').first().click();
  await expect(page).toHaveURL(/\/manual$/);
  release();
  await page.waitForLoadState("networkidle");
  const boundary = requests.length;
  for (let i = 0; i < 3; i++) await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForLoadState("networkidle");
  expect(requests.slice(boundary)).toEqual([]);
  await page.locator('a[href="/plan"]').first().click();
  await page.waitForLoadState("networkidle");
  await expect(page.getByRole("textbox", { name: "学习目标", exact: true })).toBeVisible();
  expect(requests.every(r => r.method === "GET")).toBe(true);
  await info.attach("requests.json", { body: JSON.stringify(requests), contentType: "application/json" });
});

test("independent: uncertain survives Plan and Manual navigation plus failed read-back without replay", async ({ page }, info) => {
  const h = await populatedLearning(page);
  const key = "independent-pending";
  await page.addInitScript(({ id, unitId, key }) => {
    if (!sessionStorage.getItem("independent-seeded")) {
      localStorage.setItem("vibe-learner:pending-study-chat-operation:v1", JSON.stringify({ sessionId: id, clientRequestId: key, expectedSessionRevision: 1, messageKind: "learner", studyUnitId: unitId }));
      sessionStorage.setItem("independent-seeded", "yes");
    }
  }, { id: h.session.id, unitId: h.unitId, key });
  h.session.prepared_study_unit_ids = [];
  let mode = "uncertain";
  await page.route(`${api}/study-sessions/${h.session.id}/chat-operations/${key}`, route => mode === "offline" ? route.abort("internetdisconnected") : route.fulfill({ json: h.operation(mode, key) }));
  await page.goto("/study");
  const query = page.getByRole("button", { name: "查询本次请求结果", exact: true });
  await expect(query).toBeVisible();
  await page.locator('a[href="/plan"]').first().click();
  await expect(page.getByText("Historical Course", { exact: true }).first()).toBeVisible();
  await page.locator('a[href="/"]').first().click();
  await page.locator('a[href="/manual"]').first().click();
  await page.waitForLoadState("networkidle");
  const boundary = h.requests.length;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.waitForLoadState("networkidle");
  expect(h.requests.length).toBe(boundary);
  await page.locator('a[href="/study"]').first().click();
  await expect(query).toBeVisible();
  mode = "offline";
  await query.click();
  await expect(page.getByText("暂时无法确认本次请求结果。请稍后继续查询，不要重新发送。", { exact: true })).toBeVisible();
  await expect(page.getByRole("button", { name: "请先查询本次请求结果", exact: true })).toBeDisabled();
  expect(JSON.parse((await page.evaluate(() => localStorage.getItem("vibe-learner:pending-study-chat-operation:v1")))!).clientRequestId).toBe(key);
  mode = "uncertain";
  await page.reload();
  await expect(query).toBeVisible();
  h.commitAnswer(); h.session.prepared_study_unit_ids = [h.unitId]; mode = "committed";
  await query.click();
  await expect(page.getByText("Recovered answer", { exact: true })).toBeVisible();
  expect(h.requests.every(r => r.method === "GET")).toBe(true);
  expect(h.requests.filter(r => r.path.includes("chat-operations")).every(r => r.path.endsWith(`/${key}`))).toBe(true);
  expect(await page.evaluate(() => localStorage.getItem("vibe-learner:pending-study-chat-operation:v1"))).toBeNull();
  await info.attach("requests.json", { body: JSON.stringify(h.requests), contentType: "application/json" });
});
