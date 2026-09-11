import { test, expect } from "@playwright/test";
import { populatedLearning } from "./learning-fixture";

const api = "http://127.0.0.1:18999";
async function revisionHarness(page: Parameters<typeof populatedLearning>[0]) {
  const h = await populatedLearning(page);
  const plan = Object.assign(h.plan, { revision: 0 });
  let current: any = null;
  let loseCreate = false;
  let loseDecision = false;
  let createGate: Promise<void> | null = null;
  let releaseCreate: (() => void) | undefined;
  await page.route(`${api}/learning-plans/${plan.id}/revision-history`, route => route.fulfill({ json: { revisions: [plan.revision] } }));
  await page.route(`${api}/learning-plans/${plan.id}/revisions`, async route => {
    const input = route.request().postDataJSON();
    const base = structuredClone(plan);
    current = { operation_id: `plan-revision-${"a".repeat(32)}`, client_request_id: input.client_request_id,
      plan_id: plan.id, base_revision: input.base_revision, instruction: input.instruction,
      rollback_revision: input.rollback_revision, status: "ready", base_plan: base, result: null, error_code: "",
      proposal: { schema_name: "PlanRevisionProposal", schema_version: "plan-revision-proposal-v1", explanation: "Independent revision",
        course_title: "Revised Course", overview: "Revised Overview", today_tasks: ["Review examples"],
        schedule: base.schedule.map((s: any) => ({ schedule_ref: s.id, title: "Revised Unit", focus: "Review examples" })) } };
    if (createGate) await createGate;
    if (loseCreate) await route.abort("failed"); else await route.fulfill({ json: current });
  });
  await page.route(`${api}/learning-plans/${plan.id}/revisions/*`, route => route.fulfill({ json: current }));
  await page.route(`${api}/learning-plans/${plan.id}/revisions/*/decision`, async route => {
    const decision = route.request().postDataJSON().decision;
    if (decision === "reject") current.status = "rejected";
    else if (plan.revision !== current.base_revision) current.status = "conflict";
    else {
      Object.assign(plan, { revision: current.base_revision + 1, course_title: current.proposal.course_title, overview: current.proposal.overview, today_tasks: current.proposal.today_tasks,
        schedule: current.proposal.schedule.map((item: any) => ({ ...current.base_plan.schedule.find((s: any) => s.id === item.schedule_ref), title: item.title, focus: item.focus })) });
      plan.study_unit_progress = plan.study_unit_progress.map(p => ({ ...p, objective_fragment: plan.schedule.find(s => s.unit_id === p.unit_id)!.focus }));
      current.status = "accepted"; current.result = structuredClone(plan);
    }
    if (loseDecision) await route.abort("failed"); else await route.fulfill({ json: current });
  });
  await page.goto("/plan");
  await page.getByText("修订计划 · 版本 0", { exact: true }).click();
  const panel = page.getByRole("region", { name: "计划修订", exact: true });
  await panel.getByRole("textbox", { name: "修订要求" }).fill("Review examples first");
  return { ...h, plan, panel, loseCreate: () => { loseCreate = true; }, loseDecision: () => { loseDecision = true; }, current: () => current, blockCreate: () => { createGate = new Promise<void>(resolve => { releaseCreate = resolve; }); }, releaseCreate: () => releaseCreate?.() };
}

test("independent revision: diff then reject leaves source plan unchanged", async ({ page }) => {
  const h = await revisionHarness(page);
  const before = structuredClone(h.plan);
  await h.panel.getByRole("button", { name: "生成修订预览", exact: true }).click();
  await expect(h.panel.getByRole("table", { name: "修订差异" })).toBeVisible();
  await expect(h.panel.getByRole("cell", { name: "Historical Course", exact: true })).toBeVisible();
  await expect(h.panel.getByRole("cell", { name: "Revised Course", exact: true })).toBeVisible();
  await h.panel.getByRole("button", { name: "拒绝修订", exact: true }).click();
  await expect(h.panel.getByText("已拒绝此修订，计划没有变化。", { exact: true })).toBeVisible();
  expect(h.plan).toEqual(before);
});

test("independent revision: lost creation response only queries on refresh", async ({ page }) => {
  const h = await revisionHarness(page); h.loseCreate();
  await h.panel.getByRole("button", { name: "生成修订预览", exact: true }).click();
  await expect(h.panel.getByRole("button", { name: "查询本次修订结果", exact: true })).toBeEnabled();
  await expect(h.panel.getByRole("button", { name: "生成修订预览", exact: true })).toBeDisabled();
  await page.reload();
  await expect(h.panel.getByRole("button", { name: "接受修订", exact: true })).toBeVisible();
  expect(h.requests.filter(r => r.method === "POST")).toHaveLength(1);
  expect(h.requests.some(r => r.method === "GET" && r.path.endsWith(`/${h.current().client_request_id}`))).toBe(true);
});

test("independent revision: lost accept response fences all decisions until GET recovery", async ({ page }) => {
  const h = await revisionHarness(page);
  await h.panel.getByRole("button", { name: "生成修订预览", exact: true }).click();
  await expect(h.panel.getByRole("button", { name: "接受修订", exact: true })).toBeVisible();
  h.loseDecision();
  await h.panel.getByRole("button", { name: "接受修订", exact: true }).click();
  await expect(h.panel.getByText("保存结果未确认，请查询本次修订；不要重复接受。", { exact: true })).toBeVisible();
  // Hidden or disabled are both safe; an enabled ready decision would replay a POST.
  expect(await h.panel.getByRole("button", { name: "接受修订", exact: true }).isEnabled().catch(() => false)).toBe(false);
  expect(await h.panel.getByRole("button", { name: "拒绝修订", exact: true }).isEnabled().catch(() => false)).toBe(false);
  await h.panel.getByRole("button", { name: "查询本次修订结果", exact: true }).click();
  await expect(page.getByText("修订计划 · 版本 1", { exact: true })).toBeVisible();
  expect(h.requests.filter(r => r.method === "POST")).toHaveLength(2);
  expect(h.plan.schedule[0].status).toBe("planned");
});

test("independent revision: concurrent plan revision disables stale acceptance after refresh", async ({ page }) => {
  const h = await revisionHarness(page);
  await h.panel.getByRole("button", { name: "生成修订预览", exact: true }).click();
  await expect(h.panel.getByRole("button", { name: "接受修订", exact: true })).toBeVisible();
  h.plan.revision = 1;
  await h.panel.getByRole("button", { name: "刷新当前计划", exact: true }).click();
  await expect(h.panel.getByRole("alert")).toContainText("计划版本已变化");
  await expect(h.panel.getByRole("button", { name: "接受修订", exact: true })).toBeDisabled();
  expect(h.requests.filter(r => r.method === "POST")).toHaveLength(1);
});


test("independent revision: late preview after leaving owner recovers original request without repost", async ({ page }) => {
  const h = await revisionHarness(page); h.blockCreate();
  await h.panel.getByRole("button", { name: "生成修订预览", exact: true }).click();
  await expect.poll(() => h.current()?.client_request_id).toBeTruthy();
  await page.locator('a[href="/settings"]').first().click();
  await expect(page).toHaveURL(/\/settings$/);
  h.releaseCreate();
  await page.waitForLoadState("networkidle");
  await expect(page.getByRole("region", { name: "计划修订", exact: true })).toHaveCount(0);
  await page.locator('a[href="/plan"]').first().click();
  await expect(h.panel.getByRole("table", { name: "修订差异" })).toBeVisible();
  expect(h.requests.filter(r => r.method === "POST")).toHaveLength(1);
  expect(h.requests.some(r => r.method === "GET" && r.path.endsWith(`/${h.current().client_request_id}`))).toBe(true);
});

test("independent revision: definite admission conflict unlocks only a new explicit preview", async ({ page }) => {
  const h = await revisionHarness(page);
  await page.route(`${api}/learning-plans/${h.plan.id}/revisions`, route => route.fulfill({ status: 409, json: { detail: "learning_plan_revision_conflict" } }));
  await h.panel.getByRole("button", { name: "生成修订预览", exact: true }).click();
  await expect(h.panel.getByText("请求未被接收，请刷新当前计划后重新生成预览。", { exact: true })).toBeVisible();
  await expect(h.panel.getByRole("button", { name: "生成修订预览", exact: true })).toBeEnabled();
  expect(await page.evaluate(id => localStorage.getItem(`vibe-learner:plan-revision:v1:${id}`), h.plan.id)).toBeNull();
  expect(h.requests.filter(r => r.method === "POST")).toHaveLength(1);
});

test("independent revision: missing record requires explicit local abandonment without POST replay", async ({ page }) => {
  const h = await revisionHarness(page); h.loseCreate();
  await h.panel.getByRole("button", { name: "生成修订预览", exact: true }).click();
  await expect(h.panel.getByRole("button", { name: "查询本次修订结果", exact: true })).toBeEnabled();
  await page.route(`${api}/learning-plans/${h.plan.id}/revisions/*`, route => route.fulfill({ status: 404, json: { detail: "plan_revision_not_found" } }));
  await h.panel.getByRole("button", { name: "查询本次修订结果", exact: true }).click();
  await expect(h.panel.getByRole("button", { name: "生成修订预览", exact: true })).toBeDisabled();
  await h.panel.getByRole("button", { name: "清除未找到的恢复记录", exact: true }).click();
  await expect(h.panel.getByRole("button", { name: "生成修订预览", exact: true })).toBeEnabled();
  expect(h.requests.filter(r => r.method === "POST")).toHaveLength(1);
  expect(await page.evaluate(id => localStorage.getItem(`vibe-learner:plan-revision:v1:${id}`), h.plan.id)).toBeNull();
});
