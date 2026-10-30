import type { Page } from "@playwright/test";
import {
  test,
  expect,
  deferred,
  sceneLayer,
  sceneObject,
  sceneCandidate,
  sceneRecord,
  noHorizontalOverflow,
  type SceneSave,
} from "./remaining-ux-fixtures";

async function importScene(page: Page, layers = [sceneLayer("root", "实验室")]) {
  const body: SceneSave = {
    scene_name: "原场景",
    scene_summary: "原场景摘要",
    scene_layers: layers,
    selected_layer_id: layers[0].id,
    collapsed_layer_ids: [],
  };
  await page.getByRole("button", { name: "导入 JSON", exact: true }).click();
  await page.getByLabel("导入场景 JSON 文件").setInputFiles({
    name: "synthetic-scene.json",
    mimeType: "application/json",
    buffer: Buffer.from(JSON.stringify({ version: 1, ...body })),
  });
  await expect(
    page.getByRole("textbox", { name: "场景名称", exact: true }),
  ).toHaveValue("原场景");
  return body;
}

test("SCENE: full field/structure diff exposes duplicate references/names and literal parent-rule conflict", async ({
  page,
  wire,
}) => {
  const current = sceneLayer("root", "实验室");
  current.objects = [sceneObject("clock", "时钟"), sceneObject("old", "旧书")];
  const proposed = sceneLayer("new-root", "实验室");
  proposed.summary = "新层摘要";
  proposed.atmosphere = "喧闹";
  proposed.entrance = "侧门";
  proposed.objects = [
    {
      ...sceneObject("new-clock", "时钟"),
      reuse_id: "reuse-clock",
      description: "新时钟说明",
      interaction: "拨动指针",
    },
  ];
  const child = sceneLayer("child", "观察室");
  child.reuse_id = proposed.reuse_id;
  child.rules = "访客允许离开";
  child.objects = [sceneObject("mirror-1", "镜子"), sceneObject("mirror-2", "镜子")];
  proposed.children = [child];
  wire.on("POST", "/scene-setup/generate", () => ({
    json: sceneCandidate([proposed]),
  }));
  await page.goto("/scene-setup");
  await importScene(page, [current, sceneLayer("removed", "待移除房间")]);
  await page.getByRole("textbox", { name: "场景生成关键词" }).fill("结构和规则审查");
  await page.getByRole("button", { name: "根据关键词生成场景树", exact: true }).click();
  const diff = page.locator(".proposal-diff");
  await expect(diff).toContainText("层级：2 → 2；物体：2 → 3");
  await expect(diff).toContainText("新增 1 层，移除 1 层");
  const conflict = diff.getByRole("alert");
  await expect(conflict).toContainText("发现 3 个结构约束冲突候选");
  await expect(conflict).toContainText("复用引用 reuse-new-root");
  await expect(conflict).toContainText("重复物体名称");
  await expect(conflict).toContainText("与父级 1. 实验室 的禁止约束冲突");
  await diff.getByText("查看完整字段与结构变化", { exact: true }).click();
  for (const [before, after] of [
    ["实验室摘要", "新层摘要"],
    ["安静", "喧闹"],
    ["正门", "侧门"],
    ["时钟说明", "新时钟说明"],
    ["观察", "拨动指针"],
  ]) {
    await expect(diff.locator("del").filter({ hasText: before }).first()).toHaveText(
      before,
    );
    await expect(diff.locator("ins").filter({ hasText: after }).first()).toHaveText(
      after,
    );
  }
  await expect(diff.getByText("移除物体：旧书", { exact: true })).toBeVisible();
  await expect(diff.getByText("移除：2. 待移除房间", { exact: true })).toBeVisible();
  await expect(diff).toContainText("规则语义、继承关系及交互可行性仍需人工核对");
  await expect(
    page.getByRole("textbox", { name: "场景名称", exact: true }),
  ).toHaveValue("原场景");
  await noHorizontalOverflow(page);
  await page.getByRole("button", { name: "应用到编辑区", exact: true }).click();
  await expect(
    page.getByRole("textbox", { name: "场景名称", exact: true }),
  ).toHaveValue("候选场景");
  await expect(
    page.getByRole("textbox", { name: "层级总述", exact: true }),
  ).toHaveValue("新层摘要");
  expect(wire.requests.filter((r) => r.method !== "GET").map((r) => r.path)).toEqual([
    "/scene-setup/generate",
  ]);
});

for (const movedFocus of [false, true]) {
  test(`SCENE: current save failure ${movedFocus ? "preserves later input focus/scroll" : "focuses and locates the error"} without replay`, async ({
    page,
    wire,
  }, info) => {
    const gate = deferred();
    const writes: SceneSave[] = [];
    wire.on("POST", "/scene-library", async (request) => {
      writes.push(request.postDataJSON());
      await gate.promise;
      return { status: 503, json: { detail: "当前场景保存失败" } };
    });
    await page.goto("/scene-setup");
    const original = await importScene(page);
    const save = page.getByRole("button", { name: "保存到场景库", exact: true });
    await save.focus();
    await save.press("Enter");
    await expect.poll(() => writes.length).toBe(1);
    const later = page.getByRole("textbox", { name: "场景生成关键词", exact: true });
    if (movedFocus) {
      await later.scrollIntoViewIfNeeded();
      await later.fill("保存期间继续输入");
      await expect(later).toBeInViewport();
    }
    const readInputScroll = () =>
      later.evaluate((element) => {
        const containers: { tag: string; top: number; left: number }[] = [];
        for (
          let parent = element.parentElement;
          parent;
          parent = parent.parentElement
        ) {
          if (
            parent.scrollHeight > parent.clientHeight + 1 ||
            parent.scrollWidth > parent.clientWidth + 1
          ) {
            containers.push({
              tag: parent.tagName,
              top: parent.scrollTop,
              left: parent.scrollLeft,
            });
          }
        }
        return {
          containers,
          inputTop: element.getBoundingClientRect().top,
          headerHeight:
            document
              .querySelector("main h1")
              ?.parentElement?.parentElement?.getBoundingClientRect().height ?? 0,
        };
      });
    const inputBefore = await readInputScroll();
    const before = await page.evaluate(() => ({
      scroll: scrollY,
      focus: document.activeElement?.getAttribute("aria-label"),
    }));
    gate.release();
    const alert = page.locator("main").getByRole("alert");
    await expect(alert).toHaveText("保存到场景库失败，请稍后重试。");
    const after = await page.evaluate(() => ({
      scroll: scrollY,
      focus:
        document.activeElement?.getAttribute("role") ??
        document.activeElement?.getAttribute("aria-label"),
    }));
    const inputAfter = await readInputScroll();
    await info.attach("current-save-error-focus-scroll.json", {
      body: Buffer.from(
        JSON.stringify(
          {
            movedFocus,
            before,
            after,
            inputBefore,
            inputAfter,
            alert: await alert.boundingBox(),
          },
          null,
          2,
        ),
      ),
      contentType: "application/json",
    });
    if (movedFocus) {
      await expect(later).toBeFocused();
      await expect(later).toBeInViewport();
      await expect(later).toHaveValue("保存期间继续输入");
      expect(after.scroll).toBe(before.scroll);
      expect(inputAfter.containers).toEqual(inputBefore.containers);
      expect(inputAfter.headerHeight).toBe(inputBefore.headerHeight);
      expect(Math.abs(inputAfter.inputTop - inputBefore.inputTop)).toBeLessThanOrEqual(
        1,
      );
    } else {
      await expect(alert).toBeFocused();
      await expect(alert).toBeInViewport();
    }
    await expect(
      page.getByRole("textbox", { name: "场景名称", exact: true }),
    ).toHaveValue(original.scene_name);
    expect(writes[0]).toMatchObject(original);
    expect(
      wire.requests.filter((r) => r.method === "POST" && r.path === "/scene-library"),
    ).toHaveLength(1);
    await noHorizontalOverflow(page);
  });
}

test("SCENE: a long current error stays in the reserved feedback region and remains keyboard-readable", async ({
  page,
  wire,
}) => {
  const gate = deferred();
  const detail = `SCENE-LONG-BEGIN-${"模型服务错误详情/".repeat(180)}-SCENE-LONG-END`;
  wire.on("POST", "/scene-setup/generate", async () => {
    await gate.promise;
    return { status: 503, json: { detail } };
  });
  await page.goto("/scene-setup");
  await importScene(page);
  const feedback = page.getByRole("region", { name: "场景操作反馈", exact: true });
  const name = page.getByRole("textbox", { name: "场景名称", exact: true });
  await page
    .getByRole("textbox", { name: "场景生成关键词", exact: true })
    .fill("长错误反馈");
  await page.getByRole("button", { name: "根据关键词生成场景树", exact: true }).click();
  await expect
    .poll(() => wire.requests.filter((r) => r.path === "/scene-setup/generate").length)
    .toBe(1);
  await name.scrollIntoViewIfNeeded();
  await name.focus();
  const before = await feedback.boundingBox();
  const nameBefore = await name.boundingBox();
  gate.release();
  const alert = feedback.getByRole("alert");
  await expect(alert).toContainText("SCENE-LONG-BEGIN");
  await expect(alert).toContainText("SCENE-LONG-END");
  await expect(name).toBeFocused();
  await expect(name).toBeInViewport();
  expect((await feedback.boundingBox())!.height).toBe(before!.height);
  expect(before!.height).toBeLessThanOrEqual(104);
  expect(Math.abs((await name.boundingBox())!.y - nameBefore!.y)).toBeLessThanOrEqual(
    1,
  );
  const dimensions = await feedback.evaluate((el) => ({
    height: el.clientHeight,
    content: el.scrollHeight,
    width: el.clientWidth,
    contentWidth: el.scrollWidth,
  }));
  expect(dimensions.content).toBeGreaterThan(dimensions.height);
  expect(dimensions.contentWidth).toBeLessThanOrEqual(dimensions.width);
  await feedback.focus();
  await feedback.press("End");
  await expect.poll(() => feedback.evaluate((el) => el.scrollTop)).toBeGreaterThan(0);
  expect(
    wire.requests
      .filter((r) => r.method !== "GET" && !r.path.startsWith("/diagnostics/"))
      .map((r) => r.path),
  ).toEqual(["/scene-setup/generate"]);
});

test("SCENE: subtree delete cancel keeps every field; confirm removes only that subtree and restores safe focus", async ({
  page,
  wire,
}) => {
  const doomed = sceneLayer("doomed", "待删层");
  doomed.objects = [sceneObject("root-object", "待删根物体")];
  const child = sceneLayer("doomed-child", "待删子层");
  child.objects = [sceneObject("child-object", "待删子物体")];
  doomed.children = [child];
  const survivor = sceneLayer("survivor", "保留层");
  survivor.objects = [sceneObject("kept-object", "保留物体")];
  const writes: SceneSave[] = [];
  for (const [method, path] of [
    ["POST", "/scene-library"],
    ["PUT", "/scene-library/delete-range"],
  ])
    wire.on(method, path, (request) => {
      const body = request.postDataJSON();
      writes.push(body);
      return { json: sceneRecord(body, "delete-range", writes.length) };
    });
  await page.goto("/scene-setup");
  const original = await importScene(page, [doomed, survivor]);
  await page
    .getByRole("textbox", { name: "场景摘要", exact: true })
    .fill("取消后保留的未保存摘要");
  const trigger = page
    .getByRole("article")
    .filter({ has: page.getByRole("heading", { name: "待删层", exact: true }) })
    .getByRole("button", { name: "删除当前层级", exact: true });
  const dialog = page.getByRole("dialog", { name: "确认删除层级？", exact: true });
  for (const cancelBy of ["Escape", "button"]) {
    await trigger.focus();
    await trigger.press("Enter");
    await expect(dialog).toHaveAccessibleDescription(/待删层.*所有子层级与物体/);
    await expect(
      dialog.getByRole("button", { name: "取消", exact: true }),
    ).toBeFocused();
    expect(await dialog.evaluate((el) => el.matches(":modal"))).toBe(true);
    for (const key of ["Tab", "Tab", "Shift+Tab"]) {
      await page.keyboard.press(key);
      expect(await dialog.evaluate((el) => el.contains(document.activeElement))).toBe(
        true,
      );
    }
    if (cancelBy === "Escape") await page.keyboard.press("Escape");
    else await dialog.getByRole("button", { name: "取消", exact: true }).click();
    await expect(dialog).toHaveCount(0);
    await expect(trigger).toBeFocused();
    await expect(
      page.getByRole("heading", { name: "待删子层", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "待删子物体", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("textbox", { name: "场景摘要", exact: true }),
    ).toHaveValue("取消后保留的未保存摘要");
    expect(writes).toHaveLength(0);
  }
  await page.getByRole("button", { name: "保存到场景库", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "更新已保存场景", exact: true }),
  ).toBeEnabled();
  expect(writes[0]).toMatchObject({
    ...original,
    scene_summary: "取消后保留的未保存摘要",
  });
  await trigger.focus();
  await trigger.press("Enter");
  await dialog.getByRole("button", { name: "确认删除", exact: true }).click();
  await expect(dialog).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "场景搭建", exact: true }),
  ).toBeFocused();
  for (const name of ["待删层", "待删子层", "待删根物体", "待删子物体"])
    await expect(page.getByRole("heading", { name, exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "保留层", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "保留物体", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "更新已保存场景", exact: true }).click();
  await expect.poll(() => writes.length).toBe(2);
  expect(writes[1]).toMatchObject({
    scene_name: original.scene_name,
    scene_summary: "取消后保留的未保存摘要",
    scene_layers: [survivor],
    selected_layer_id: survivor.id,
  });
  expect(wire.requests.filter((r) => r.method === "DELETE")).toEqual([]);
});

test("SCENE: saved-library delete is separate from load; cancellation and scoped confirmation preserve the editor", async ({
  page,
  wire,
}) => {
  const tree = [sceneLayer("saved-root", "保存层")];
  const body = {
    scene_name: "待删保存场景",
    scene_summary: "库中摘要",
    scene_layers: tree,
    selected_layer_id: tree[0].id,
    collapsed_layer_ids: [],
  };
  let items = [
    sceneRecord(body, "delete-saved", 4),
    sceneRecord({ ...body, scene_name: "保留保存场景" }, "keep-saved", 2),
  ];
  wire.on("GET", "/scene-library", () => ({ json: { items } }));
  wire.on("DELETE", "/scene-library/delete-saved", () => {
    items = items.filter((item) => item.scene_id !== "delete-saved");
    return { json: { deleted_scene_id: "delete-saved" } };
  });
  const writes: SceneSave[] = [];
  wire.on("POST", "/scene-library", (request) => {
    const payload = request.postDataJSON();
    writes.push(payload);
    return { json: sceneRecord(payload, "post-delete-save", 1) };
  });
  await page.goto("/scene-setup");
  const original = await importScene(page);
  await page
    .getByRole("textbox", { name: "场景摘要", exact: true })
    .fill("未保存编辑区摘要");
  await page.getByRole("button", { name: "已保存场景", exact: true }).click();
  const target = page
    .locator("div")
    .filter({ has: page.getByRole("button", { name: "载入场景", exact: true }) })
    .filter({ has: page.getByText("待删保存场景", { exact: true }) })
    .filter({ hasNot: page.getByText("保留保存场景", { exact: true }) })
    .first();
  await expect(
    target.getByRole("button", { name: "载入场景", exact: true }),
  ).toBeVisible();
  await expect(
    target.getByRole("button", { name: "删除已保存场景", exact: true }),
  ).not.toBeVisible();
  await target.getByText("删除操作", { exact: true }).click();
  const prompts: string[] = [];
  page.once("dialog", async (dialog) => {
    prompts.push(dialog.message());
    await dialog.dismiss();
  });
  await target.getByRole("button", { name: "删除已保存场景", exact: true }).click();
  expect(prompts).toEqual(["确认删除已保存场景“待删保存场景”？"]);
  await expect(
    page.getByRole("textbox", { name: "场景摘要", exact: true }),
  ).toHaveValue("未保存编辑区摘要");
  expect(wire.requests.filter((r) => r.method === "DELETE")).toEqual([]);
  page.once("dialog", (dialog) => dialog.accept());
  await target.getByRole("button", { name: "删除已保存场景", exact: true }).click();
  await expect(page.getByText("待删保存场景", { exact: true })).toHaveCount(0);
  await expect(page.getByText("保留保存场景", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("textbox", { name: "场景摘要", exact: true }),
  ).toHaveValue("未保存编辑区摘要");
  await page.getByRole("button", { name: "保存到场景库", exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  expect(writes[0]).toMatchObject({ ...original, scene_summary: "未保存编辑区摘要" });
  expect(wire.requests.filter((r) => r.method === "DELETE").map((r) => r.path)).toEqual(
    ["/scene-library/delete-saved"],
  );
});

test("SCENE: long generation failure preserves later input/focus and never applies or replays", async ({
  page,
  wire,
}) => {
  const gate = deferred();
  const detail = `SCENE-BEGIN-${"scene_generation_failure_".repeat(160)}-SCENE-END`;
  wire.on("POST", "/scene-setup/generate", async () => {
    await gate.promise;
    return { status: 503, json: { detail } };
  });
  await page.goto("/scene-setup");
  await importScene(page);
  const keyword = page.getByRole("textbox", { name: "场景生成关键词" });
  await keyword.fill("失败候选");
  await page.getByRole("button", { name: "根据关键词生成场景树", exact: true }).click();
  await expect
    .poll(() => wire.requests.filter((r) => r.method === "POST").length)
    .toBe(1);
  // Generation input changes belong to a newer request scope, so an old failure
  // must not replace its feedback or take focus.
  await keyword.fill("失败期间继续输入");
  const scroll = await page.evaluate(() => scrollY);
  gate.release();
  await expect(
    page.getByRole("button", { name: "根据关键词生成场景树", exact: true }),
  ).toBeEnabled();
  await expect(keyword).toHaveValue("失败期间继续输入");
  await expect(keyword).toBeFocused();
  expect(await page.evaluate(() => scrollY)).toBe(scroll);
  await expect(
    page.getByRole("textbox", { name: "场景名称", exact: true }),
  ).toHaveValue("原场景");
  await expect(
    page.getByRole("button", { name: "应用到编辑区", exact: true }),
  ).toHaveCount(0);
  await expect(page.locator("main").getByRole("alert")).toHaveCount(0);
  expect(wire.requests.filter((r) => r.method !== "GET").map((r) => r.path)).toEqual([
    "/scene-setup/generate",
  ]);
  await noHorizontalOverflow(page);
});

test("SCENE: edits during slow generation fence the late candidate", async ({
  page,
  wire,
}) => {
  const gate = deferred();
  wire.on("POST", "/scene-setup/generate", async () => {
    await gate.promise;
    return { json: sceneCandidate() };
  });
  await page.goto("/scene-setup");
  await importScene(page);
  await page.getByRole("textbox", { name: "场景生成关键词" }).fill("迟到候选");
  await page.getByRole("button", { name: "根据关键词生成场景树", exact: true }).click();
  await expect
    .poll(() => wire.requests.filter((r) => r.method === "POST").length)
    .toBe(1);
  const name = page.getByRole("textbox", { name: "场景名称", exact: true });
  await name.fill("生成中继续编辑");
  gate.release();
  await expect(
    page.getByRole("button", { name: "根据关键词生成场景树", exact: true }),
  ).toBeEnabled();
  await expect(name).toHaveValue("生成中继续编辑");
  await expect(name).toBeFocused();
  await expect(
    page.getByRole("button", { name: "应用到编辑区", exact: true }),
  ).toHaveCount(0);
  expect(wire.requests.filter((r) => r.method !== "GET")).toHaveLength(1);
});

test("SCENE: slow consecutive create/update preserve newer edits and use the saved revision", async ({
  page,
  wire,
}) => {
  const gates = [deferred(), deferred()];
  const writes: (SceneSave & { expected_revision: number })[] = [];
  let saved: ReturnType<typeof sceneRecord> | undefined;
  wire.on("GET", "/scene-library", () => ({ json: { items: saved ? [saved] : [] } }));
  for (const [method, path] of [
    ["POST", "/scene-library"],
    ["PUT", "/scene-library/saved-ux"],
  ])
    wire.on(method, path, async (request) => {
      const body = request.postDataJSON();
      const index = writes.length;
      writes.push(body);
      await gates[index].promise;
      saved = sceneRecord(body, "saved-ux", index + 1);
      return { json: saved };
    });
  await page.goto("/scene-setup");
  await importScene(page);
  const name = page.getByRole("textbox", { name: "场景名称", exact: true });
  await page.getByRole("button", { name: "保存到场景库", exact: true }).click();
  await expect.poll(() => writes.length).toBe(1);
  await name.fill("第一次在途输入");
  gates[0].release();
  await expect(
    page.getByRole("button", { name: "更新已保存场景", exact: true }),
  ).toBeEnabled();
  await expect(name).toHaveValue("第一次在途输入");
  await page.getByRole("button", { name: "更新已保存场景", exact: true }).click();
  await expect.poll(() => writes.length).toBe(2);
  await name.fill("第二次在途输入");
  gates[1].release();
  await expect(
    page.getByRole("status").filter({ hasText: "已更新已保存场景" }),
  ).toBeVisible();
  await expect(name).toHaveValue("第二次在途输入");
  await expect(name).toBeFocused();
  expect(
    writes.map((body) => ({ name: body.scene_name, revision: body.expected_revision })),
  ).toEqual([
    { name: "原场景", revision: 0 },
    { name: "第一次在途输入", revision: 1 },
  ]);
  expect(wire.requests.filter((r) => r.method !== "GET")).toHaveLength(2);
});

test("SCENE: populated saved-library search matches name/summary, has an empty state and never writes", async ({
  page,
  wire,
}) => {
  const layers = [sceneLayer("root", "实验室")];
  const body = {
    scene_name: "北塔",
    scene_summary: "恒星观测",
    scene_layers: layers,
    selected_layer_id: "root",
    collapsed_layer_ids: [],
  };
  wire.on("GET", "/scene-library", () => ({
    json: {
      items: [
        sceneRecord(body, "tower", 1),
        sceneRecord(
          { ...body, scene_name: "地下室", scene_summary: "矿物标本" },
          "basement",
          3,
        ),
      ],
    },
  }));
  await page.goto("/scene-setup");
  await page.getByRole("button", { name: "已保存场景", exact: true }).click();
  const search = page.getByRole("searchbox", { name: "搜索已保存场景" });
  await search.fill("恒星");
  await expect(page.getByText("北塔", { exact: true })).toBeVisible();
  await expect(page.getByText("地下室", { exact: true })).not.toBeVisible();
  await search.fill("地下室");
  await expect(page.getByText("地下室", { exact: true })).toBeVisible();
  await search.fill("不存在");
  await expect(page.getByText("没有匹配的场景。", { exact: true })).toBeVisible();
  await expect(search).toBeFocused();
  await noHorizontalOverflow(page);
  expect(wire.requests.filter((r) => r.method !== "GET")).toEqual([]);
});
