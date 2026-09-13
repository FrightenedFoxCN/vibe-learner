import { expect, test } from "@playwright/test";

import { populatedLearning } from "./learning-fixture";

test("Plan Workspace uses wide space and exposes explicit form labels", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const fixture = await populatedLearning(page);
  fixture.plan.schedule[0].focus = "Definition 2.1 · PDF 100–103 · X ×_Y Y′ · ".repeat(18);
  await page.goto("/plan");
  await expect(page.getByText("Historical Course", { exact: true }).first()).toBeVisible();

  const layout = await page.locator(".plan-content-grid").evaluate((grid) => {
    const setup = grid.querySelector(".plan-setup-shell")!.getBoundingClientRect();
    const main = grid.querySelector(".plan-main-column")!.getBoundingClientRect();
    const whole = grid.getBoundingClientRect();
    return { wholeWidth: whole.width, setupWidth: setup.width, mainWidth: main.width, gap: main.left - setup.right };
  });
  expect(layout.wholeWidth).toBeGreaterThan(1000);
  expect(layout.mainWidth).toBeGreaterThan(layout.setupWidth * 1.5);
  expect(layout.gap).toBeGreaterThanOrEqual(20);

  const focus = page.getByText(/Definition 2\.1/).first();
  await expect(focus).toBeVisible();
  expect(await focus.evaluate((node) => ({
    wraps: getComputedStyle(node).whiteSpace === "pre-wrap",
    contained: node.scrollWidth <= node.clientWidth,
    selectable: getComputedStyle(node).userSelect === "text",
  }))).toEqual({ wraps: true, contained: true, selectable: true });

  for (const [id, label] of [
    ["plan-persona", "教师人格"],
    ["plan-scene", "计划场景"],
    ["plan-generation-mode", "创建方式"],
    ["plan-document-file", "教材文件（PDF）"],
    ["plan-objective", "学习目标"],
  ] as const) {
    const control = page.locator(`#${id}`);
    await expect(control).toHaveCount(1);
    await expect(page.locator(`label[for="${id}"]`, { hasText: label })).toHaveCount(1);
  }
  await expect(page.getByRole("textbox", { name: "学习目标", exact: true })).toBeVisible();
});

test("Plan Workspace shows a long PDF filename once with an inspectable full value", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  await populatedLearning(page);
  await page.goto("/plan");
  const filename = `${"algebraic-geometry-reference-".repeat(8)}volume-one.pdf`;
  await page.locator("#plan-document-file").setInputFiles({
    name: filename,
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4 test"),
  });

  const filenameNode = page.locator(".plan-file-name");
  await expect(filenameNode).toHaveText(filename);
  await expect(filenameNode).toHaveAttribute("title", filename);
  await expect(page.getByText(filename, { exact: true })).toHaveCount(1);
  expect(await filenameNode.evaluate((node) => node.scrollWidth > node.clientWidth)).toBe(true);
});

test("Plan Workspace presents four sessions as distinct course atoms", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const fixture = await populatedLearning(page);
  const plan: any = fixture.plan;
  const template = plan.schedule[0];
  plan.today_tasks = ["Complete the first definition recall.", "Check the worked example steps."];
  plan.output_language = "en";
  plan.schedule = Array.from({ length: 4 }, (_, index) => ({
    ...structuredClone(template),
    id: `schedule-course-${index + 1}`,
    title: `Course ${index + 1}`,
    focus: `Independent task for course ${index + 1}.`,
    duration_minutes: 45,
    status: index === 1 ? "completed" : "planned",
    schedule_chapters: template.schedule_chapters.map((chapter: any, chapterIndex: number) => ({
      ...structuredClone(chapter),
      id: `schedule-course-${index + 1}:chapter-${chapterIndex + 1}`,
    })),
  }));
  plan.resolved_planning_intent = {
    schema_version: "planning-resolved-intent-v1",
    pdf_page_ranges: {
      source: "model_inferred",
      value: [{ page_start: 1, page_end: 2 }],
    },
    outline_targets: { source: "model_inferred", value: [] },
    session_count: { source: "model_inferred", value: 4 },
    minutes_per_session: { source: "model_inferred", value: 45 },
    output_language: { source: "model_inferred", value: "en" },
  };
  plan.progress_summary = {
    total_schedule_count: 4,
    completed_schedule_count: 1,
    in_progress_schedule_count: 0,
    pending_schedule_count: 3,
    blocked_schedule_count: 0,
    completion_percent: 25,
  };
  plan.study_unit_progress[0] = {
    ...plan.study_unit_progress[0],
    schedule_ids: plan.schedule.map((item: any) => item.id),
    total_schedule_count: 4,
    completed_schedule_count: 1,
    in_progress_schedule_count: 0,
    pending_schedule_count: 3,
    blocked_schedule_count: 0,
    completion_percent: 25,
    status: "in_progress",
  };
  plan.progress_events = [{
    id: "review-course-2",
    actor: "user",
    source: "ui",
    schedule_ids: ["schedule-course-2"],
    status: "completed",
    note: "Course 2 review is persisted independently.",
    created_at: "2026-09-13T10:00:00+08:00",
  }];

  await page.goto("/plan");
  await expect(page.locator("[data-plan-schedule]")).toHaveCount(4);
  await expect(page.getByText("今日行动", { exact: true })).toBeVisible();
  await expect(page.getByText("Complete the first definition recall.", { exact: true })).toBeVisible();

  for (let index = 1; index <= 4; index += 1) {
    const card = page.locator(`[data-plan-schedule="schedule-course-${index}"]`);
    await expect(card.getByText(`第 ${index} 课`, { exact: true })).toBeVisible();
    await expect(card.getByText("时长 45 分钟", { exact: true })).toBeVisible();
    await expect(card.getByText("范围 p.1–2", { exact: true })).toBeVisible();
    await expect(card.getByText("本次任务", { exact: true })).toBeVisible();
    await expect(card.getByRole("button", { name: `开始第 ${index} 课：Course ${index}` })).toBeVisible();
    await expect(card.getByRole("button", { name: `完成第 ${index} 课：Course ${index}` })).toBeVisible();
  }

  const second = page.locator('[data-plan-schedule="schedule-course-2"]');
  await second.getByText(/复盘与进度记录/).click();
  await expect(second.getByRole("textbox", { name: "第 2 课复盘" })).toBeVisible();
  await expect(second.getByText("Course 2 review is persisted independently.", { exact: true })).toBeVisible();
});
