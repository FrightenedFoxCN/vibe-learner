import { test, expect, type Page } from "@playwright/test";
import { populatedLearning } from "./learning-fixture";

const api = "http://127.0.0.1:18999";
async function questionHarness(page: Page, type: "multiple_choice" | "fill_blank" = "multiple_choice") {
  const h = await populatedLearning(page);
  h.session.turns[0].interactive_question = {
    schema_version: "study-interactive-question-v2", question_type: type,
    prompt: type === "multiple_choice" ? "Choose the stable invariant" : "Name the stable invariant",
    difficulty: "medium", topic: "Independent question", options: type === "multiple_choice" ? [{ key: "A", text: "Stable value" }, { key: "B", text: "Changing value" }] : [],
    call_back: false, result: null,
  };
  let fail = false;
  let readStarted = false;
  let release!: () => void;
  let gate: Promise<void> | null = null;
  const attempts: any[] = [];
  await page.route(`${api}/study-sessions/${h.session.id}/attempt`, async route => {
    const data = route.request().postDataJSON(); attempts.push(data);
    if (fail) return route.fulfill({ status: 409, json: { detail: "study_session_revision_conflict" } });
    const result = { schema_version: "study-question-result-v1", attempt_id: "attempt-independent", client_attempt_id: data.client_attempt_id,
      submitted_answer: data.submitted_answer, is_correct: true, feedback_text: "Independent answer saved", explanation: "Explanation only after committed read-back",
      before_revision: h.session.revision, committed_revision: h.session.revision + 1, committed_at: "2026-08-24T10:00:01+08:00" };
    h.session.turns[0].interactive_question.result = result;
    h.session.revision = result.committed_revision;
    h.session.updated_at = result.committed_at;
    await route.fulfill({ json: { ...result, schema_version: "study-question-attempt-response-v1", session_id: h.session.id, turn_id: data.turn_id } });
  });
  await page.route(`${api}/study-sessions/${h.session.id}`, async route => {
    readStarted = true; if (gate) await gate;
    await route.fulfill({ json: h.session });
  });
  await page.goto("/study");
  const group = page.getByRole("group", { name: type === "multiple_choice" ? "选择题（单选）" : "填空题", exact: true });
  await expect(group).toBeVisible();
  return { ...h, group, attempts, fail: () => { fail = true; }, blockRead: () => { gate = new Promise<void>(resolve => { release = resolve; }); }, releaseRead: () => release(), readStarted: () => readStarted };
}

test("independent question: native single choice keyboard semantics and 44px touch targets", async ({ page }, info) => {
  await page.setViewportSize({ width: 390, height: 844 });
  const h = await questionHarness(page);
  const radios = h.group.getByRole("radio");
  await expect(radios).toHaveCount(2);
  await expect(h.group.getByRole("checkbox")).toHaveCount(0);
  await radios.first().focus(); await page.keyboard.press("Space");
  await expect(radios.first()).toBeChecked();
  await page.keyboard.press("ArrowDown");
  await expect(radios.nth(1)).toBeChecked(); await expect(radios.first()).not.toBeChecked();
  await page.keyboard.press("ArrowUp"); await expect(radios.first()).toBeChecked();
  await page.keyboard.press("Tab");
  await expect(h.group.getByRole("button", { name: "提交答案", exact: true })).toBeFocused();
  const sizes = await h.group.locator("label, button").evaluateAll(elements => elements.map(el => ({ text: el.textContent, width: el.getBoundingClientRect().width, height: el.getBoundingClientRect().height })));
  expect(sizes.every(size => size.width >= 44 && size.height >= 44)).toBe(true);
  expect(h.attempts).toHaveLength(0);
  await info.attach("touch-targets.json", { body: JSON.stringify(sizes), contentType: "application/json" });
});

test("independent question: busy waits for persisted Session before feedback and explanation", async ({ page }) => {
  const h = await questionHarness(page); h.blockRead();
  await h.group.getByRole("radio", { name: "A. Stable value", exact: true }).check();
  await h.group.getByRole("button", { name: "提交答案", exact: true }).click();
  await expect.poll(h.readStarted).toBe(true);
  await expect(h.group).toHaveAttribute("aria-busy", "true");
  await expect(h.group.getByRole("radio").first()).toBeDisabled();
  await expect(h.group.getByRole("button", { name: "正在记录答案…", exact: true })).toBeDisabled();
  await expect(page.getByText("Independent answer saved · 已记录", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "查看解析", exact: true })).toHaveCount(0);
  h.releaseRead();
  const feedback = page.getByRole("status").filter({ hasText: "Independent answer saved · 已记录" });
  await expect(feedback).toBeVisible(); await expect(feedback).toBeFocused();
  await expect(h.group).toHaveAttribute("aria-busy", "false");
  const explanation = h.group.getByRole("button", { name: "查看解析", exact: true });
  await expect(explanation).toHaveAttribute("aria-expanded", "false");
  const controlledId = await explanation.getAttribute("aria-controls");
  await explanation.click(); await expect(h.group.getByRole("button", { name: "收起解析", exact: true })).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator(`[id="${controlledId}"]`)).toHaveText("Explanation only after committed read-back");
  expect(h.attempts).toHaveLength(1);
});

test("independent question: labelled blank Enter submits once and failed attempt announces and restores focus", async ({ page }) => {
  const h = await questionHarness(page, "fill_blank"); h.fail();
  const input = h.group.getByRole("textbox", { name: "你的答案", exact: true });
  await expect(input).toHaveAccessibleDescription(/Name the stable invariant/);
  const bounds = await input.boundingBox(); expect(bounds!.height).toBeGreaterThanOrEqual(44);
  await input.fill("Invariant"); await input.press("Enter");
  const alert = page.getByRole("alert").filter({ hasText: "答案未记录，请检查后重新提交。" });
  await expect(alert).toBeVisible(); await expect(alert).toBeFocused();
  await expect(h.group).toHaveAttribute("aria-busy", "false");
  await expect(input).toHaveValue("Invariant");
  await expect(input).toHaveAccessibleDescription(/答案未记录/);
  await expect(h.group.getByRole("button", { name: "重新提交答案", exact: true })).toBeEnabled();
  expect(h.attempts).toHaveLength(1);
});

test("independent question: delayed persisted read-back does not steal focus after navigation", async ({ page }) => {
  const h = await questionHarness(page); h.blockRead();
  await h.group.getByRole("radio", { name: "A. Stable value", exact: true }).check();
  await h.group.getByRole("button", { name: "提交答案", exact: true }).click();
  await expect.poll(h.readStarted).toBe(true);
  await page.locator('a[href="/settings"]').first().click();
  await expect(page).toHaveURL(/\/settings$/);
  const destination = page.locator('a[href="/plan"]').first(); await destination.focus();
  h.releaseRead(); await page.waitForLoadState("networkidle");
  await expect(destination).toBeFocused();
  await expect(page.getByText("Independent answer saved · 已记录", { exact: true })).toHaveCount(0);
  expect(h.attempts).toHaveLength(1);
});

test("independent question: focus moved to another control stays there after same-page save", async ({ page }) => {
  const h = await questionHarness(page); h.blockRead();
  await h.group.getByRole("radio", { name: "A. Stable value", exact: true }).check();
  await h.group.getByRole("button", { name: "提交答案", exact: true }).click();
  await expect.poll(h.readStarted).toBe(true);
  const other = page.locator('a[href="/settings"]').first(); await other.focus();
  h.releaseRead();
  await expect(page.getByText("Independent answer saved · 已记录", { exact: true })).toBeVisible();
  await expect(other).toBeFocused();
});
