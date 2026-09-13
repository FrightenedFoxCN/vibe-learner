import { expect, test } from "@playwright/test";

import { populatedLearning } from "./learning-fixture";

function addPresentationEvidence(turn: Record<string, any>) {
  turn.character_events = [{
    emotion: "calm",
    action: "points to the diagram",
    speech_style: "steady",
    scene_hint: "Unit 1, pages 1-2",
    line_segment_id: "session-1:chat:0",
    timing_hint: "instant",
    tool_name: "read_page_range_content",
    tool_summary: "Read pages 1–2 from the protected textbook snapshot.",
    delivery_cue: "Speak slowly and pause after the definition.",
    commentary: "",
  }];
  turn.tool_calls = [{
    tool_call_id: "call-presentation-1",
    tool_name: "read_page_range_content",
    arguments_json: "{}",
    result_summary: "Read pages 1–2 from the protected textbook snapshot.",
    result_json: "{}",
  }];
}

test("Study Dialog keeps the conversation continuous and separates status responsibilities", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 1000 });
  const fixture = await populatedLearning(page);
  fixture.session.turns[0].assistant_reply = "Persisted teacher explanation is the primary content.";
  addPresentationEvidence(fixture.session.turns[0]);

  await page.goto("/study");
  await expect(page.getByText("Persisted teacher explanation is the primary content.", { exact: true })).toBeVisible();

  const layout = await page.locator(".study-console-layout").evaluate((grid) => {
    const conversation = grid.querySelector<HTMLElement>('[aria-label="学习对话"]')!.getBoundingClientRect();
    const sidebar = grid.querySelector<HTMLElement>("aside")!.getBoundingClientRect();
    const transcript = grid.querySelector<HTMLElement>(".study-transcript")!.getBoundingClientRect();
    const composer = grid.querySelector<HTMLElement>(".study-composer")!.getBoundingClientRect();
    return {
      width: grid.getBoundingClientRect().width,
      conversationWidth: conversation.width,
      sidebarWidth: sidebar.width,
      transcriptWidth: transcript.width,
      composerGap: composer.top - transcript.bottom,
    };
  });
  expect(layout.width).toBeGreaterThan(1100);
  expect(layout.conversationWidth).toBeGreaterThan(760);
  expect(layout.transcriptWidth).toBeGreaterThan(740);
  expect(layout.sidebarWidth).toBeGreaterThanOrEqual(280);
  expect(layout.composerGap).toBeGreaterThanOrEqual(0);
  expect(layout.composerGap).toBeLessThanOrEqual(24);

  const actionNotice = page.locator("[data-study-action-notice]");
  await expect(actionNotice).toContainText("操作反馈");
  await expect(page.locator('[data-study-status="session"]')).toHaveText("会话已建立");
  await expect(page.locator('[data-study-status="sync"]')).toHaveText("记录同步已同步");
  await expect(page.locator('[data-study-status="model"]')).toHaveText("模型空闲");
  await expect(page.getByText("角色状态", { exact: true })).toBeVisible();
  await expect(page.getByText("待开始", { exact: true })).toBeVisible();
});

test("Study Dialog progressively discloses performance cues and tool receipts", async ({ page }) => {
  const fixture = await populatedLearning(page);
  addPresentationEvidence(fixture.session.turns[0]);

  await page.goto("/study");
  const details = page.locator("[data-study-event-details]").first();
  await expect(details).not.toHaveAttribute("open", "");
  await expect(details.getByText("角色动作", { exact: true })).not.toBeVisible();
  await expect(details.getByText("表达提示", { exact: true })).not.toBeVisible();
  await expect(details.getByText("工具回执", { exact: true })).not.toBeVisible();

  await details.getByText(/表演与工具详情/).click();
  await expect(details).toHaveAttribute("open", "");
  await expect(details.getByText("角色动作", { exact: true })).toBeVisible();
  await expect(details.getByText("表达提示", { exact: true })).toBeVisible();
  await expect(details.getByText("工具回执", { exact: true })).toBeVisible();
  await expect(details.locator("p", { hasText: "Read pages 1–2 from the protected textbook snapshot." })).toBeVisible();
});
