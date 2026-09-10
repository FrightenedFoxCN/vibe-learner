import { test, expect } from "@playwright/test";
import { populatedLearning } from "./learning-fixture";

const api = "http://127.0.0.1:18999";

test("historical goal-only Plan and Session restore across routes without new generation", async ({ page }) => {
  const h = await populatedLearning(page);
  await page.goto("/study");
  await expect(page.getByText("Historical answer", { exact: true })).toBeVisible();
  const question = page.getByRole("textbox", { name: "向Fixture Mentor提问", exact: true });
  await question.fill("Keep my unsent question");
  await page.locator('a[href="/plan"]').first().click();
  await expect(page.getByText("Historical Course", { exact: true }).first()).toBeVisible();
  await page.locator('a[href="/settings"]').first().click();
  await page.locator('a[href="/study"]').first().click();
  await expect(page.getByText("Historical answer", { exact: true })).toBeVisible();
  await expect(question).toHaveValue("Keep my unsent question");
  expect(h.requests.every(request => request.method === "GET")).toBe(true);
});

test("refresh queries the original uncertain operation; manual read-back unlocks the committed reply", async ({ page }) => {
  const h = await populatedLearning(page);
  await page.addInitScript(({ id, unitId }) => {
    localStorage.setItem("vibe-learner:pending-study-chat-operation:v1", JSON.stringify({ sessionId: id, clientRequestId: "pending-learner", expectedSessionRevision: 1, messageKind: "learner", studyUnitId: unitId }));
  }, { id: h.session.id, unitId: h.unitId });
  h.session.prepared_study_unit_ids = [];
  let committed = false;
  await page.route(`${api}/study-sessions/${h.session.id}/chat-operations/pending-learner`, route => route.fulfill({ json: h.operation(committed ? "committed" : "uncertain") }));
  await page.goto("/study");
  const query = page.getByRole("button", { name: "查询本次请求结果", exact: true });
  await expect(query).toBeVisible();
  await expect(page.getByRole("button", { name: "请先查询本次请求结果", exact: true })).toBeDisabled();
  await page.reload();
  await expect(query).toBeVisible();
  h.commitAnswer(); h.session.prepared_study_unit_ids = [h.unitId]; committed = true;
  await query.click();
  await expect(page.getByText("Recovered answer", { exact: true })).toBeVisible();
  await expect(query).toHaveCount(0);
  expect(h.requests.filter(request => request.path.includes("chat-operations")).length).toBe(3);
  expect(h.requests.every(request => request.method === "GET")).toBe(true);
  expect(await page.evaluate(() => localStorage.getItem("vibe-learner:pending-study-chat-operation:v1"))).toBeNull();
});

test("leaving with a chat POST in flight recovers by query on return without another POST", async ({ page }) => {
  const h = await populatedLearning(page);
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  let requestId = "";
  await page.route(`${api}/study-sessions/${h.session.id}/chat`, async route => {
    requestId = route.request().postDataJSON().client_request_id;
    await pending;
    await route.abort("failed");
  });
  await page.route(`${api}/study-sessions/${h.session.id}/chat-operations/*`, route => route.fulfill({ json: h.operation("committed", requestId) }));
  await page.goto("/study");
  await expect(page.getByText("Historical answer", { exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "向Fixture Mentor提问", exact: true }).fill("Recover my question");
  const sent = page.waitForRequest(request => request.method() === "POST" && request.url().endsWith("/chat"));
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await sent;
  await page.locator('a[href="/settings"]').first().click();
  await expect(page).toHaveURL(/\/settings$/);
  h.commitAnswer(); release();
  await page.locator('a[href="/study"]').first().click();
  await expect(page.getByText("Recovered answer", { exact: true })).toBeVisible();
  await expect.poll(() => h.requests.filter(request => request.path.includes("chat-operations")).length).toBe(1);
  expect(requestId).not.toBe("");
  expect(h.requests.filter(request => request.method === "POST")).toHaveLength(1);
});
