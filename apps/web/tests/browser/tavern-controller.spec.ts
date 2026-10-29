import { test, expect } from "@playwright/test";
import { tavernFixture } from "./tavern-copy-fixture";

test("Tavern composition keeps roster display order and mobile DOM flow after the controller split", async ({
  page,
}) => {
  await tavernFixture(page, "partial");
  await page.setViewportSize({ width: 390, height: 844 });
  const roster = page.getByRole("region", { name: "角色与目标", exact: true });
  const boxes = await roster.getByRole("checkbox").all();
  for (const box of [...boxes].reverse()) await box.check();
  await expect(
    page.getByText("本轮回应：Completed Actor → Failed Actor → Blocked Actor", {
      exact: true,
    }),
  ).toBeVisible();
  const flow = await page
    .locator(".tavern-workspace-grid")
    .evaluate((node) => [...node.children].map((child) => child.className));
  expect(flow).toEqual([
    "tavern-left-rail",
    "tavern-right-rail",
    "tavern-panel tavern-conversation-panel",
  ]);
  const composer = page.getByRole("region", { name: "发起互动", exact: true });
  const conversation = page.getByRole("region", {
    name: "对话记录",
    exact: true,
  });
  const composerBox = await composer.boundingBox(),
    conversationBox = await conversation.boundingBox();
  expect(composerBox!.y).toBeLessThan(conversationBox!.y);
  const input = page.getByRole("textbox", { name: "你的消息", exact: true });
  await input.fill("Controller browser round");
  await page.getByRole("button", { name: /发送并回应/ }).click();
  await expect(
    page.getByText("Committed actor reply", { exact: true }),
  ).toBeVisible();
  await expect(input).toHaveValue("");
  await expect(input).toBeFocused();
});
