import { test, expect } from "@playwright/test";
import { observeRequests } from "./api-fixture";
import { wireUnitRevision } from "../support/study-unit-revision-wire";
const api = "http://127.0.0.1:18999";

test("saved OCR progress survives reload, lost resume response only queries, and complete result can proceed", async ({
  page,
}) => {
  await observeRequests(page);
  await page.addInitScript(() =>
    sessionStorage.setItem("vibe-learner:document-checkpoint:v1", "document-1"),
  );
  const document = wireUnitRevision().preview.base_document;
  const source = {
    contract_version: "document-checkpoint-response-v1",
    operation_id: "document-process-op-source",
    document_id: "document-1",
    operation_status: "failed",
    page_count: 2,
    completed_page_count: 1,
    stage: "pages",
    force_ocr: true,
    storage_limited: false,
    child_operation_id: null,
    pages: [
      { page_number: 1, text_preview: "Saved OCR fragment", extraction_source: "ocr" },
    ],
    study_units: [],
    result: null,
    projection_state: "checkpoint_only",
  };
  const child = {
    ...source,
    operation_id: "document-process-op-child",
    operation_status: "committed",
    stage: "study_units",
    completed_page_count: 2,
    study_units: document.study_units,
    result: document,
    projection_state: "committed",
  };
  let posted = 0,
    admitted = false;
  await page.route(`${api}/documents/document-1/checkpoint`, (r) =>
    r.fulfill({ json: admitted ? child : source }),
  );
  await page.route(`${api}/documents/document-1/checkpoints/*`, (r) =>
    r.fulfill({
      json: r.request().url().endsWith(child.operation_id)
        ? child
        : { ...source, child_operation_id: admitted ? child.operation_id : null },
    }),
  );
  await page.route(`${api}/documents/document-1/process`, async (r) => {
    const request = r.request().postDataJSON();
    expect(request.resume_from_operation_id).toBe(source.operation_id);
    expect(request.force_ocr).toBe(true);
    posted++;
    admitted = true;
    await r.abort("failed");
  });
  await page.goto("/plan");
  const panel = page.getByRole("region", { name: "教材处理保存进度", exact: true });
  await expect(panel).toContainText("已保存 1/2 页");
  await expect(panel).toContainText("尚未提交为可学习教材");
  await page.reload();
  await expect(panel).toContainText("已保存 1/2 页");
  await panel.getByRole("button", { name: "从保存进度继续处理", exact: true }).click();
  await expect(panel).toContainText("续跑结果尚未确认");
  await panel.getByRole("button", { name: "查询保存进度", exact: true }).click();
  await expect(panel).toContainText("该次教材处理已提交");
  await expect(
    panel.getByRole("button", { name: "使用该教材生成计划", exact: true }),
  ).toBeEnabled();
  await page.reload();
  await expect(
    panel.getByRole("button", { name: "使用该教材生成计划", exact: true }),
  ).toBeEnabled();
  expect(posted).toBe(1);
});
