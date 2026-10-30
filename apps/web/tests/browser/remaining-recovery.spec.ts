import type { Locator, Page, Request, TestInfo } from "@playwright/test";
import responses from "../../../../packages/shared/fixtures/settings/responses-v1.json" with { type: "json" };
import {
  test,
  expect,
  deferred,
  persona,
  timestamp,
  apiOrigin,
} from "./remaining-ux-fixtures";

type Reply = { status?: number; json: unknown };
type Register = (
  method: string,
  path: string,
  handler: (request: Request) => Reply | Promise<Reply>,
) => void;

function tavern(on: Register, emptyRoom = false, emptyPersonas = false) {
  const actor = persona({
    id: "recovery-actor",
    name: "恢复角色",
    relationship: "同伴",
  });
  const unrelated = persona({ id: "unrelated-actor", name: "无关人格", revision: 3 });
  let people = emptyPersonas ? [] : [actor, unrelated];
  let exists = !emptyRoom;
  const room = {
    id: "recovery-room",
    creation_key: "",
    creation_input_digest: "",
    title: "恢复验收房间",
    scene_profile: null,
    harness_policy: {
      version: "tavern-harness-v1",
      max_character_messages: 4,
      max_reply_characters: 1200,
      context_message_limit: 18,
      prevent_speaker_impersonation: true,
    },
    status: "active" as "active" | "archived",
    revision: 0,
    last_sequence: 1,
    created_at: timestamp,
    updated_at: timestamp,
  };
  const participants = [
    {
      room_id: room.id,
      persona_id: actor.id,
      display_order: 0,
      display_name: actor.name,
      persona_snapshot: actor,
      prompt_hash: "synthetic-recovery-prompt",
      joined_at: timestamp,
    },
  ];
  let messages = [
    {
      id: "existing-message",
      room_id: room.id,
      sequence: 1,
      run_id: "",
      author_kind: "user",
      persona_id: "",
      persona_name: "",
      content: "归档之前已保存的对话",
      emotion: "",
      action: "",
      speech_style: "",
      addressed_participant_ids: [],
      reply_to_message_id: "",
      client_request_id: "",
      created_at: timestamp,
      harness_trace: null,
    },
  ];
  const writes: {
    method: string;
    path: string;
    body: Record<string, unknown> | null;
  }[] = [];
  const detail = () => ({
    room,
    participants,
    messages,
    message_count: messages.length,
    next_after_sequence: null,
    next_before_sequence: null,
  });
  on("GET", "/personas", () => ({ json: { items: people } }));
  on("GET", "/tavern/rooms", () => ({
    json: {
      contract_version: "tavern-room-list-v1",
      next_cursor: null,
      items: exists
        ? [
            {
              id: room.id,
              title: room.title,
              participant_persona_ids: [actor.id],
              participant_names: [actor.name],
              message_count: messages.length,
              revision: room.revision,
              status: room.status,
              created_at: timestamp,
              updated_at: timestamp,
            },
          ]
        : [],
    },
  }));
  on("GET", `/tavern/rooms/${room.id}`, () => ({ json: detail() }));
  on("GET", `/tavern/rooms/${room.id}/runs`, () => ({ json: { items: [] } }));
  on("GET", `/tavern/rooms/${room.id}/run-recovery`, () => ({ json: { items: [] } }));
  on("POST", "/tavern/rooms", (request) => {
    const body = request.postDataJSON();
    writes.push({ method: "POST", path: "/tavern/rooms", body });
    room.title = body.title;
    room.creation_key = body.idempotency_key;
    messages = [];
    room.last_sequence = 0;
    exists = true;
    return { json: detail() };
  });
  on("PATCH", `/tavern/rooms/${room.id}`, (request) => {
    const body = request.postDataJSON();
    writes.push({ method: "PATCH", path: `/tavern/rooms/${room.id}`, body });
    expect(body.expected_revision).toBe(room.revision);
    expect(["active", "archived"]).toContain(body.status);
    room.status = body.status;
    room.revision++;
    return { json: detail() };
  });
  on("DELETE", `/personas/${actor.id}`, () => {
    writes.push({ method: "DELETE", path: `/personas/${actor.id}`, body: null });
    return {
      status: 409,
      json: {
        detail: "persona_in_use:plans=0:sessions=0:scene_instances=0:tavern_rooms=1",
      },
    };
  });
  on("DELETE", `/personas/${unrelated.id}`, () => {
    writes.push({ method: "DELETE", path: `/personas/${unrelated.id}`, body: null });
    people = people.filter((p) => p.id !== unrelated.id);
    return { json: { deleted_persona_id: unrelated.id } };
  });
  return { actor, unrelated, room, messages, participants, writes };
}

async function navigate(page: Page, path: string) {
  const nav = page.getByRole("complementary", { name: "Primary navigation" });
  const toggle = nav.getByRole("button", { name: /全部导航/ });
  if (
    (await toggle.isVisible()) &&
    (await toggle.getAttribute("aria-expanded")) === "false"
  )
    await toggle.click();
  await nav.locator(`a[href="${path}"]`).click();
  await expect(page).toHaveURL(new RegExp(`${path}$`));
}

function navigationOrder(page: Page) {
  const nav = page.getByRole("complementary", { name: "Primary navigation" });
  if (page.viewportSize()!.width <= 760)
    return [nav.getByRole("button", { name: /全部导航/ })];
  return [
    "/",
    "/plan",
    "/study",
    "/tavern",
    "/persona-spectrum",
    "/scene-setup",
    "/sensory-tools",
    "/settings",
    "/model-usage",
    "/manual",
  ]
    .map((path) => nav.locator(`a[href="${path}"]`))
    .concat(nav.getByRole("button", { name: "Collapse navigation", exact: true }));
}

async function fullKeyboardOrder(page: Page, controls: Locator[], info: TestInfo) {
  const observations: { index: number; accessible: string; forward: boolean }[] = [];
  await controls[0].focus();
  for (let index = 0; index < controls.length; index++) {
    if (index) await page.keyboard.press("Tab");
    await expect(controls[index]).toBeFocused();
    await expect(controls[index]).toBeInViewport();
    observations.push({
      index,
      accessible: await controls[index].ariaSnapshot(),
      forward: true,
    });
  }
  await page.keyboard.press("Tab");
  expect(await page.evaluate(() => document.activeElement === document.body)).toBe(
    true,
  );
  await page.keyboard.press("Shift+Tab");
  for (let index = controls.length - 1; index >= 0; index--) {
    if (index < controls.length - 1) await page.keyboard.press("Shift+Tab");
    await expect(controls[index]).toBeFocused();
    await expect(controls[index]).toBeInViewport();
    observations.push({
      index,
      accessible: await controls[index].ariaSnapshot(),
      forward: false,
    });
  }
  await info.attach("full-keyboard-order.json", {
    body: Buffer.from(JSON.stringify(observations, null, 2)),
    contentType: "application/json",
  });
}

test("Tavern dual empty state exposes an actionable Persona link and cannot mutate", async ({
  page,
  wire,
}, info) => {
  tavern(wire.on, true, true);
  await page.goto("/tavern");
  const setup = page.getByRole("region", { name: "创建房间", exact: true });
  await expect(setup).toContainText("人格库为空。先前往");
  await expect(
    page.getByText("还没有房间。选择 1–6 位人格即可创建。", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("先创建或打开一个酒馆，然后开始对话。", { exact: true }),
  ).toBeVisible();
  await expect(
    setup.getByRole("button", { name: "创建并进入", exact: true }),
  ).toBeDisabled();
  await expect(page.getByRole("region", { name: "发起互动", exact: true })).toHaveCount(
    0,
  );
  const next = setup.getByRole("link", { name: "人格色谱", exact: true });
  await fullKeyboardOrder(
    page,
    [
      ...navigationOrder(page),
      page.getByRole("button", { name: "新建酒馆", exact: true }),
      setup.getByRole("textbox", { name: "标题", exact: true }),
      next,
      setup.getByRole("combobox", { name: "场景（可选）", exact: true }),
      setup.getByRole("textbox", { name: "开场白（可选）", exact: true }),
    ],
    info,
  );
  await next.focus();
  await next.press("Enter");
  await expect(page).toHaveURL(/\/persona-spectrum$/);
  expect(
    wire.requests.filter(
      (r) => r.method !== "GET" && !r.path.startsWith("/diagnostics/"),
    ),
  ).toEqual([]);
});

test("Tavern without rooms supports the full keyboard setup path and restores the created Room after reload", async ({
  page,
  wire,
}, info) => {
  const h = tavern(wire.on, true);
  await page.goto("/tavern");
  const setup = page.getByRole("region", { name: "创建房间", exact: true });
  const title = setup.getByRole("textbox", { name: "标题", exact: true });
  const choices = setup.getByRole("checkbox");
  await expect(choices).toHaveCount(2);
  await fullKeyboardOrder(
    page,
    [
      ...navigationOrder(page),
      page.getByRole("button", { name: "新建酒馆", exact: true }),
      title,
      choices.nth(0),
      choices.nth(1),
      setup.getByRole("combobox", { name: "场景（可选）", exact: true }),
      setup.getByRole("textbox", { name: "开场白（可选）", exact: true }),
      setup.getByRole("button", { name: "创建并进入", exact: true }),
    ],
    info,
  );
  await title.focus();
  await title.press("ControlOrMeta+A");
  await page.keyboard.insertText("键盘创建的房间");
  await choices.nth(0).focus();
  await choices.nth(0).press("Space");
  await setup.getByRole("button", { name: "创建并进入", exact: true }).focus();
  await page.keyboard.press("Enter");
  await expect(
    page.getByRole("heading", { level: 1, name: "键盘创建的房间", exact: true }),
  ).toBeVisible();
  expect(h.writes).toHaveLength(1);
  expect(h.writes[0].body).toMatchObject({
    title: "键盘创建的房间",
    persona_ids: [h.actor.id],
    scene_profile: null,
    opening_prompt: "",
  });
  expect(h.writes[0].body!.idempotency_key).toEqual(expect.any(String));
  expect(String(h.writes[0].body!.idempotency_key).length).toBeGreaterThan(0);
  await page.reload();
  await expect(
    page.getByRole("heading", { level: 1, name: "键盘创建的房间", exact: true }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("region", { name: "角色与目标", exact: true })
      .getByRole("checkbox")
      .first(),
  ).toBeChecked();
  expect(h.writes).toHaveLength(1);
  expect(wire.requests.filter((r) => r.path.endsWith("/turns"))).toEqual([]);
});

test("Tavern active-room keyboard order spans all panels in both directions without trapping or sending", async ({
  page,
  wire,
}, info) => {
  tavern(wire.on);
  await page.goto("/tavern");
  const composer = page.getByRole("region", { name: "发起互动", exact: true });
  const message = composer.getByRole("textbox", { name: "你的消息", exact: true });
  await message.fill("只校验焦点顺序，不发送");
  const controls = [
    ...navigationOrder(page),
    page.getByRole("button", { name: "刷新", exact: true }),
    page.getByRole("button", { name: "归档", exact: true }),
    page.getByRole("button", { name: "新建酒馆", exact: true }),
    page
      .getByRole("region", { name: "最近酒馆", exact: true })
      .getByRole("button")
      .first(),
    message,
    composer.getByRole("textbox", {
      name: "下一轮引导（可选，不会显示在对话中）",
      exact: true,
    }),
    composer.getByRole("button", { name: "发送并回应", exact: false }),
    composer.getByRole("button", { name: "继续角色互动", exact: true }),
    page.getByRole("region", { name: "角色与目标", exact: true }).getByRole("checkbox"),
    page.locator("details.reliability-details > summary"),
  ];
  await fullKeyboardOrder(page, controls, info);
  await expect(message).toHaveValue("只校验焦点顺序，不发送");
  expect(
    wire.requests.filter(
      (r) => r.method !== "GET" && !r.path.startsWith("/diagnostics/"),
    ),
  ).toEqual([]);
});

test("Settings route departure flushes an unsent debounced edit; return and reload read the saved value", async ({
  page,
  wire,
}) => {
  let saved = { ...responses.runtime_settings, show_debug_info: false };
  const writes: Record<string, unknown>[] = [];
  wire.on("GET", "/runtime-settings", () => ({ json: saved }));
  wire.on("PATCH", "/runtime-settings", (request) => {
    const body = request.postDataJSON();
    writes.push(body);
    saved = { ...saved, ...body };
    return { json: saved };
  });
  await page.goto("/settings");
  const toggle = page.getByRole("checkbox", { name: "显示调试悬浮窗", exact: true });
  await expect(toggle).not.toBeChecked();
  await page.clock.install();
  await page.clock.pauseAt(await page.evaluate(() => Date.now() + 100));
  await toggle.check();
  expect(writes).toHaveLength(0);
  await navigate(page, "/manual");
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].show_debug_info).toBe(true);
  await navigate(page, "/settings");
  await expect(toggle).toBeChecked();
  await page.reload();
  await expect(toggle).toBeChecked();
  expect(writes).toHaveLength(1);
});

for (const earlierFails of [false, true]) {
  test(`Settings in-flight route departure drains latest edit after earlier ${earlierFails ? "failure" : "success"} without replay`, async ({
    page,
    wire,
  }, info) => {
    let saved = { ...responses.runtime_settings, show_debug_info: false };
    const gates = [deferred(), deferred()];
    const writes: Record<string, unknown>[] = [];
    wire.on("GET", "/runtime-settings", () => ({ json: saved }));
    wire.on("PATCH", "/runtime-settings", async (request) => {
      const body = request.postDataJSON();
      const index = writes.length;
      writes.push(body);
      await gates[index].promise;
      if (index === 0 && earlierFails)
        return { status: 503, json: { detail: "较早保存失败" } };
      saved = { ...saved, ...body };
      return { json: saved };
    });
    await page.goto("/settings");
    const toggle = page.getByRole("checkbox", { name: "显示调试悬浮窗", exact: true });
    await toggle.check();
    await expect.poll(() => writes.length).toBe(1);
    await expect(page.getByText("自动保存中", { exact: true })).toBeVisible();
    await toggle.uncheck();
    // Restoring false alone is already satisfied if the earlier write fails.
    // A second field supplies a real outstanding difference from the baseline.
    // This changes synthetic configuration only; no provider is contacted.
    const protocol = page.getByRole("combobox", { name: "模型接口协议", exact: true });
    await protocol.selectOption("litellm");
    await navigate(page, "/manual");
    expect(writes).toHaveLength(1);
    gates[0].release();
    await expect.poll(() => writes.length).toBe(2);
    gates[1].release();
    await expect.poll(() => saved.show_debug_info).toBe(false);
    await expect.poll(() => saved.plan_provider).toBe("litellm");
    await navigate(page, "/settings");
    await expect(toggle).not.toBeChecked();
    await expect(protocol).toHaveValue("litellm");
    await page.reload();
    await expect(toggle).not.toBeChecked();
    await expect(protocol).toHaveValue("litellm");
    expect(
      writes.map((body) => ({
        debug: body.show_debug_info,
        protocol: body.plan_provider,
      })),
    ).toEqual([
      { debug: true, protocol: "mock" },
      { debug: false, protocol: "litellm" },
    ]);
    await page.waitForTimeout(1100); // Beyond the real 900ms debounce, proving no replay.
    expect(writes).toHaveLength(2);
    expect(
      wire.requests.filter(
        (r) => r.path.includes("/check-") || r.path.endsWith("/turns"),
      ),
    ).toEqual([]);
    await info.attach("departed-save-queue.json", {
      body: Buffer.from(JSON.stringify({ earlierFails, writes }, null, 2)),
      contentType: "application/json",
    });
  });
}

test("Settings accepted save with lost response reloads authoritative state without another PATCH", async ({
  page,
  wire,
}, info) => {
  let saved = { ...responses.runtime_settings, show_debug_info: false };
  const writes: Record<string, unknown>[] = [];
  wire.on("GET", "/runtime-settings", () => ({ json: saved }));
  await page.route(`${apiOrigin}/runtime-settings`, async (route) => {
    if (route.request().method() !== "PATCH") return route.fallback();
    const body = route.request().postDataJSON();
    writes.push(body);
    saved = { ...saved, ...body }; // Synthetic server commit precedes response loss.
    await route.abort("connectionreset");
  });
  await page.goto("/settings");
  const toggle = page.getByRole("checkbox", { name: "显示调试悬浮窗", exact: true });
  await toggle.check();
  await expect(
    page.getByRole("button", { name: "重试保存", exact: true }),
  ).toBeVisible();
  expect(writes).toHaveLength(1);
  await page.reload();
  await expect(toggle).toBeChecked();
  await expect(page.getByRole("button", { name: "重试保存", exact: true })).toHaveCount(
    0,
  );
  await page.waitForTimeout(1100);
  expect(writes).toHaveLength(1);
  await info.attach("lost-settings-response.json", {
    body: Buffer.from(
      JSON.stringify(
        { writes, saved: saved.show_debug_info, replayed: false },
        null,
        2,
      ),
    ),
    contentType: "application/json",
  });
});

test("Tavern archive and Persona deletion combination preserves the room snapshot, transcript and unsent draft", async ({
  page,
  wire,
}, info) => {
  const h = tavern(wire.on);
  await page.goto("/tavern");
  const message = page.getByRole("textbox", { name: "你的消息", exact: true });
  await message.fill("归档往返保留的未发送消息");
  await page.getByRole("button", { name: "归档", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "恢复使用", exact: true }),
  ).toBeEnabled();
  await expect(message).toBeDisabled();
  await expect(message).toHaveValue("归档往返保留的未发送消息");
  await navigate(page, "/persona-spectrum");
  await page.getByRole("button", { name: "人格库", exact: true }).click();
  const referenced = page
    .getByRole("article")
    .filter({ has: page.getByText(h.actor.name, { exact: true }) });
  await referenced.getByText("删除操作", { exact: true }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await referenced.getByRole("button", { name: "删除", exact: true }).click();
  await expect(
    page
      .getByText("该人格仍被酒馆房间 1 条引用，暂时不能删除。", { exact: true })
      .first(),
  ).toBeVisible();
  await expect(referenced).toBeVisible();
  const other = page
    .getByRole("article")
    .filter({ has: page.getByText(h.unrelated.name, { exact: true }) });
  await other.getByText("删除操作", { exact: true }).click();
  page.once("dialog", (dialog) => dialog.accept());
  await other.getByRole("button", { name: "删除", exact: true }).click();
  await expect(other).toHaveCount(0);
  await navigate(page, "/tavern");
  await expect(
    page.getByRole("button", { name: "恢复使用", exact: true }),
  ).toBeEnabled();
  await expect(message).toBeDisabled();
  await expect(message).toHaveValue("归档往返保留的未发送消息");
  await expect(page.getByText("归档之前已保存的对话", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "恢复使用", exact: true }).click();
  await expect(page.getByRole("button", { name: "归档", exact: true })).toBeEnabled();
  await expect(message).toBeEnabled();
  await expect(message).toHaveValue("归档往返保留的未发送消息");
  await page.reload();
  await expect(message).toHaveValue("归档往返保留的未发送消息");
  await expect(page.getByText("归档之前已保存的对话", { exact: true })).toBeVisible();
  expect(h.room.revision).toBe(2);
  expect(h.participants[0].persona_snapshot).toEqual(h.actor);
  expect(h.writes).toEqual([
    {
      method: "PATCH",
      path: "/tavern/rooms/recovery-room",
      body: { expected_revision: 0, status: "archived" },
    },
    { method: "DELETE", path: "/personas/recovery-actor", body: null },
    { method: "DELETE", path: "/personas/unrelated-actor", body: null },
    {
      method: "PATCH",
      path: "/tavern/rooms/recovery-room",
      body: { expected_revision: 1, status: "active" },
    },
  ]);
  expect(wire.requests.filter((r) => r.path.endsWith("/turns"))).toEqual([]);
  await info.attach("archive-delete-restore.json", {
    body: Buffer.from(
      JSON.stringify(
        { writes: h.writes, participant: h.participants[0], messages: h.messages },
        null,
        2,
      ),
    ),
    contentType: "application/json",
  });
});
