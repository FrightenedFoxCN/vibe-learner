import { test, expect } from "@playwright/test";

const api = "http://127.0.0.1:18443";

test("French planning and inherited Study language survive navigation and reload; a Study override persists", async ({
  page,
}) => {
  const pageErrors: string[] = [];
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await page.goto("/plan");
  await page
    .getByRole("combobox", { name: "创建方式", exact: true })
    .selectOption("goal_only");
  await page
    .getByRole("textbox", { name: "学习目标", exact: true })
    .fill("Study vector spaces and linear maps");
  await page
    .getByRole("combobox", { name: "输出语言", exact: true })
    .selectOption("fr");
  await page.reload();
  await expect(
    page.getByRole("combobox", { name: "输出语言", exact: true }),
  ).toHaveValue("fr");
  const planResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith("/learning-plans/stream") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "按目标生成", exact: true }).click();
  const generated = await planResponse;
  expect(generated.request().postDataJSON().planning_intent.output_language).toEqual({
    status: "user_explicit",
    value: "fr",
  });
  await expect(
    page.getByRole("button", { name: "按目标生成", exact: true }),
  ).toBeEnabled({ timeout: 20000 });
  const plans = await (await page.request.get(`${api}/learning-plans`)).json();
  expect(plans.items).toHaveLength(1);
  const plan = plans.items[0];
  expect(plan.output_language).toBe("fr");
  expect(plan.today_tasks.some((task: string) => task.includes("Objectif"))).toBe(true);
  await page.goto(`/study?plan=${encodeURIComponent(plan.id)}`);
  const create = page.getByRole("button", {
    name: /创建.*会话|开始.*学习|开始对话|开启学习/,
  });
  if (await create.count()) await create.first().click();
  await expect(
    page.getByRole("combobox", { name: "输出语言", exact: true }),
  ).toHaveValue("fr");
  const question = page.getByRole("textbox", { name: /^向.*提问$/ });
  await question.fill("Explain a vector basis");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByText(/Commençons par le concept central/).first()).toBeVisible(
    { timeout: 15000 },
  );
  await page.reload();
  await expect(
    page.getByRole("combobox", { name: "输出语言", exact: true }),
  ).toHaveValue("fr");
  await page
    .getByRole("combobox", { name: "输出语言", exact: true })
    .selectOption("en");
  await question.fill("Give me the next step");
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect(page.getByText(/First identify the core concept/).first()).toBeVisible({
    timeout: 15000,
  });
  await page.reload();
  await expect(
    page.getByRole("combobox", { name: "输出语言", exact: true }),
  ).toHaveValue("en");
  await page.screenshot({
    path: "/tmp/vibe-output-language-study.png",
    fullPage: true,
    animations: "disabled",
  });
  const layout = await page
    .getByRole("combobox", { name: "输出语言", exact: true })
    .evaluate((field) => {
      const rectangle = field.getBoundingClientRect();
      const target = document.elementFromPoint(
        rectangle.x + rectangle.width / 2,
        rectangle.y + rectangle.height / 2,
      );
      return {
        hit: target === field,
        width: rectangle.width,
        height: rectangle.height,
        scrollX: window.scrollX,
        x: rectangle.x,
        viewportWidth: innerWidth,
        scrollWidth: document.documentElement.scrollWidth,
        padding: getComputedStyle(document.querySelector("main")!).paddingLeft,
      };
    });
  await test.info().attach("language-control-layout", {
    body: JSON.stringify(layout),
    contentType: "application/json",
  });
  expect(layout.hit).toBe(true);
  expect(layout.height).toBeGreaterThanOrEqual(44);
  expect(layout.scrollWidth).toBeLessThanOrEqual(layout.viewportWidth);
  expect(pageErrors).toEqual([]);
});
