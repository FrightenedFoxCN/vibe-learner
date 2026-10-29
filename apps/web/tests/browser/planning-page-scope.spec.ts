import { test, expect } from "@playwright/test";
import { observeRequests } from "./api-fixture";
import { wirePlan } from "../support/learning-wire";
import { wireUnitRevision } from "../support/study-unit-revision-wire";
const api = "http://127.0.0.1:18999";

test("PDF scope draft survives navigation and reload while printed labels remain invalid input", async ({
  page,
}) => {
  await observeRequests(page);
  await page.goto("/plan");
  const field = page.getByRole("textbox", { name: "PDF 物理页范围（可选）" });
  await field.fill("100–103");
  await page.goto("/settings");
  await page.goto("/plan");
  await expect(field).toHaveValue("100–103");
  await page.reload();
  await expect(field).toHaveValue("100–103");
  await field.fill("iv-viii");
  await expect(page.getByRole("alert").filter({ hasText: "物理页" })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "生成计划", exact: true }),
  ).toBeDisabled();
});

test("persisted plan displays PDF 100–103 separately from printed 70–73 after refresh", async ({
  page,
}) => {
  await observeRequests(page);
  const plan = wirePlan();
  plan.persona_id = "fixture-mentor";
  plan.study_units[0].page_end = 104;
  plan.schedule[0].schedule_chapters[0].anchor_page_start = 100;
  plan.schedule[0].schedule_chapters[0].anchor_page_end = 103;
  plan.schedule[0].schedule_chapters[0].content_slices = [
    { page_start: 100, page_end: 103, source_section_ids: ["section-1"] },
  ];
  const unknown = { status: "unknown", value: null };
  Object.assign(plan, {
    planning_intent: {
      schema_version: "planning-intent-v1",
      pdf_page_ranges: {
        status: "user_explicit",
        value: [{ page_start: 100, page_end: 103 }],
      },
      outline_targets: unknown,
      session_count: unknown,
      minutes_per_session: unknown,
      output_language: unknown,
    },
  });
  const document = wireUnitRevision().preview.base_document;
  document.page_count = 104;
  document.study_units[0].page_end = 104;
  document.sections[0].page_end = 104;
  await page.route(`${api}/documents`, (r) =>
    r.fulfill({ json: { items: [document] } }),
  );
  await page.route(`${api}/learning-plans`, (r) =>
    r.fulfill({ json: { items: [plan] } }),
  );
  await page.route(`${api}/documents/document-1/page-numbering?*`, (r) =>
    r.fulfill({
      json: {
        contract_version: "document-page-numbering-v1",
        coordinate_system: "pdf_physical_1_based",
        document_id: "document-1",
        document_revision: 3,
        physical_page_count: 104,
        pages: [
          {
            physical_pdf_page: 100,
            printed_page: { label: "70", source: "pdf_metadata" },
          },
          {
            physical_pdf_page: 103,
            printed_page: { label: "73", source: "pdf_metadata" },
          },
        ],
      },
    }),
  );
  await page.goto("/plan");
  const scope = page.getByRole("region", { name: "计划页码范围", exact: true });
  await expect(scope).toContainText("PDF 物理页范围：100–103");
  await expect(scope).toContainText("PDF 物理第 100 页 → 印刷标签 70");
  await expect(scope).toContainText("PDF 物理第 103 页 → 印刷标签 73");
  await page.reload();
  await expect(scope).toContainText("PDF 物理页范围：100–103");
});
