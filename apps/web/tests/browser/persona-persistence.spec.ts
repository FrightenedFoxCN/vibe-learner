import { test, expect } from "@playwright/test";
import { observeRequests } from "./api-fixture";

test("Persona create read-back binds the saved record while retaining edits made in flight", async ({ page }) => {
  await observeRequests(page);
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  let saved: Record<string, unknown> | undefined;
  await page.route("http://127.0.0.1:18999/personas", async route => {
    if (route.request().method() === "POST") {
      saved = { ...route.request().postDataJSON(), id: "created-persona", revision: 1, source: "user" };
      await pending;
      await route.fulfill({ json: saved });
    } else if (saved) {
      await route.fulfill({ json: { items: [saved] } });
    } else await route.fallback();
  });
  await page.goto("/persona-spectrum");
  const name = page.getByRole("textbox", { name: "名称", exact: true });
  await expect(name).toHaveValue("Fixture Mentor");
  await page.getByRole("button", { name: "新建人格草稿", exact: true }).click();
  await name.fill("Submitted name");
  const sent = page.waitForRequest(request => request.method() === "POST" && request.url().endsWith("/personas"));
  await page.getByRole("button", { name: "创建人格", exact: true }).click();
  await sent;
  await name.fill("Later edit");
  release();
  await expect(page.getByRole("button", { name: "更新人格", exact: true })).toBeEnabled();
  await expect(name).toHaveValue("Later edit");
  expect(saved?.name).toBe("Submitted name");
});
