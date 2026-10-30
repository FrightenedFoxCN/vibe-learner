import { wireModelTools } from "../support/model-config-wire";
import { test, expect, deferred, noHorizontalOverflow } from "./remaining-ux-fixtures";

function stages() {
  return ["study", "planning", "disabled"].map((name) => ({
    name,
    label: name === "study" ? "学习" : "规划",
    stage_enabled: name !== "disabled",
    tools: Array.from({ length: 24 }, (_, i) => ({
      name: `tool-${i}`,
      label: `${name} 工具 ${i}`,
      description: `用途-${name}-${i}`,
      category: i < 20 ? "read" : "write",
      category_label: i < 20 ? "读取" : "写入",
      enabled: i === 12,
      available: name !== "disabled" && i !== 17,
      unavailable_reason: i === 17 ? "环境不支持" : "",
    })),
  }));
}

test("SENSORY: slow consecutive saves serialize, roll back only failure, and retain focus/scroll", async ({
  page,
  wire,
}) => {
  const data = stages();
  const gates = [deferred(), deferred(), deferred()];
  const writes: unknown[] = [];
  wire.on("GET", "/model-tools/config", () => ({ json: wireModelTools(data) }));
  wire.on("PATCH", "/model-tools/config", async (request) => {
    const index = writes.length;
    const body = request.postDataJSON();
    writes.push(body);
    await gates[index].promise;
    if (index === 1) return { status: 503, json: { detail: "第二次保存失败" } };
    for (const toggle of body.toggles)
      data
        .find((s) => s.name === toggle.stage_name)!
        .tools.find((t) => t.name === toggle.tool_name)!.enabled = toggle.enabled;
    return { json: wireModelTools(data) };
  });
  await page.goto("/sensory-tools");
  const first = page.getByRole("checkbox", { name: "study 工具 12", exact: true });
  const second = page.getByRole("checkbox", { name: "study 工具 13", exact: true });
  const third = page.getByRole("checkbox", { name: "study 工具 14", exact: true });
  await first.focus();
  await first.press("Space");
  await expect.poll(() => writes.length).toBe(1);
  await second.focus();
  await second.press("Space");
  await third.focus();
  await third.press("Space");
  const scroll = await page.evaluate(() => scrollY);
  expect(writes).toHaveLength(1);
  gates[0].release();
  await expect.poll(() => writes.length).toBe(2);
  await expect(first).not.toBeChecked();
  gates[1].release();
  await expect.poll(() => writes.length).toBe(3);
  await expect(second).not.toBeChecked();
  await expect(third).toBeChecked();
  gates[2].release();
  await expect(
    page.getByRole("status").filter({ hasText: "工具配置已保存。" }),
  ).toBeVisible();
  await expect(third).toBeFocused();
  expect(await page.evaluate(() => scrollY)).toBe(scroll);
  expect(writes).toEqual(
    [12, 13, 14].map((i) => ({
      toggles: [{ stage_name: "study", tool_name: `tool-${i}`, enabled: i !== 12 }],
    })),
  );
  expect(wire.requests.filter((r) => r.method === "PATCH")).toHaveLength(3);
});

for (const firstFails of [false, true]) {
  test(`SENSORY: three reversals of the same tool retain the latest intent after slow ${firstFails ? "failure" : "success"}`, async ({
    page,
    wire,
  }) => {
    const data = stages();
    const gate = deferred();
    const writes: {
      toggles: { stage_name: string; tool_name: string; enabled: boolean }[];
    }[] = [];
    wire.on("GET", "/model-tools/config", () => ({ json: wireModelTools(data) }));
    wire.on("PATCH", "/model-tools/config", async (request) => {
      const body = request.postDataJSON();
      writes.push(body);
      if (writes.length === 1) {
        await gate.promise;
        if (firstFails)
          return { status: 503, json: { detail: "第一次保存失败，保留后续操作" } };
      }
      data[0].tools[0].enabled = body.toggles[0].enabled;
      return { json: wireModelTools(data) };
    });
    await page.goto("/sensory-tools");
    const toggle = page.getByRole("checkbox", { name: "study 工具 0", exact: true });
    await toggle.focus();
    await toggle.press("Space");
    await expect.poll(() => writes.length).toBe(1);
    await toggle.press("Space");
    await toggle.press("Space");
    gate.release();
    await expect(
      page.getByRole("status").filter({ hasText: "工具配置已保存。" }),
    ).toBeVisible();
    await expect.poll(() => writes.length).toBe(3);
    expect(writes.map((body) => body.toggles[0].enabled)).toEqual([true, false, true]);
    await expect(toggle).toBeChecked();
    await expect(toggle).toBeFocused();
  });
}

test("SENSORY: stage/category/availability filters bound batch writes and preserve disabled stage", async ({
  page,
  wire,
}) => {
  const data = stages();
  const writes: unknown[] = [];
  wire.on("GET", "/model-tools/config", () => ({ json: wireModelTools(data) }));
  wire.on("PATCH", "/model-tools/config", (request) => {
    const body = request.postDataJSON();
    writes.push(body);
    for (const toggle of body.toggles)
      data
        .find((s) => s.name === toggle.stage_name)!
        .tools.find((t) => t.name === toggle.tool_name)!.enabled = toggle.enabled;
    return { json: wireModelTools(data) };
  });
  await page.goto("/sensory-tools");
  await expect(
    page.getByRole("status").filter({ hasText: "找到 72 个工具" }),
  ).toBeVisible();
  await expect(page.getByText("用途-study-0", { exact: true })).not.toBeVisible();
  await page.getByRole("checkbox", { name: "展开用途说明" }).check();
  await expect(page.getByText("用途-study-0", { exact: true })).toBeVisible();
  await page.getByRole("combobox", { name: "工作阶段" }).selectOption("planning");
  await page.getByRole("searchbox", { name: "搜索工具" }).fill("工具 1");
  await page.getByRole("combobox", { name: "可用性" }).selectOption("unavailable");
  await expect(
    page.getByRole("status").filter({ hasText: "找到 1 个工具" }),
  ).toBeVisible();
  await expect(
    page.getByRole("checkbox", { name: "planning 工具 17", exact: true }),
  ).toBeDisabled();
  await page.getByRole("combobox", { name: "可用性" }).selectOption("available");
  await page.getByRole("button", { name: "批量管理", exact: true }).click();
  await page.getByRole("button", { name: "启用筛选结果", exact: true }).click();
  await expect(
    page.getByRole("status").filter({ hasText: "工具配置已保存。" }),
  ).toBeVisible();
  expect(writes).toEqual([
    {
      toggles: [1, 10, 11, 13, 14, 15, 16, 18, 19].map((i) => ({
        stage_name: "planning",
        tool_name: `tool-${i}`,
        enabled: true,
      })),
    },
  ]);
  await page.getByRole("combobox", { name: "工作阶段" }).selectOption("disabled");
  await page.getByRole("combobox", { name: "可用性" }).selectOption("");
  expect(data[2].stage_enabled).toBe(false);
  expect(wireModelTools(data).stages[2].tools.every((t) => !t.effective_enabled)).toBe(
    true,
  );
  await expect(page.getByText("阶段关闭", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "启用筛选结果", exact: true }).click();
  await page.getByRole("searchbox", { name: "搜索工具" }).fill("不存在的工具");
  await expect(
    page.getByText("没有匹配的工具，请调整搜索或筛选。", { exact: true }),
  ).toBeVisible();
  expect(writes).toHaveLength(1);
  await noHorizontalOverflow(page);
});

test("SENSORY: long failed save remains readable and does not steal later search focus", async ({
  page,
  wire,
}) => {
  const gate = deferred();
  const detail = `LONG-BEGIN-${"无法保存配置/请稍后重试_".repeat(160)}-LONG-END`;
  wire.on("GET", "/model-tools/config", () => ({ json: wireModelTools(stages()) }));
  wire.on("PATCH", "/model-tools/config", async () => {
    await gate.promise;
    return { status: 503, json: { detail } };
  });
  await page.goto("/sensory-tools");
  await page.getByRole("checkbox", { name: "study 工具 12", exact: true }).click();
  await expect
    .poll(() => wire.requests.filter((r) => r.method === "PATCH").length)
    .toBe(1);
  const search = page.getByRole("searchbox", { name: "搜索工具" });
  await search.fill("study 工具 12");
  const scroll = await page.evaluate(() => scrollY);
  gate.release();
  const alert = page.locator("main").getByRole("alert");
  await expect(alert).toContainText("LONG-BEGIN");
  await expect(alert).toContainText("LONG-END");
  await expect(search).toBeFocused();
  expect(await page.evaluate(() => scrollY)).toBe(scroll);
  await expect(
    page.getByRole("checkbox", { name: "study 工具 12", exact: true }),
  ).toBeChecked();
  await noHorizontalOverflow(page);
  expect(wire.requests.filter((r) => r.method === "PATCH")).toHaveLength(1);
});
