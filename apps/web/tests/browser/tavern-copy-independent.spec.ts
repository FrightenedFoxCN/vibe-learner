import { test, expect } from "@playwright/test";
import { tavernFixture } from "./tavern-copy-fixture";
const api = "http://127.0.0.1:18999";

for (const status of ["partial", "failed"] as const) {
  test(`independent Tavern copy: ${status} has readable primary feedback and blocked is unexecuted`, async ({ page }, info) => {
    const h = await tavernFixture(page, status);
    const roster = page.getByRole("region", { name: "角色与目标", exact: true });
    for (const checkbox of await roster.getByRole("checkbox").all()) await checkbox.check();
    await page.getByRole("textbox", { name: "你的消息", exact: true }).fill("Independent round");
    await page.getByRole("button", { name: "发送并回应", exact: false }).click();
    await expect.poll(() => h.getRun()?.status).toBe(status);
    const details = page.locator("details.reliability-details");
    await expect(details).not.toHaveAttribute("open", "");
    const blocked = roster.locator("label").filter({ hasText: "Blocked Actor" });
    await expect(blocked).toContainText("上一轮尚未执行");
    await expect(blocked).not.toContainText(/回应失败|角色失败/);
    await expect(page.getByText(status === "partial" ? "部分角色回应未完成；已保存的回应不会重复生成，可在下方仅恢复未完成角色。" : "本轮角色回应未完成；可从恢复入口继续尚未完成的角色。", { exact: true })).toBeVisible();
    const visibleText = await page.locator("body").innerText();
    expect(visibleText).not.toMatch(/INDEPENDENT_.*RAW_CODE|tavern_[a-z_]+/);
    await details.locator("summary").click();
    await expect(details).toContainText(/因前序回应未完成而暂未执行/);
    await expect(details.getByRole("button", { name: "仅重试未完成角色", exact: true })).toBeEnabled();
    if (status === "partial") await expect(page.getByText("Committed actor reply", { exact: true })).toBeVisible();
    await info.attach("visible-copy.json", { body: JSON.stringify({ status, visibleText, details: await details.innerText() }), contentType: "application/json" });
  });
}

test("independent Tavern copy: archived room explicitly stays read-only", async ({ page }) => {
  await tavernFixture(page, "failed", true);
  await expect(page.getByRole("textbox", { name: "你的消息", exact: true })).toBeDisabled();
  await expect(page.getByRole("textbox", { name: "你的消息", exact: true })).toHaveAttribute("placeholder", "归档房间为只读状态。");
  await expect(page.getByText(/已打开归档房间（只读）/)).toBeVisible();
});

for (const [code, expectedCopy] of [
  ["tavern_retry_context_changed", "房间内容或角色设定已变化，不能继续旧恢复任务。"],
  ["UNKNOWN_INDEPENDENT_PRIVATE_CODE", "重试未完整返回；已重新同步已保存的结果。"],
] as const) {
  test(`independent Tavern copy: retry error ${code} stays readable without raw leakage`, async ({ page }, info) => {
    await tavernFixture(page, "partial");
    const roster = page.getByRole("region", { name: "角色与目标", exact: true });
    for (const checkbox of await roster.getByRole("checkbox").all()) await checkbox.check();
    await page.getByRole("textbox", { name: "你的消息", exact: true }).fill("Independent round");
    await page.getByRole("button", { name: "发送并回应", exact: false }).click();
    await expect(page.getByText("Committed actor reply", { exact: true })).toBeVisible();
    let retries = 0;
    await page.route(`${api}/tavern/rooms/copy-room/runs/copy-run/retry`, route => {
      retries++;
      return route.fulfill({ status: 409, json: { detail: { code, run_id: "copy-run", child_run_id: "", current_revision: 1, recovery_action: "reload_room" } } });
    });
    const composer = page.getByRole("region", { name: "发起互动", exact: true });
    await composer.getByRole("button", { name: "仅重试未完成角色", exact: true }).click();
    await expect(page.getByText(expectedCopy, { exact: true })).toBeVisible();
    expect(retries).toBe(1);
    const visibleText = await page.locator("body").innerText();
    expect(visibleText).not.toContain(code);
    expect(visibleText).not.toMatch(/INDEPENDENT_.*RAW_CODE|当前叶节点/);
    await expect(page.getByText("Committed actor reply", { exact: true })).toBeVisible();
    await info.attach("retry-visible-copy.json", { body: JSON.stringify({ code, visibleText }), contentType: "application/json" });
  });
}
