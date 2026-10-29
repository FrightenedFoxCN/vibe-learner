import { test, expect } from "@playwright/test";
import { observeRequests } from "./api-fixture";
import { wirePlan } from "../support/learning-wire";
import { wireUnitRevision } from "../support/study-unit-revision-wire";

async function fixture(page: Parameters<typeof observeRequests>[0]) {
  const requests = await observeRequests(page);
  const plan = { ...wirePlan(), persona_id: "fixture-mentor" };
  let current = wireUnitRevision();
  let document = current.preview.base_document;
  const api = "http://127.0.0.1:18999";
  await page.route(`${api}/documents`, route => route.fulfill({ json: { items: [document] } }));
  await page.route(`${api}/learning-plans`, route => route.fulfill({ json: { items: [plan] } }));
  await page.route(`${api}/learning-plans/plan-1/study-unit-revision`, route => route.fulfill({ json: current }));
  await page.route(`${api}/learning-plans/plan-1/study-unit-revision/*/decision`, async route => {
    if (route.request().postDataJSON().decision === "accept") {
      current = wireUnitRevision(true);
      document = current.result!;
      await route.abort("failed");
    } else {
      current.status = "rejected";
      await route.fulfill({ json: current });
    }
  });
  page.on("request", request => {
    if (request.url().startsWith(api) && request.method() === "POST") requests.push({ method: "POST", path: new URL(request.url()).pathname });
  });
  await page.goto("/plan");
  const panel = page.getByRole("region", { name: "教材单元修订", exact: true });
  await expect(panel.getByRole("table")).toBeVisible();
  return { panel, requests, document: () => document };
}

test("preview diff and lost acceptance response recover through GET and reload", async ({ page }) => {
  const h = await fixture(page);
  await expect(h.panel.getByRole("table")).toContainText("修改并保留标识");
  await expect(h.panel.getByRole("table")).toContainText("PDF 1–2");
  await expect(h.panel.getByRole("table")).toContainText("纳入计划");
  await h.panel.getByRole("button", { name: "确认教材修订", exact: true }).click();
  await expect(h.panel).toContainText("暂时无法确认结果");
  await expect(h.panel.getByRole("button", { name: "确认教材修订", exact: true })).toBeDisabled();
  await expect(h.panel.getByRole("button", { name: "拒绝教材修订", exact: true })).toBeDisabled();
  await h.panel.getByRole("button", { name: "查询教材修订结果", exact: true }).click();
  await expect(h.panel).toContainText("教材单元已更新");
  await expect(h.panel).toContainText("当前教材版本 4");
  await page.reload();
  await expect(h.panel).toContainText("教材单元已更新");
  expect(h.requests.filter(request => request.method === "POST")).toHaveLength(1);
});

test("skipping and rejecting preserve the conservative plan and textbook", async ({ page }) => {
  const h = await fixture(page);
  await page.reload();
  await expect(h.panel.getByRole("button", { name: "确认教材修订", exact: true })).toBeEnabled();
  expect(h.requests.filter(request => request.method === "POST")).toHaveLength(0);
  await h.panel.getByRole("button", { name: "拒绝教材修订", exact: true }).click();
  await expect(h.panel).toContainText("教材和当前计划保持原样");
  expect(h.document().revision).toBe(3);
  expect(h.document().study_units[0].title).toBe("Unit 1");
});
