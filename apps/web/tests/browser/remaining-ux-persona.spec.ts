import {
  test,
  expect,
  deferred,
  persona,
  personaCandidate,
  card,
  noHorizontalOverflow,
} from "./remaining-ux-fixtures";

test("PERSONA: per-card rejection/acceptance and field/reference diff match the saved draft", async ({
  page,
  wire,
}) => {
  const writes: Record<string, unknown>[] = [];
  wire.on("POST", "/persona-cards/generate", () => ({ json: personaCandidate() }));
  wire.on("PATCH", "/personas/ux-persona", (request) => {
    const body = request.postDataJSON();
    writes.push(body);
    const saved = persona({ ...body, revision: 2 });
    wire.on("GET", "/personas", () => ({ json: { items: [saved] } }));
    return { json: saved };
  });
  await page.goto("/persona-spectrum");
  await page.getByRole("textbox", { name: "卡片生成关键词" }).fill("逐卡审查");
  await page
    .getByRole("button", { name: "根据关键词生成人格卡片", exact: true })
    .click();
  const diff = page.locator(".proposal-diff");
  for (const [before, after] of [
    ["原摘要", "候选摘要"],
    ["原关系", "候选关系"],
    ["原称呼", "候选称呼"],
  ]) {
    await expect(diff.locator("del").filter({ hasText: before })).toHaveText(before);
    await expect(diff.locator("ins").filter({ hasText: after })).toHaveText(after);
  }
  const item = (index: number) =>
    page.getByRole("listitem").filter({
      has: page.getByRole("checkbox", { name: `选择候选卡 ${index}`, exact: true }),
    });
  await item(2).getByRole("button", { name: "拒绝这张卡片", exact: true }).click();
  await expect(
    page.getByRole("checkbox", { name: "选择候选卡 2", exact: true }),
  ).toHaveCount(0);
  await page.getByRole("checkbox", { name: "选择候选卡 3", exact: true }).uncheck();
  await item(1).getByRole("button", { name: "仅合并这张卡片", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "摘要", exact: true })).toHaveValue(
    "原摘要",
  );
  await page.getByText("查看完整参考提示 diff", { exact: true }).click();
  await expect(diff).toContainText("新增：无");
  await expect(diff).toContainText("保留：保留来源");
  await page.getByRole("button", { name: "应用到当前编辑区", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "摘要", exact: true })).toHaveValue(
    "候选摘要",
  );
  await expect(page.getByRole("textbox", { name: "关系", exact: true })).toHaveValue(
    "候选关系",
  );
  await expect(
    page.getByRole("textbox", { name: "学习者称呼", exact: true }),
  ).toHaveValue("候选称呼");
  expect(
    wire.requests
      .filter((r) => ["POST", "PATCH"].includes(r.method))
      .map((r) => r.path),
  ).toEqual(["/persona-cards/generate"]);
  await page.getByRole("button", { name: "更新人格", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "已更新人格" }),
  ).toBeVisible();
  expect(writes).toHaveLength(1);
  expect(writes[0]).toMatchObject({
    name: "UX Mentor",
    summary: "候选摘要",
    relationship: "候选关系",
    learner_address: "候选称呼",
    expected_revision: 1,
    reference_hints: ["保留来源", "移除来源"],
  });
  expect(writes[0].slots).toEqual([
    {
      kind: "custom",
      label: "原插槽",
      content: "原内容",
      weight: 1,
      locked: false,
      sort_order: 0,
    },
    {
      kind: "custom",
      label: "候选插槽 1",
      content: "候选内容 1",
      weight: 50,
      locked: false,
      sort_order: 10,
    },
  ]);
  await noHorizontalOverflow(page);
});

test("PERSONA: bulk clear is separate from normal editing; cancel retains the draft and confirm clears only slots", async ({
  page,
  wire,
}) => {
  const secondSlot = {
    kind: "teaching_method",
    label: "保留插槽",
    content: "保留内容",
    weight: 20,
    locked: false,
    sort_order: 10,
  };
  let saved = persona({ slots: [...persona().slots, secondSlot] });
  const writes: Record<string, unknown>[] = [];
  wire.on("GET", "/personas", () => ({ json: { items: [saved] } }));
  wire.on("PATCH", "/personas/ux-persona", (request) => {
    const body = request.postDataJSON();
    writes.push(body);
    saved = persona({ ...body, revision: writes.length + 1 });
    return { json: saved };
  });
  await page.goto("/persona-spectrum");
  const name = page.getByRole("textbox", { name: "名称", exact: true });
  const summary = page.getByRole("textbox", { name: "摘要", exact: true });
  await name.fill("清空前未保存名称");
  await summary.fill("清空前未保存摘要");
  await expect(page.getByRole("button", { name: "添加", exact: true })).toBeVisible();
  const clear = page.getByRole("button", { name: "清空全部插槽", exact: true });
  await expect(clear).not.toBeVisible();
  await page.getByText("批量操作", { exact: true }).click();
  const prompts: string[] = [];
  page.once("dialog", async (dialog) => {
    prompts.push(dialog.message());
    await dialog.dismiss();
  });
  await clear.click();
  expect(prompts).toEqual(["将清空当前 2 个插槽，是否继续？"]);
  await expect(name).toHaveValue("清空前未保存名称");
  await expect(summary).toHaveValue("清空前未保存摘要");
  await expect(page.getByRole("button", { name: /^删除插槽 / })).toHaveCount(2);
  expect(writes).toHaveLength(0);
  // A single-slot edit is local and distinct from clearing all or deleting a library record.
  await page.getByRole("button", { name: "删除插槽 原插槽", exact: true }).click();
  await expect(page.getByRole("button", { name: /^删除插槽 / })).toHaveCount(1);
  await page.getByRole("button", { name: "更新人格", exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({
    name: "清空前未保存名称",
    summary: "清空前未保存摘要",
    relationship: "原关系",
    learner_address: "原称呼",
    system_prompt: "原约束",
    reference_hints: ["保留来源", "移除来源"],
    slots: [{ ...secondSlot, sort_order: 0 }],
  });
  await expect(
    page.getByRole("button", { name: "更新人格", exact: true }),
  ).toBeEnabled();
  page.once("dialog", async (dialog) => {
    prompts.push(dialog.message());
    await dialog.accept();
  });
  await clear.click();
  expect(prompts[1]).toBe("将清空当前 1 个插槽，是否继续？");
  await expect(page.getByRole("button", { name: /^删除插槽 / })).toHaveCount(0);
  await expect(clear).toBeDisabled();
  await page.getByRole("button", { name: "更新人格", exact: true }).click();
  await expect.poll(() => writes.length).toBe(2);
  expect(writes[1]).toMatchObject({ ...writes[0], expected_revision: 2, slots: [] });
  expect(wire.requests.filter((r) => r.method === "DELETE")).toEqual([]);
});

test("PERSONA: library deletion is disclosed separately; cancel keeps unsaved edits and confirm deletes only its target", async ({
  page,
  wire,
}) => {
  const active = persona();
  const other = persona({ id: "other-persona", name: "另一个人格", revision: 7 });
  const builtin = persona({
    id: "builtin-persona",
    name: "只读内置",
    source: "builtin",
  });
  let items = [active, other, builtin];
  const deleted: string[] = [];
  wire.on("GET", "/personas", () => ({ json: { items } }));
  wire.on("DELETE", "/personas/other-persona", (request) => {
    deleted.push(request.url());
    items = items.filter((p) => p.id !== other.id);
    return { json: { deleted_persona_id: other.id } };
  });
  await page.goto("/persona-spectrum");
  const name = page.getByRole("textbox", { name: "名称", exact: true });
  await name.fill("不随库删除丢失的草稿");
  await page.getByRole("button", { name: "人格库", exact: true }).click();
  const target = page
    .getByRole("article")
    .filter({ has: page.getByText("另一个人格", { exact: true }) });
  const own = page
    .getByRole("article")
    .filter({ has: page.getByText("UX Mentor", { exact: true }) });
  const readonly = page
    .getByRole("article")
    .filter({ has: page.getByText("只读内置", { exact: true }) });
  await expect(target.getByRole("button", { name: "载入", exact: true })).toBeVisible();
  await expect(
    target.getByRole("button", { name: "删除", exact: true }),
  ).not.toBeVisible();
  await expect(readonly.getByText("删除操作", { exact: true })).toHaveCount(0);
  await own.getByText("删除操作", { exact: true }).click();
  const prompts: string[] = [];
  page.once("dialog", async (dialog) => {
    prompts.push(dialog.message());
    await dialog.dismiss();
  });
  await own.getByRole("button", { name: "删除", exact: true }).click();
  expect(prompts[0]).toContain("未保存修改也会丢失");
  await expect(name).toHaveValue("不随库删除丢失的草稿");
  await expect(page.getByRole("combobox", { name: "人格", exact: true })).toHaveValue(
    active.id,
  );
  expect(deleted).toEqual([]);
  await target.getByText("删除操作", { exact: true }).click();
  page.once("dialog", async (dialog) => {
    prompts.push(dialog.message());
    await dialog.dismiss();
  });
  await target.getByRole("button", { name: "删除", exact: true }).click();
  await expect(target).toBeVisible();
  await expect(name).toHaveValue("不随库删除丢失的草稿");
  expect(deleted).toEqual([]);
  page.once("dialog", async (dialog) => {
    prompts.push(dialog.message());
    await dialog.accept();
  });
  await target.getByRole("button", { name: "删除", exact: true }).click();
  await expect(target).toHaveCount(0);
  await expect(own).toBeVisible();
  await expect(readonly).toBeVisible();
  await expect(name).toHaveValue("不随库删除丢失的草稿");
  expect(deleted.map((url) => new URL(url).pathname + new URL(url).search)).toEqual([
    "/personas/other-persona?expected_revision=7",
  ]);
  expect(
    wire.requests.filter(
      (r) => r.method !== "GET" && !r.path.startsWith("/diagnostics/"),
    ),
  ).toEqual([{ method: "DELETE", path: "/personas/other-persona", body: null }]);
});

test("PERSONA: card-library delete disclosure can be closed without mutation; explicit delete preserves the inserted draft slot", async ({
  page,
  wire,
}) => {
  const libraryCard = card(9, { source: "manual", title: "可删除库卡片" });
  let items = [libraryCard];
  const writes: Record<string, unknown>[] = [];
  wire.on("GET", "/persona-cards", () => ({ json: { items } }));
  wire.on("DELETE", "/persona-cards/ux-card-9", () => {
    items = [];
    return { json: { deleted_persona_card_id: libraryCard.id } };
  });
  wire.on("PATCH", "/personas/ux-persona", (request) => {
    const body = request.postDataJSON();
    writes.push(body);
    const saved = persona({ ...body, revision: 2 });
    wire.on("GET", "/personas", () => ({ json: { items: [saved] } }));
    return { json: saved };
  });
  await page.goto("/persona-spectrum");
  const libraryToggle = page.getByRole("button", { name: "卡片库", exact: true });
  if ((await libraryToggle.getAttribute("aria-expanded")) === "false")
    await libraryToggle.click();
  const target = page
    .getByRole("article")
    .filter({ has: page.getByText("可删除库卡片", { exact: true }) });
  await expect(
    target.getByRole("button", { name: "插入当前人格", exact: true }),
  ).toBeVisible();
  await expect(
    target.getByRole("button", { name: "删除", exact: true }),
  ).not.toBeVisible();
  await target.getByRole("button", { name: "插入当前人格", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "删除插槽 候选插槽 9", exact: true }),
  ).toBeVisible();
  await target.getByText("删除操作", { exact: true }).click();
  await expect(target.getByRole("button", { name: "删除", exact: true })).toBeVisible();
  await target.getByText("删除操作", { exact: true }).click();
  await expect(
    target.getByRole("button", { name: "删除", exact: true }),
  ).not.toBeVisible();
  await expect(target).toBeVisible();
  expect(wire.requests.filter((r) => r.method === "DELETE")).toEqual([]);
  await target.getByText("删除操作", { exact: true }).click();
  await target.getByRole("button", { name: "删除", exact: true }).click();
  await expect(target).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "删除插槽 候选插槽 9", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "更新人格", exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0].slots).toEqual([
    ...persona().slots,
    {
      kind: "custom",
      label: "候选插槽 9",
      content: "候选内容 9",
      weight: 50,
      locked: false,
      sort_order: 10,
    },
  ]);
  expect(wire.requests.filter((r) => r.method === "DELETE").map((r) => r.path)).toEqual(
    ["/persona-cards/ux-card-9"],
  );
});

test("PERSONA: populated source filters compose with search and never discard the active draft", async ({
  page,
  wire,
}) => {
  wire.on("GET", "/personas", () => ({
    json: {
      items: [
        persona(),
        persona({
          id: "builtin-ux",
          name: "内置导师",
          source: "builtin",
          summary: "天文教学",
        }),
        persona({ id: "user-ux", name: "实验导师", summary: "矿物教学" }),
      ],
    },
  }));
  await page.goto("/persona-spectrum");
  const name = page.getByRole("textbox", { name: "名称", exact: true });
  await name.fill("保留当前未保存草稿");
  await page.getByRole("button", { name: "人格库", exact: true }).click();
  const search = page.getByRole("textbox", { name: "搜索人格库", exact: true });
  const source = page.getByRole("combobox", { name: "筛选人格来源" });
  await expect(page.getByRole("status").filter({ hasText: "3 个人格" })).toBeVisible();
  await source.selectOption("builtin");
  await expect(page.getByRole("status").filter({ hasText: "1 个人格" })).toBeVisible();
  await search.fill("矿物");
  await expect(
    page.getByText("没有匹配的人格，请调整搜索或筛选。", { exact: true }),
  ).toBeVisible();
  await source.selectOption("user");
  await expect(page.getByRole("status").filter({ hasText: "1 个人格" })).toBeVisible();
  await expect(page.getByText("实验导师", { exact: true })).toBeVisible();
  await expect(name).toHaveValue("保留当前未保存草稿");
  await expect(page.getByRole("combobox", { name: "人格", exact: true })).toHaveValue(
    "ux-persona",
  );
  await noHorizontalOverflow(page);
  expect(wire.requests.filter((r) => r.method !== "GET")).toEqual([]);
});

test("PERSONA: destructive replacement can be cancelled and shows exact removed reference hints", async ({
  page,
  wire,
}) => {
  wire.on("POST", "/persona-cards/generate", () => ({ json: personaCandidate() }));
  await page.goto("/persona-spectrum");
  await page.getByRole("textbox", { name: "卡片生成关键词" }).fill("替换审查");
  await page
    .getByRole("button", { name: "根据关键词生成人格卡片", exact: true })
    .click();
  await expect(
    page.getByRole("checkbox", { name: "选择候选卡 1", exact: true }),
  ).toBeChecked();
  await page.getByText("替换选项（会清空当前内容）", { exact: true }).click();
  await page
    .getByRole("checkbox", { name: "应用前清空摘要、关系、称呼、参考提示和全部插槽" })
    .check();
  await page.getByText("查看完整参考提示 diff", { exact: true }).click();
  const diff = page.locator(".proposal-diff");
  await expect(diff).toContainText("清空：移除来源");
  await expect(diff).toContainText("新增：新增来源 2、新增来源 3");
  await expect(diff).toContainText("删除现有 1 个，再插入已选卡片");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("button", { name: "应用到当前编辑区", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "摘要", exact: true })).toHaveValue(
    "原摘要",
  );
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "应用到当前编辑区", exact: true }).click();
  await expect(page.getByRole("textbox", { name: "摘要", exact: true })).toHaveValue(
    "候选摘要",
  );
  expect(wire.requests.filter((r) => r.method !== "GET").map((r) => r.path)).toEqual([
    "/persona-cards/generate",
  ]);
});

test("PERSONA: candidate application and invalid save locate the required name without writing", async ({
  page,
  wire,
}) => {
  wire.on("POST", "/persona-cards/generate", () => ({ json: personaCandidate() }));
  await page.goto("/persona-spectrum");
  await page.getByRole("button", { name: "新建人格草稿", exact: true }).click();
  await page.getByRole("textbox", { name: "卡片生成关键词" }).fill("名称定位");
  await page
    .getByRole("button", { name: "根据关键词生成人格卡片", exact: true })
    .click();
  await expect(
    page.getByRole("note").filter({ hasText: "名称尚未填写" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "应用到当前编辑区", exact: true }).click();
  const name = page.getByRole("textbox", { name: "名称", exact: true });
  await expect(name).toHaveValue("");
  await expect(name).toBeFocused();
  await expect(name).toBeInViewport();
  await page.getByRole("button", { name: "创建人格", exact: true }).click();
  await expect(page.locator("main").getByRole("alert")).toContainText(
    "请先填写人格名称",
  );
  await expect(page.locator("main").getByRole("alert")).toBeFocused();
  expect(wire.requests.filter((r) => r.method !== "GET").map((r) => r.path)).toEqual([
    "/persona-cards/generate",
  ]);
  await noHorizontalOverflow(page);
});

test("PERSONA: slow create/update retain newer edits and send the committed revision exactly once", async ({
  page,
  wire,
}) => {
  const gates = [deferred(), deferred()];
  const writes: Record<string, unknown>[] = [];
  let saved = persona();
  wire.on("GET", "/personas", () => ({ json: { items: [saved] } }));
  for (const [method, path] of [
    ["POST", "/personas"],
    ["PATCH", "/personas/created-ux"],
  ])
    wire.on(method, path, async (request) => {
      const body = request.postDataJSON();
      const index = writes.length;
      writes.push(body);
      await gates[index].promise;
      saved = persona({ ...body, id: "created-ux", revision: index + 1 });
      return { json: saved };
    });
  await page.goto("/persona-spectrum");
  await page.getByRole("button", { name: "新建人格草稿", exact: true }).click();
  const name = page.getByRole("textbox", { name: "名称", exact: true });
  await name.fill("第一次提交");
  await page.getByRole("button", { name: "创建人格", exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  await expect(
    page.getByRole("button", { name: "保存中", exact: true }).last(),
  ).toBeDisabled();
  await name.fill("在途新输入");
  gates[0].release();
  await expect(
    page.getByRole("button", { name: "更新人格", exact: true }),
  ).toBeEnabled();
  await expect(name).toHaveValue("在途新输入");
  await expect(name).toBeFocused();
  await page.getByRole("button", { name: "更新人格", exact: true }).click();
  await expect.poll(() => writes.length).toBe(2);
  await name.fill("第二次在途输入");
  gates[1].release();
  await expect(
    page.getByRole("button", { name: "更新人格", exact: true }),
  ).toBeEnabled();
  await expect(name).toHaveValue("第二次在途输入");
  await expect(name).toBeFocused();
  expect(
    writes.map((body) => ({ name: body.name, revision: body.expected_revision })),
  ).toEqual([
    { name: "第一次提交", revision: undefined },
    { name: "在途新输入", revision: 1 },
  ]);
  expect(wire.requests.filter((r) => r.method !== "GET")).toHaveLength(2);
});

test("PERSONA: long save error preserves draft and a later keyword focus without replay", async ({
  page,
  wire,
}) => {
  const gate = deferred();
  const detail = `PERSONA-BEGIN-${"network_failure_".repeat(160)}-PERSONA-END`;
  wire.on("PATCH", "/personas/ux-persona", async () => {
    await gate.promise;
    return { status: 503, json: { detail } };
  });
  await page.goto("/persona-spectrum");
  await page.getByRole("textbox", { name: "名称", exact: true }).fill("保留失败草稿");
  await page.getByRole("button", { name: "更新人格", exact: true }).click();
  await expect
    .poll(() => wire.requests.filter((r) => r.method === "PATCH").length)
    .toBe(1);
  const keyword = page.getByRole("textbox", { name: "卡片生成关键词" });
  await keyword.fill("继续编辑关键词");
  const scroll = await page.evaluate(() => scrollY);
  gate.release();
  await expect(page.locator("main").getByRole("alert")).toContainText("PERSONA-END");
  await expect(keyword).toBeFocused();
  await expect(page.getByRole("textbox", { name: "名称", exact: true })).toHaveValue(
    "保留失败草稿",
  );
  expect(await page.evaluate(() => scrollY)).toBe(scroll);
  expect(wire.requests.filter((r) => r.method === "PATCH")).toHaveLength(1);
  await noHorizontalOverflow(page);
});
