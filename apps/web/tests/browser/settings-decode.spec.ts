import { test, expect } from "@playwright/test";
import { observeRequests } from "./api-fixture";
import responses from "../../../../packages/shared/fixtures/settings/responses-v1.json" with { type: "json" };

const api = "http://127.0.0.1:18999";

test("malformed Settings cannot initialize autosave or show configured defaults", async ({
  page,
}) => {
  const requests = await observeRequests(page);
  await page.route(`${api}/runtime-settings`, (route) =>
    route.fulfill({
      json: { ...responses.runtime_settings, show_debug_info: "false" },
    }),
  );
  page.on("request", (request) => {
    if (request.url().startsWith(api) && request.method() !== "GET")
      requests.push({
        method: request.method(),
        path: new URL(request.url()).pathname,
      });
  });
  await page.goto("/settings");
  await expect(page.getByText(/设置加载失败/)).toBeVisible();
  await expect(page.locator("[data-model-scope]")).toHaveCount(0);
  expect(requests.filter((request) => request.method !== "GET")).toHaveLength(
    0,
  );
});

test("string false in a tool flag fails visibly instead of enabling a checkbox", async ({
  page,
}) => {
  await observeRequests(page);
  const payload = structuredClone(responses.model_tools);
  const tool = payload.stages[0].tools[0];
  await page.route(`${api}/model-tools/config`, (route) =>
    route.fulfill({
      json: {
        ...payload,
        stages: [
          { ...payload.stages[0], tools: [{ ...tool, enabled: "false" }] },
        ],
      },
    }),
  );
  await page.goto("/sensory-tools");
  await expect(
    page.getByRole("alert").filter({ hasText: "配置操作失败" }),
  ).toBeVisible();
  await expect(
    page.getByRole("checkbox", { name: tool.label, exact: true }),
  ).toHaveCount(0);
});

test("Model Usage renders coherent provider totals and rejects malformed counters on reload", async ({
  page,
}) => {
  await observeRequests(page);
  let malformed = false;
  await page.route(`${api}/model-usage/stats`, (route) =>
    route.fulfill({
      json: { ...responses.model_usage, total_tokens: malformed ? "207" : 207 },
    }),
  );
  await page.goto("/model-usage");
  await expect(page.getByText("207", { exact: true }).first()).toBeVisible();
  malformed = true;
  await page.reload();
  await expect(
    page.getByText(/model_usage: expected_safe_integer/),
  ).toBeVisible();
});
