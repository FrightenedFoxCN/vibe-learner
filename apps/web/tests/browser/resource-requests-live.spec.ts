import { test, expect, type Page, type Request, type TestInfo } from "@playwright/test";
import { writeFile } from "node:fs/promises";

const api = "http://127.0.0.1:18447";
const before = process.env.WEB_DEDUPE_PHASE === "before";
const learningResources = [
  "/documents",
  "/learning-plans",
  "/personas",
  "/scene-library",
];

function observe(page: Page) {
  let phase = "bootstrap";
  const start = performance.now();
  const records: {
    phase: string;
    method: string;
    path: string;
    startMs: number;
    endMs?: number;
    status?: number;
    failure?: string;
  }[] = [];
  const pending = new Map<Request, (typeof records)[number]>();
  page.on("request", (request) => {
    if (!request.url().startsWith(api + "/") || request.url().includes("/diagnostics/"))
      return;
    const url = new URL(request.url());
    const record = {
      phase,
      method: request.method(),
      path: url.pathname + url.search,
      startMs: performance.now() - start,
    };
    records.push(record);
    pending.set(request, record);
  });
  page.on("response", (response) => {
    const record = pending.get(response.request());
    if (record) record.status = response.status();
  });
  page.on("requestfinished", (request) => {
    const record = pending.get(request);
    if (record) record.endMs = performance.now() - start;
  });
  page.on("requestfailed", (request) => {
    const record = pending.get(request);
    if (record) {
      record.endMs = performance.now() - start;
      record.failure = request.failure()?.errorText;
    }
  });
  return {
    records,
    phase: (name: string) => {
      phase = name;
    },
    count: (name: string, path: string) =>
      records.filter(
        (record) =>
          record.phase === name &&
          record.path.split("?")[0] === path &&
          record.method === "GET",
      ).length,
    settled: async () => {
      // networkidle can already be satisfied while routed requests are queued;
      // observe actual finished/failed wire records before closing the phase.
      await page.waitForTimeout(100);
      await expect
        .poll(() => records.filter((record) => record.endMs === undefined).length, {
          timeout: 15000,
        })
        .toBe(0);
    },
  };
}

async function save(info: TestInfo, name: string, payload: unknown) {
  const path = info.outputPath(name);
  await writeFile(path, JSON.stringify(payload, null, 2));
  await info.attach(name, { path, contentType: "application/json" });
}

async function fixture(page: Page, key: string) {
  const personas = [];
  for (const name of ["Focus A", "Focus B"]) {
    const response = await page.request.post(`${api}/personas`, {
      data: {
        name: `${name} ${key}`,
        summary: "Synthetic focus fixture",
        relationship: "peer",
        learner_address: "Learner",
        system_prompt: "Speak only as yourself",
        slots: [],
      },
    });
    expect(response.ok()).toBe(true);
    personas.push(await response.json());
  }
  const created = await page.request.post(`${api}/tavern/rooms`, {
    data: {
      title: `History ${key}`,
      persona_ids: personas.map((persona) => persona.id),
      idempotency_key: `request-history-${key}`,
    },
  });
  const detail = await created.json();
  const turn = await page.request.post(`${api}/tavern/rooms/${detail.room.id}/turns`, {
    data: {
      input: { kind: "user_message", content: `historical-${key}` },
      mode: "facilitated",
      target_persona_ids: personas.map((persona) => persona.id),
      idempotency_key: `historical-turn-${key}`,
      expected_room_revision: 0,
    },
  });
  expect(turn.ok()).toBe(true);
  const planResponse = await page.request.post(`${api}/learning-plans`, {
    data: {
      document_id: "",
      persona_id: personas[0].id,
      objective: "Study vectors",
      client_request_id: `history-plan-${key}`,
    },
  });
  expect(planResponse.ok()).toBe(true);
  const plan = await planResponse.json();
  await page.addInitScript(
    ({ roomId, planId, personaId }) => {
      localStorage.setItem("vibe-learner:tavern:active-room", roomId);
      sessionStorage.setItem(
        "vibe-learner:learning-workspace-page-cache:v1",
        JSON.stringify({ selection: { planId, personaId, sceneLibraryId: "" } }),
      );
    },
    { roomId: detail.room.id, planId: plan.id, personaId: personas[0].id },
  );
  return { roomId: detail.room.id as string, personas };
}

test.afterEach(async ({ request }) => {
  await request.post(`${api}/__acceptance__/release`);
});

test("populated focus bursts, Plan/Study navigation and return refreshes have bounded resource reads", async ({
  page,
}, info) => {
  const h = await fixture(page, "focus");
  const trace = observe(page);
  await page.goto("/plan");
  await page.waitForLoadState("networkidle");
  await trace.settled();
  for (const path of learningResources) {
    await page.route(`${api}${path}`, async (route) => {
      const response = await route.fetch();
      await new Promise((resolve) => setTimeout(resolve, 300));
      await route.fulfill({ response });
    });
  }
  trace.phase("focus-burst");
  await page.evaluate(() => {
    for (let i = 0; i < 8; i++) window.dispatchEvent(new Event("focus"));
  });
  await page.waitForLoadState("networkidle");
  await trace.settled();
  const focusCounts = Object.fromEntries(
    learningResources.map((path) => [path, trace.count("focus-burst", path)]),
  );
  await save(info, "focus-burst-counts.json", { before, focusCounts });
  if (!before)
    expect(focusCounts).toEqual(
      Object.fromEntries(learningResources.map((path) => [path, 1])),
    );
  trace.phase("plan-to-study");
  await page.locator('a[href="/study"]').first().click();
  await expect(page).toHaveURL(/\/study$/);
  await page.waitForLoadState("networkidle");
  await trace.settled();
  for (const path of learningResources)
    expect(trace.count("plan-to-study", path)).toBe(0);
  trace.phase("leave-learning");
  await page.locator('a[href="/tavern"]').first().click();
  await expect(page).toHaveURL(/\/tavern$/);
  await page.waitForLoadState("networkidle");
  await trace.settled();
  expect(
    (await (await page.request.get(`${api}/tavern/rooms/${h.roomId}/runs`)).json())
      .items,
  ).toHaveLength(1);
  trace.phase("tavern-focus");
  await page.evaluate(() => {
    for (let i = 0; i < 8; i++) window.dispatchEvent(new Event("focus"));
  });
  await page.waitForLoadState("networkidle");
  await trace.settled();
  expect(
    trace.records.filter((record) => record.phase === "tavern-focus"),
  ).toHaveLength(0);
  trace.phase("return-with-focus");
  await page.locator('a[href="/plan"]').first().click();
  await expect(page).toHaveURL(/\/plan$/);
  await expect(
    page.getByRole("textbox", { name: "学习目标", exact: true }),
  ).toBeVisible();
  await page.evaluate(() => {
    for (let i = 0; i < 8; i++) window.dispatchEvent(new Event("focus"));
  });
  await page.waitForLoadState("networkidle");
  await trace.settled();
  const returnCounts = Object.fromEntries(
    learningResources.map((path) => [path, trace.count("return-with-focus", path)]),
  );
  if (!before)
    for (const path of learningResources)
      expect(returnCounts[path], path).toBeLessThanOrEqual(2);
  await save(info, "resource-request-timeline.json", {
    before,
    fixture: { roomId: h.roomId, historicalRuns: 1 },
    focusCounts,
    returnCounts,
    records: trace.records,
  });
  await page.unrouteAll({ behavior: "wait" });
});

test("slow Tavern polls and lost-response recovery retain fresh read-back without replaying the historical or current turn", async ({
  page,
}, info) => {
  const h = await fixture(page, "recovery");
  const trace = observe(page);
  await page.goto("/tavern");
  await page.waitForLoadState("networkidle");
  const roster = page.getByRole("region", { name: "角色与目标", exact: true });
  await roster.getByRole("checkbox").nth(1).check();
  let activePolls = 0,
    maxActivePolls = 0;
  await page.route(`${api}/tavern/rooms/${h.roomId}/runs?*`, async (route) => {
    activePolls++;
    maxActivePolls = Math.max(maxActivePolls, activePolls);
    const response = await route.fetch();
    await new Promise((resolve) => setTimeout(resolve, 1400));
    await route.fulfill({ response });
    activePolls--;
  });
  await page.route(`${api}/tavern/rooms/${h.roomId}/turns`, async (route) => {
    await route.fetch(); // The real request commits before its response is lost.
    await route.abort("failed");
  });
  await page.request.post(`${api}/__acceptance__/configure`, {
    data: { hold: [h.personas[0].name] },
  });
  trace.phase("poll-and-focus");
  await page
    .getByRole("textbox", { name: "你的消息", exact: true })
    .fill("dedupe-recovery-round");
  await page.getByRole("button", { name: /发送并回应/ }).click();
  await expect
    .poll(
      async () =>
        (
          await (await page.request.get(`${api}/__acceptance__/calls`)).json()
        ).calls.filter(
          (call: { message: string }) => call.message === "dedupe-recovery-round",
        ).length,
    )
    .toBe(1);
  await page.evaluate(() => {
    for (let i = 0; i < 8; i++) window.dispatchEvent(new Event("focus"));
  });
  // Observe several real 900ms poll ticks with slower 1400ms responses.
  await page.waitForTimeout(3200);
  expect(maxActivePolls).toBe(1);
  for (const path of learningResources)
    expect(trace.count("poll-and-focus", path)).toBe(0);
  trace.phase("lost-response-readback");
  await page.request.post(`${api}/__acceptance__/release`);
  await expect(page.getByRole("button", { name: /继续角色互动/ })).toBeEnabled({
    timeout: 15000,
  });
  await page.waitForTimeout(1000);
  const detail = await (
    await page.request.get(`${api}/tavern/rooms/${h.roomId}`)
  ).json();
  const runs = (
    await (await page.request.get(`${api}/tavern/rooms/${h.roomId}/runs`)).json()
  ).items;
  expect(runs).toHaveLength(2);
  expect(runs.every((run: { status: string }) => run.status === "completed")).toBe(
    true,
  );
  expect(
    detail.messages.filter(
      (item: { author_kind: string }) => item.author_kind === "user",
    ),
  ).toHaveLength(2);
  const providerCalls = (
    await (await page.request.get(`${api}/__acceptance__/calls`)).json()
  ).calls.filter(
    (call: { message: string }) => call.message === "dedupe-recovery-round",
  );
  expect(providerCalls).toHaveLength(2);
  expect(
    trace.records.filter(
      (record) => record.method === "POST" && record.path.endsWith("/turns"),
    ),
  ).toHaveLength(1);
  // One new GET after ambiguous outcome must not reuse an older pending poll.
  expect(trace.count("lost-response-readback", `/tavern/rooms/${h.roomId}`)).toBe(1);
  if (!before)
    expect(
      trace.count("lost-response-readback", `/tavern/rooms/${h.roomId}/runs`),
    ).toBe(1);
  await save(info, "recovery-request-timeline.json", {
    freshRunReadCount: trace.count(
      "lost-response-readback",
      `/tavern/rooms/${h.roomId}/runs`,
    ),
    before,
    fixture: { roomId: h.roomId, historicalRuns: 1 },
    maxActivePolls,
    providerCalls,
    runs,
    records: trace.records,
  });
  await page.unrouteAll({ behavior: "wait" });
});
