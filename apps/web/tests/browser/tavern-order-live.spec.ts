import { test, expect, type Page } from "@playwright/test";
import { writeFile } from "node:fs/promises";

async function evidence(
  info: import("@playwright/test").TestInfo,
  name: string,
  data: unknown,
) {
  const path = info.outputPath(name);
  await writeFile(path, JSON.stringify(data, null, 2));
  await info.attach(name, { path, contentType: "application/json" });
}

const api = "http://127.0.0.1:18447";
const expectedOrder = ["Bravo", "Charlie", "Alpha"];
const roster = (page: Page) =>
  page.getByRole("region", { name: "角色与目标", exact: true });
const composer = (page: Page) =>
  page.getByRole("region", { name: "发起互动", exact: true });
const row = (page: Page, name: string) =>
  roster(page).locator("label").filter({ hasText: name });
const checkbox = (page: Page, name: string) => row(page, name).getByRole("checkbox");

test.afterEach(async ({ request }) => {
  await request.post(`${api}/__acceptance__/release`);
});

async function room(page: Page, key: string) {
  const ids: Record<string, string> = {};
  for (const name of ["Alpha", "Bravo", "Charlie"]) {
    const response = await page.request.post(`${api}/personas`, {
      data: {
        name,
        summary: "Keep a distinct viewpoint",
        relationship: "peer",
        learner_address: "Learner",
        system_prompt: "Speak only as yourself",
        slots: [],
      },
    });
    expect(response.ok()).toBe(true);
    ids[name] = (await response.json()).id;
  }
  const response = await page.request.post(`${api}/tavern/rooms`, {
    data: {
      title: `Order ${key}`,
      persona_ids: expectedOrder.map((name) => ids[name]),
      idempotency_key: `order-room-${key}`,
    },
  });
  expect(response.ok()).toBe(true);
  const created = await response.json();
  await page.addInitScript(
    (id) => localStorage.setItem("vibe-learner:tavern:active-room", id),
    created.room.id,
  );
  await page.goto("/tavern");
  await expect(roster(page).getByRole("checkbox")).toHaveCount(3);
  await checkbox(page, "Bravo").uncheck();
  for (const name of [...expectedOrder].reverse()) await checkbox(page, name).check();
  await expect(composer(page).locator(".tavern-recipient-preview")).toHaveText(
    "本轮回应：Bravo → Charlie → Alpha",
  );
  expect(await roster(page).locator("strong").allTextContents()).toEqual(expectedOrder);
  return {
    id: created.room.id as string,
    ids,
    participantIds: expectedOrder.map((name) => ids[name]),
  };
}

async function runs(page: Page, roomId: string) {
  return (await (await page.request.get(`${api}/tavern/rooms/${roomId}/runs`)).json())
    .items;
}
async function calls(page: Page, message: string) {
  const observed = await (await page.request.get(`${api}/__acceptance__/calls`)).json();
  return observed.calls.filter((call: { message: string }) => call.message === message);
}

test("reverse selection follows roster order; an in-flight room reload keeps server steps and never repeats committed actors", async ({
  page,
}, info) => {
  const h = await room(page, "restore");
  await page.request.post(`${api}/__acceptance__/configure`, {
    data: { hold: ["Bravo"] },
  });
  const message = "order-restore-round";
  await composer(page)
    .getByRole("textbox", { name: "你的消息", exact: true })
    .fill(message);
  await composer(page)
    .getByRole("button", { name: /发送并回应/ })
    .click();
  await expect(row(page, "Bravo")).toContainText("正在生成");
  await expect(row(page, "Charlie")).toContainText("等待发言");
  await expect(row(page, "Alpha")).toContainText("等待发言");
  await expect.poll(async () => (await calls(page, message)).length).toBe(1);
  const root = (await runs(page, h.id))[0];
  expect(root.scheduled_participant_ids).toEqual(h.participantIds);
  expect(
    root.speaker_steps.map((step: { persona_id: string }) => step.persona_id),
  ).toEqual(h.participantIds);
  await page.reload();
  await expect(composer(page).locator(".tavern-recipient-preview")).toHaveText(
    "本轮回应：Bravo → Charlie → Alpha",
  );
  await expect(row(page, "Bravo")).toContainText("正在生成");
  await expect(row(page, "Charlie")).toContainText("等待发言");
  await page.request.post(`${api}/__acceptance__/release`);
  await expect.poll(async () => (await runs(page, h.id))[0].status).toBe("completed");
  await page.reload();
  for (const name of expectedOrder)
    await expect(row(page, name)).toContainText("上一轮已回应");
  const detail = await (await page.request.get(`${api}/tavern/rooms/${h.id}`)).json();
  expect(
    detail.messages
      .filter((item: { author_kind: string }) => item.author_kind === "persona")
      .map((item: { persona_name: string }) => item.persona_name),
  ).toEqual(expectedOrder);
  expect(
    (await calls(page, message)).map((call: { name: string }) => call.name),
  ).toEqual(expectedOrder);
  await evidence(info, "roster-order-restoration.json", {
    selectedOrder: [...expectedOrder].reverse(),
    rosterOrder: expectedOrder,
    root,
    detail,
    calls: await calls(page, message),
  });
});

test("a partial child retry previews only unfinished actors even after retargeting; completed replies are retained", async ({
  page,
}, info) => {
  const h = await room(page, "partial");
  const message = "order-partial-round";
  await page.request.post(`${api}/__acceptance__/configure`, {
    data: { fail_once: ["Charlie"] },
  });
  await composer(page)
    .getByRole("textbox", { name: "你的消息", exact: true })
    .fill(message);
  await composer(page)
    .getByRole("button", { name: /发送并回应/ })
    .click();
  await expect(
    composer(page).getByRole("button", { name: "仅重试未完成角色", exact: true }),
  ).toBeEnabled();
  const source = (await runs(page, h.id))[0];
  expect(source.status).toBe("partial");
  expect(source.speaker_steps.map((step: { status: string }) => step.status)).toEqual([
    "completed",
    "failed",
    "blocked",
  ]);
  expect(source.scheduled_participant_ids).toEqual(h.participantIds);
  const savedMessageId = source.generated_message_ids[0];
  await page.reload();
  await expect(row(page, "Bravo")).toContainText("上一轮已回应");
  await expect(row(page, "Charlie")).toContainText("上一轮未完成");
  await expect(row(page, "Alpha")).toContainText("上一轮尚未执行");
  for (const name of ["Charlie", "Alpha"]) await checkbox(page, name).uncheck();
  await checkbox(page, "Bravo").check();
  await expect(composer(page).locator(".tavern-recipient-preview")).toHaveText(
    "本轮回应：Bravo",
  );
  await page.request.post(`${api}/__acceptance__/configure`, {
    data: { hold: ["Charlie"] },
  });
  await composer(page)
    .getByRole("button", { name: "仅重试未完成角色", exact: true })
    .click();
  await expect(row(page, "Charlie")).toContainText("正在生成");
  await expect(row(page, "Alpha")).toContainText("等待发言");
  await expect(composer(page).locator(".tavern-recipient-preview")).toHaveText(
    "本轮回应：Charlie → Alpha",
  );
  await expect(row(page, "Bravo")).toContainText("下轮目标");
  await page.screenshot({
    path: "/tmp/vibe-tavern-order-active-retry.png",
    fullPage: true,
    animations: "disabled",
  });
  await page.request.post(`${api}/__acceptance__/release`);
  await expect.poll(async () => (await runs(page, h.id))[0].status).toBe("completed");
  const chain = (
    await (await page.request.get(`${api}/tavern/rooms/${h.id}/run-recovery`)).json()
  ).items[0];
  const child = chain.leaf_run;
  expect(child.parent_run_id).toBe(source.id);
  expect(child.scheduled_participant_ids).toEqual([h.ids.Charlie, h.ids.Alpha]);
  expect(
    child.speaker_steps.map((step: { persona_id: string }) => step.persona_id),
  ).toEqual([h.ids.Charlie, h.ids.Alpha]);
  const detail = await (await page.request.get(`${api}/tavern/rooms/${h.id}`)).json();
  expect(
    detail.messages.filter(
      (item: { author_kind: string }) => item.author_kind === "user",
    ),
  ).toHaveLength(1);
  const replies = detail.messages.filter(
    (item: { author_kind: string }) => item.author_kind === "persona",
  );
  expect(replies.map((item: { persona_name: string }) => item.persona_name)).toEqual(
    expectedOrder,
  );
  expect(replies[0].id).toBe(savedMessageId);
  expect(replies[1].reply_to_message_id).toBe(savedMessageId);
  expect(replies[2].reply_to_message_id).toBe(replies[1].id);
  expect(
    (await calls(page, message)).map((call: { name: string }) => call.name),
  ).toEqual(["Bravo", "Charlie", "Charlie", "Alpha"]);
  await page.reload();
  await expect(composer(page)).toContainText("上次未完成的多人互动已由重试恢复");
  await expect(
    composer(page).getByRole("button", { name: "仅重试未完成角色", exact: true }),
  ).toHaveCount(0);
  await evidence(info, "roster-order-child-retry.json", {
    source,
    child,
    chain,
    detail,
    calls: await calls(page, message),
  });
});
