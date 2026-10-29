import { test, expect, type Page } from "@playwright/test";

const api = "http://127.0.0.1:18445";
const pendingKey = "vibe-learner:pending-study-chat-operation:v1";

test.afterEach(async ({ request }) => {
  await request.post(`${api}/__acceptance__/release`);
});

async function openStudy(page: Page, name: string) {
  const persona = (await (await page.request.get(`${api}/personas`)).json()).items[0];
  const planResponse = await page.request.post(`${api}/learning-plans`, {
    data: {
      client_request_id: `recovery-plan-${name}`,
      document_id: "",
      persona_id: persona.id,
      objective: "Study vectors",
      planning_intent: { output_language: { status: "user_explicit", value: "en" } },
    },
  });
  expect(planResponse.ok()).toBe(true);
  const plan = await planResponse.json();
  await page.goto(`/study?plan=${encodeURIComponent(plan.id)}`);
  const create = page.getByRole("button", { name: "创建会话", exact: true });
  await expect(create).toBeVisible();
  await create.click();
  const composer = page.getByRole("textbox", { name: /^向.*提问$/ });
  await expect(composer).toBeEnabled();
  await expect(page.getByRole("button", { name: "发送", exact: true })).toBeEnabled();
  return composer;
}

test("a timed-out POST remains running on the real server; bounded polling and reload only read the original operation", async ({
  page,
}) => {
  const composer = await openStudy(page, "timeout");
  await page.clock.install();
  const learnerWrites: string[] = [];
  page.on("request", (request) => {
    if (
      request.url().endsWith("/chat") &&
      request.method() === "POST" &&
      request.postDataJSON().message_kind === "learner"
    )
      learnerWrites.push(request.postDataJSON().client_request_id);
  });
  await composer.fill("hold:long-browser-wait");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect
    .poll(async () =>
      (
        await (await page.request.get(`${api}/__acceptance__/calls`)).json()
      ).messages.includes("hold:long-browser-wait"),
    )
    .toBe(true);
  await page.clock.runFor(60_000);
  await expect(page.getByText(/等待本次请求结果超时/)).toBeVisible();
  const identity = await page.evaluate(
    (key) => JSON.parse(localStorage.getItem(key)!),
    pendingKey,
  );
  const endpoint = `${api}/study-sessions/${identity.sessionId}/chat-operations/${identity.clientRequestId}`;
  expect((await (await page.request.get(endpoint)).json()).status).toBe("running");
  const query = page.getByRole("button", { name: "查询本次请求结果", exact: true });
  await query.click();
  for (const delay of [2000, 4000, 8000, 15000, 30000, 30000]) {
    await expect(query).toBeEnabled();
    await page.clock.runFor(delay);
  }
  await expect(page.getByText(/自动查询已暂停（已查询 6 次）/)).toBeVisible();
  expect(learnerWrites).toEqual([identity.clientRequestId]);
  await page.request.post(`${api}/__acceptance__/release`);
  await expect
    .poll(async () => (await (await page.request.get(endpoint)).json()).status)
    .toBe("committed");
  await query.click();
  await expect(query).toHaveCount(0);
  await page.reload();
  await expect(page.getByText("hold:long-browser-wait", { exact: true })).toBeVisible();
  expect(
    await page.evaluate((key) => localStorage.getItem(key), pendingKey),
  ).toBeNull();
  expect(learnerWrites).toHaveLength(1);
});

test("uncertain survives offline reconnect and reload without resending; changed same-key payload remains rejected", async ({
  page,
  context,
}) => {
  const composer = await openStudy(page, "uncertain");
  const posts: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      request.url().endsWith("/chat") &&
      request.postDataJSON().message_kind === "learner"
    )
      posts.push(request.postDataJSON().client_request_id);
  });
  await composer.fill("uncertain:do-not-replay");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(
    page
      .getByRole("region", { name: "学习对话", exact: true })
      .getByText(/等待或刷新不能证明没有产生影响/),
  ).toBeVisible();
  const identity = await page.evaluate(
    (key) => JSON.parse(localStorage.getItem(key)!),
    pendingKey,
  );
  const mismatch = await page.request.post(
    `${api}/study-sessions/${identity.sessionId}/chat`,
    {
      data: {
        client_request_id: identity.clientRequestId,
        expected_session_revision: identity.expectedSessionRevision,
        message: "changed same key",
        message_kind: "learner",
        output_language: "en",
      },
    },
  );
  expect(mismatch.status()).toBe(409);
  await context.setOffline(true);
  await expect(page.getByText(/浏览器当前离线，无法确认请求结果/)).toBeVisible();
  await context.setOffline(false);
  await expect(
    page
      .getByRole("region", { name: "学习对话", exact: true })
      .getByText(/等待或刷新不能证明没有产生影响/),
  ).toBeVisible();
  await page.reload();
  await expect(
    page.getByRole("button", { name: "请先查询本次请求结果", exact: true }),
  ).toBeDisabled();
  expect(posts).toEqual([identity.clientRequestId]);
  expect(
    (
      await (await page.request.get(`${api}/__acceptance__/calls`)).json()
    ).messages.filter((message: string) => message === "uncertain:do-not-replay"),
  ).toHaveLength(1);
});

test("not-committed reload explains the terminal outcome without resending the restored draft", async ({
  page,
}) => {
  const composer = await openStudy(page, "rejected");
  const posts: string[] = [];
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      request.url().endsWith("/chat") &&
      request.postDataJSON().message_kind === "learner"
    )
      posts.push(request.postDataJSON().client_request_id);
  });
  await composer.fill("reject:invalid-reply");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "重新发送（新请求）", exact: true }),
  ).toBeVisible();
  await page.reload();
  await expect(page.getByText(/恢复记录不保存原消息或附件/)).toBeVisible();
  await expect(page.getByText("已确认本次回复未保存", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "重新发送（新请求）", exact: true }),
  ).toHaveCount(0);
  expect(posts).toHaveLength(1);
});
