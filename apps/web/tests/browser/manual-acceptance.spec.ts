import { expect, test, type Page, type TestInfo } from "@playwright/test";

const api = "http://127.0.0.1:18996";
const web = "http://127.0.0.1:13417";
const pendingKey = "vibe-learner:pending-study-chat-operation:v1";
const goal = "用一周掌握 Python 循环，每天 30 分钟";
const personaName = "手册验收导师";
const sceneName = "手册验收自习室";
const browserDiagnostics = new WeakMap<
  Page,
  { pageErrors: string[]; blocked: string[] }
>();

async function read(page: Page, path: string) {
  const response = await page.request.get(`${api}${path}`);
  expect(response.ok(), path).toBe(true);
  return response.json();
}

async function evidence(info: TestInfo, name: string, value: unknown) {
  await info.attach(name, {
    body: JSON.stringify(value, null, 2),
    contentType: "application/json",
  });
}

async function tavernGeometry(page: Page) {
  return page.evaluate(() => {
    function measure(selector: string) {
      const element = document.querySelector(selector);
      if (!element) throw new Error(`Missing Tavern geometry subject: ${selector}`);
      const rect = element.getBoundingClientRect();
      const style = getComputedStyle(element);
      return {
        rect: {
          x: rect.x,
          y: rect.y,
          left: rect.left,
          right: rect.right,
          top: rect.top,
          bottom: rect.bottom,
          width: rect.width,
          height: rect.height,
        },
        computed: {
          padding: style.padding,
          paddingLeft: style.paddingLeft,
          paddingRight: style.paddingRight,
          appNavWidth: style.getPropertyValue("--app-nav-width").trim(),
          position: style.position,
          transform: style.transform,
          transition: style.transition,
        },
      };
    }
    const main = measure("main.tavern-page");
    const header = measure(".tavern-header");
    const headerH1 = measure(".tavern-header h1");
    const nav = measure(".app-side-nav");
    const sessionPanel = measure(".tavern-session-panel");
    const mainAnimations = document
      .querySelector("main.tavern-page")!
      .getAnimations()
      .filter((animation) => animation.playState === "running")
      .map((animation) => ({
        type: animation.constructor.name,
        currentTime: String(animation.currentTime),
        keyframes:
          animation.effect instanceof KeyframeEffect
            ? animation.effect.getKeyframes()
            : [],
      }));
    return {
      scrollX: window.scrollX,
      scrollY: window.scrollY,
      document: {
        scrollWidth: document.documentElement.scrollWidth,
        clientWidth: document.documentElement.clientWidth,
        scrollHeight: document.documentElement.scrollHeight,
        clientHeight: document.documentElement.clientHeight,
      },
      viewport: {
        innerWidth,
        innerHeight,
        devicePixelRatio,
        visual: window.visualViewport
          ? {
              width: window.visualViewport.width,
              height: window.visualViewport.height,
              offsetLeft: window.visualViewport.offsetLeft,
              offsetTop: window.visualViewport.offsetTop,
              pageLeft: window.visualViewport.pageLeft,
              pageTop: window.visualViewport.pageTop,
              scale: window.visualViewport.scale,
            }
          : null,
      },
      rootAppNavWidth: getComputedStyle(document.documentElement)
        .getPropertyValue("--app-nav-width")
        .trim(),
      main,
      header,
      headerH1,
      nav,
      sessionPanel,
      mainAnimations,
      clearOfNav: {
        headerH1:
          headerH1.rect.left >= nav.rect.right &&
          headerH1.rect.right <= document.documentElement.clientWidth,
        sessionPanel:
          sessionPanel.rect.left >= nav.rect.right &&
          sessionPanel.rect.right <= document.documentElement.clientWidth,
      },
    };
  });
}

async function assertTavernGeometry(page: Page, info: TestInfo, phase: string) {
  const samples: Awaited<ReturnType<typeof tavernGeometry>>[] = [];
  try {
    await expect
      .poll(
        async () => {
          const sample = await tavernGeometry(page);
          if (samples.length < 12) samples.push(sample);
          else samples[11] = sample;
          return {
            ...sample.clearOfNav,
            layoutSettled: sample.mainAnimations.length === 0,
          };
        },
        {
          message: `Tavern Header h1 and Tavern Session Panel must both clear the navigation (${phase})`,
          timeout: 5_000,
          intervals: [100, 200, 400],
        },
      )
      .toEqual({ headerH1: true, sessionPanel: true, layoutSettled: true });
  } finally {
    await evidence(info, `tavern-geometry-${phase}.json`, samples);
  }
}

test.beforeEach(async ({ context, page }, info) => {
  const pageErrors: string[] = [];
  const blocked: string[] = [];
  browserDiagnostics.set(page, { pageErrors, blocked });
  page.on("pageerror", (error) => pageErrors.push(error.message));
  await context.addInitScript((base) => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = {
      aiBaseUrl: base,
      isDesktop: false,
      platform: "unknown",
      secretStorageMode: "plain_text",
      vaultState: "unconfigured",
      vaultPath: "",
      storageRoot: "",
      startupError: "",
    };
  }, api);
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if ([web, api].includes(url.origin)) await route.continue();
    else {
      blocked.push(url.origin + url.pathname);
      await route.abort("blockedbyclient");
    }
  });
  // Keep diagnostics bounded and fail visibly on accidental access to another backend.
  info.annotations.push({
    type: "scope",
    description: "production Web 13417; disposable mock API 18996",
  });
});

test.afterEach(async ({ page }, info) => {
  const diagnostics = browserDiagnostics.get(page)!;
  await evidence(info, "browser-diagnostics.json", diagnostics);
  expect(diagnostics.pageErrors).toEqual([]);
  expect(diagnostics.blocked).toEqual([]);
});

test("01 fresh data, manual navigation and first mock Settings save survive reload", async ({
  page,
}, info) => {
  const baseline = await read(page, "/__acceptance__/evidence");
  expect(baseline.auto_migrate_local_data).toBe(false);
  expect(baseline.allowed_origins).toEqual([web]);
  expect(baseline.provider_guard).toBe("mock_without_secrets_only");
  expect(baseline.storage_root).toContain("vibe-manual-acceptance-");
  const preflight = await page.request.fetch(`${api}/runtime-settings`, {
    method: "OPTIONS",
    headers: { Origin: web, "Access-Control-Request-Method": "PATCH" },
  });
  expect(preflight.headers()["access-control-allow-origin"]).toBe(web);
  for (const path of [
    "/documents",
    "/learning-plans",
    "/study-sessions",
    "/scene-library",
    "/tavern/rooms",
  ]) {
    expect((await read(page, path)).items, `empty ${path}`).toEqual([]);
  }
  await page.goto("/manual");
  await expect(
    page.getByRole("heading", { name: "用户手册", exact: true }),
  ).toBeVisible();
  const contents = page.getByRole("navigation", { name: "手册目录" });
  await expect(contents.getByRole("link")).toHaveCount(7);
  for (const id of [
    "start",
    "study",
    "characters",
    "tavern",
    "recovery",
    "data",
    "install",
  ]) {
    await contents.locator(`a[href="#${id}"]`).click();
    await expect(page.locator(`#${id} h2`)).toBeInViewport();
  }
  await page
    .locator("#start")
    .getByRole("link", { name: "统一设置", exact: true })
    .click();
  await expect(page).toHaveURL(/\/settings$/);
  const provider = page.getByRole("combobox", { name: "模型接口协议", exact: true });
  await expect(provider).toHaveValue("mock");
  await provider.selectOption("mock");
  const settingsSaved = page.waitForResponse(
    (response) =>
      response.url() === `${api}/runtime-settings` &&
      response.request().method() === "PATCH",
  );
  await page.getByRole("checkbox", { name: "显示调试悬浮窗", exact: true }).uncheck();
  expect((await settingsSaved).ok()).toBe(true);
  await expect(page.getByText("已保存", { exact: true })).toBeVisible();
  await page.reload();
  await expect(provider).toHaveValue("mock");
  await expect(
    page.getByRole("checkbox", { name: "显示调试悬浮窗", exact: true }),
  ).not.toBeChecked();
  const settings = await read(page, "/runtime-settings");
  expect(settings.plan_provider).toBe("mock");
  for (const key of [
    "openai_api_key",
    "openai_plan_api_key",
    "openai_setting_api_key",
    "openai_chat_api_key",
  ])
    expect(settings[key]).toBeFalsy();
  await evidence(info, "fresh-mock-settings.json", { baseline, settings });
});

async function generatePlan(
  page: Page,
  mode: "goal_only" | "document",
  objective: string,
) {
  await page.goto("/manual");
  await page
    .locator("#start")
    .getByRole("link", { name: "计划生成", exact: true })
    .click();
  await page
    .getByRole("combobox", { name: "创建方式", exact: true })
    .selectOption(mode);
  await page.getByRole("textbox", { name: "学习目标", exact: true }).fill(objective);
  await page
    .getByRole("combobox", { name: "输出语言", exact: true })
    .selectOption("zh-CN");
  if (mode === "document") {
    const pdf = await page.request.get(`${api}/__acceptance__/textbook.pdf`);
    expect(pdf.ok()).toBe(true);
    await page.locator('input[type="file"]').setInputFiles({
      name: "manual-python-loops.pdf",
      mimeType: "application/pdf",
      buffer: await pdf.body(),
    });
  }
  const button = page.getByRole("button", {
    name: mode === "document" ? "生成计划" : "按目标生成",
    exact: true,
  });
  await expect(button).toBeEnabled();
  const response = page.waitForResponse(
    (response) =>
      response.url().endsWith("/learning-plans/stream") &&
      response.request().method() === "POST",
  );
  await button.click();
  expect((await response).ok()).toBe(true);
  await expect(page.getByRole("button", { name: /^开始第 1 课：/ })).toBeEnabled({
    timeout: 30_000,
  });
  const plan = (await read(page, "/learning-plans")).items.find(
    (item: { objective: string }) => item.objective === objective,
  );
  expect(plan).toBeTruthy();
  await page.reload();
  await expect(page.getByRole("button", { name: /^开始第 1 课：/ })).toBeEnabled();
  return plan;
}

async function startAndAsk(page: Page, planId: string, message: string) {
  await page.getByRole("button", { name: /^开始第 1 课：/ }).click();
  await expect(page).toHaveURL(/\/study/);
  const composer = page.getByRole("textbox", { name: /^向.*提问$/ });
  await expect(composer).toBeEnabled();
  const sent = page.waitForResponse(
    (response) =>
      /\/study-sessions\/[^/]+\/chat$/.test(response.url()) &&
      response.request().method() === "POST" &&
      response.request().postDataJSON().message_kind === "learner",
  );
  await composer.fill(message);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  const response = await sent;
  expect(response.ok()).toBe(true);
  const sessionId = response.url().split("/").at(-2)!;
  await expect(page.getByText(message, { exact: true })).toBeVisible();
  await expect(page.getByText(/我们先确认核心概念和成立条件/).first()).toBeVisible();
  await page.reload();
  await expect(page.getByText(message, { exact: true })).toBeVisible();
  const session = await read(page, `/study-sessions/${sessionId}`);
  expect(session.plan_id).toBe(planId);
  expect(JSON.stringify(session.turns)).toContain(message);
  return session;
}

test("02 goal-only Plan starts a Study Session; learner question and mock answer persist", async ({
  page,
}, info) => {
  const plan = await generatePlan(page, "goal_only", goal);
  const session = await startAndAsk(page, plan.id, "for 循环怎样遍历三个数字？");
  await expect(
    page.getByText("当前计划未关联教材，可直接围绕章节目标展开对话。", { exact: true }),
  ).toBeVisible();
  await page.screenshot({
    path: "/tmp/vibe-manual-acceptance/goal-study.png",
    fullPage: true,
  });
  await evidence(info, "goal-only-plan-study.json", { plan, session });
});

test("03 a newly uploaded text PDF is parsed, planned and used in Study", async ({
  page,
}, info) => {
  const plan = await generatePlan(
    page,
    "document",
    "根据教材比较 for 与 while 循环，分三天学习，每天 30 分钟",
  );
  const documents = (await read(page, "/documents")).items;
  const document = documents.find(
    (item: { id: string }) => item.id === plan.document_id,
  );
  expect(document).toBeTruthy();
  expect(document.status).toBe("processed");
  expect(document.page_count).toBe(3);
  const session = await startAndAsk(
    page,
    plan.id,
    "教材中 while 循环的停止条件是什么？",
  );
  expect(session.document_id).toBe(document.id);
  await page.screenshot({
    path: "/tmp/vibe-manual-acceptance/textbook-study.png",
    fullPage: true,
  });
  await evidence(info, "textbook-plan-study.json", { document, plan, session });
});

test("04 user-authored Persona and Scene save, reload and are selected in a new Tavern Room", async ({
  page,
}, info) => {
  await page.goto("/manual");
  await page
    .locator("#characters")
    .getByRole("link", { name: "人格色谱", exact: true })
    .click();
  await page.getByRole("button", { name: "新建人格草稿", exact: true }).click();
  await page.getByRole("textbox", { name: "名称", exact: true }).fill(personaName);
  await page
    .getByRole("textbox", { name: "摘要", exact: true })
    .fill("用简短例子解释 Python 循环的学习伙伴。");
  await page
    .getByRole("textbox", { name: "关系", exact: true })
    .fill("一起练习编程的学伴");
  const savedPersona = page.waitForResponse(
    (response) =>
      response.url() === `${api}/personas` && response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "创建人格", exact: true }).click();
  const personaResponse = await savedPersona;
  expect(personaResponse.ok()).toBe(true);
  const createdPersona = await personaResponse.json();
  await expect(
    page.getByRole("button", { name: "更新人格", exact: true }),
  ).toBeEnabled();
  await page.reload();
  await page
    .getByRole("combobox", { name: "人格", exact: true })
    .selectOption(createdPersona.id);
  await expect(page.getByRole("textbox", { name: "名称", exact: true })).toHaveValue(
    personaName,
  );
  const persona = (await read(page, "/personas")).items.find(
    (item: { id: string }) => item.id === createdPersona.id,
  );
  expect(persona).toBeTruthy();

  await page.goto("/manual");
  await page
    .locator("#characters")
    .getByRole("link", { name: "场景搭建", exact: true })
    .click();
  await page.getByRole("textbox", { name: "场景名称", exact: true }).fill(sceneName);
  await page
    .getByRole("textbox", { name: "场景摘要", exact: true })
    .fill("有白板与练习桌的安静编程自习室。");
  await page
    .getByRole("textbox", { name: "层级名称", exact: true })
    .fill("手册验收校园");
  await page.getByRole("button", { name: "添加子层", exact: true }).first().click();
  await page.getByRole("textbox", { name: "层级名称", exact: true }).fill("循环练习室");
  await page.getByRole("button", { name: "添加物体", exact: true }).first().click();
  await page
    .getByRole("textbox", { name: "物体名称", exact: true })
    .fill("循环演示白板");
  const savedScene = page.waitForResponse(
    (response) =>
      response.url() === `${api}/scene-library` &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "保存到场景库", exact: true }).click();
  expect((await savedScene).ok()).toBe(true);
  const scene = (await read(page, "/scene-library")).items.find(
    (item: { scene_name: string }) => item.scene_name === sceneName,
  );
  expect(scene).toBeTruthy();
  expect(JSON.stringify(scene)).toContain("循环演示白板");
  await page.reload();
  await expect(
    page.getByRole("textbox", { name: "场景名称", exact: true }),
  ).toHaveValue(sceneName);

  await page.goto("/manual");
  await page
    .locator("#tavern")
    .getByRole("link", { name: "角色酒馆", exact: true })
    .click();
  const setup = page.getByRole("region", { name: "创建房间", exact: true });
  await setup.getByRole("textbox", { name: "标题", exact: true }).fill("手册验收酒馆");
  for (const checkbox of await setup.getByRole("checkbox").all())
    await checkbox.uncheck();
  await setup.getByRole("checkbox", { name: new RegExp(personaName) }).check();
  await setup
    .getByRole("combobox", { name: "场景（可选）", exact: true })
    .selectOption(scene.scene_id);
  const createdRoom = page.waitForResponse(
    (response) =>
      response.url() === `${api}/tavern/rooms` &&
      response.request().method() === "POST",
  );
  await setup.getByRole("button", { name: "创建并进入", exact: true }).click();
  const roomResponse = await createdRoom;
  expect(roomResponse.ok()).toBe(true);
  const room = await roomResponse.json();
  const roomId = room.room?.id ?? room.id;
  const composer = page.getByRole("region", { name: "发起互动", exact: true });
  await composer
    .getByRole("textbox", { name: "你的消息", exact: true })
    .fill("一起解释一个 for 循环例子。");
  await composer.getByRole("button", { name: /发送并回应/ }).click();
  await expect
    .poll(async () => {
      const detail = await read(page, `/tavern/rooms/${roomId}`);
      return detail.messages.filter(
        (item: { author_kind: string }) => item.author_kind === "persona",
      ).length;
    })
    .toBe(1);
  await page.reload();
  await expect(
    page.getByText("一起解释一个 for 循环例子。", { exact: true }),
  ).toBeVisible();
  const detail = await read(page, `/tavern/rooms/${roomId}`);
  expect(JSON.stringify(detail)).toContain(personaName);
  expect(JSON.stringify(detail)).toContain(sceneName);
  const sessionsBeforeArchive = (await read(page, "/study-sessions")).items.length;
  await page.getByRole("button", { name: "归档", exact: true }).click();
  await expect(
    page.getByRole("button", { name: "恢复使用", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "恢复使用", exact: true }).click();
  await expect(page.getByRole("button", { name: "归档", exact: true })).toBeVisible();
  expect((await read(page, "/study-sessions")).items).toHaveLength(
    sessionsBeforeArchive,
  );
  await evidence(info, "persona-scene-tavern.json", { persona, scene, detail });
  await assertTavernGeometry(page, info, "before-screenshot");
  await page.screenshot({
    path: "/tmp/vibe-manual-acceptance/tavern.png",
    fullPage: true,
  });
  await evidence(
    info,
    "tavern-geometry-after-fullpage-raw.json",
    await tavernGeometry(page),
  );
  await assertTavernGeometry(page, info, "after-fullpage-screenshot");
  await page.screenshot({
    path: "/tmp/vibe-manual-acceptance/tavern-viewport.png",
    fullPage: false,
  });
  await evidence(
    info,
    "tavern-geometry-after-viewport-screenshot.json",
    await tavernGeometry(page),
  );
  await assertTavernGeometry(page, info, "after-viewport-screenshot");
  await assertTavernGeometry(page, info, "before-fullpage-disabled");
  await page.screenshot({
    path: "/tmp/vibe-manual-acceptance/tavern-fullpage-disabled.png",
    fullPage: true,
    animations: "disabled",
  });
  await evidence(
    info,
    "tavern-geometry-after-fullpage-disabled-raw.json",
    await tavernGeometry(page),
  );
  await assertTavernGeometry(page, info, "after-fullpage-disabled");
});

test("05 lost committed Study reply is recovered by original identity GET after reload, without replay", async ({
  page,
  context,
}, info) => {
  const plan = (await read(page, "/learning-plans")).items.find(
    (item: { objective: string }) => item.objective === goal,
  );
  expect(plan).toBeTruthy();
  await page.goto(`/study?plan=${encodeURIComponent(plan.id)}`);
  const composer = page.getByRole("textbox", { name: /^向.*提问$/ });
  await expect(composer).toBeEnabled();
  const writes: string[] = [];
  const reads: string[] = [];
  let loseReply = true;
  let hideRecovery = true;
  let committed: unknown;
  await page.route(`${api}/study-sessions/*/chat-operations/*`, async (route) => {
    reads.push(route.request().url());
    if (hideRecovery) await route.abort("connectionreset");
    else await route.continue();
  });
  await page.route(`${api}/study-sessions/*/chat`, async (route) => {
    const body = route.request().postDataJSON();
    if (body.message_kind !== "learner") return route.continue();
    writes.push(body.client_request_id);
    if (!loseReply) return route.continue();
    loseReply = false;
    const response = await route.fetch();
    expect(response.ok()).toBe(true);
    committed = await response.json();
    await route.abort("connectionreset");
  });
  const message = "这个已提交但响应丢失的问题只应发送一次。";
  await composer.fill(message);
  await page.getByRole("button", { name: "发送", exact: true }).click();
  await expect
    .poll(async () => page.evaluate((key) => localStorage.getItem(key), pendingKey))
    .not.toBeNull();
  await expect.poll(() => committed).toBeTruthy();
  const identity = await page.evaluate(
    (key) => JSON.parse(localStorage.getItem(key)!),
    pendingKey,
  );
  expect(writes).toEqual([identity.clientRequestId]);
  const endpoint = `/study-sessions/${identity.sessionId}/chat-operations/${identity.clientRequestId}`;
  expect((await read(page, endpoint)).status).toBe("committed");
  await context.setOffline(true);
  await expect(page.getByText(/浏览器当前离线，无法确认请求结果/)).toBeVisible();
  hideRecovery = false;
  await context.setOffline(false);
  await page.reload();
  await expect(page.getByText(message, { exact: true })).toBeVisible();
  await expect
    .poll(async () => page.evaluate((key) => localStorage.getItem(key), pendingKey))
    .toBeNull();
  expect(writes).toEqual([identity.clientRequestId]);
  expect(reads.length).toBeGreaterThan(0);
  expect(reads.every((url) => url.endsWith(endpoint))).toBe(true);
  const backend = await read(page, "/__acceptance__/evidence");
  expect(
    backend.study_calls.filter((call: { message: string }) => call.message === message),
  ).toHaveLength(1);
  await evidence(info, "lost-response-read-only-recovery.json", {
    identity,
    writes,
    reads,
    receipt: await read(page, endpoint),
    backend,
  });
});

test("06 recovery, data retention and installer SHA instructions are readable and bounded", async ({
  page,
}, info) => {
  await page.goto("/manual");
  await expect(page.locator("#recovery")).toContainText("结果未确认前不要重发");
  await expect(page.locator("#recovery")).toContainText("不能据此判断服务端已停止");
  await expect(page.locator("#data")).toContainText("services/ai/data/");
  await expect(page.locator("#data")).toContainText("ai-data");
  await expect(page.locator("#data")).toContainText("Vault");
  await expect(page.locator("#data")).toContainText("归档不等于删除");
  await expect(page.locator("#data")).toContainText("清除站点数据可能丢失草稿");
  await expect(page.locator("#start")).toContainText(
    "设置会自动保存，确认“已保存”后继续",
  );
  await expect(page.locator("#start")).toContainText("点击“开始”");
  await expect(page.locator("#study")).toContainText("64 MiB、512");
  await expect(page.locator("#characters")).toContainText("内置人格只读");
  await expect(page.locator("#data")).toContainText(
    "网页版连接远程后端时数据在远程机器",
  );
  await expect(page.locator("#data")).toContainText("备份需同时覆盖数据库和文件目录");
  await expect(
    page.locator("#install").getByRole("link", { name: "项目发布页", exact: true }),
  ).toHaveAttribute("href", "https://github.com/FrightenedFoxCN/vibe-learner/releases");
  await expect(page.locator("#install")).toContainText("SHA256SUMS.txt");
  await page.getByText("如何计算 SHA-256", { exact: true }).click();
  for (const command of [
    'shasum -a 256 "安装包.dmg"',
    'Get-FileHash "安装包.exe" -Algorithm SHA256',
    'sha256sum "安装包.AppImage"',
  ]) {
    await expect(page.locator("#install")).toContainText(command);
  }
  await expect(page.locator("#install")).toContainText("临时签名不等于正式公证");
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),
  ).toBe(true);
  await page.screenshot({
    path: "/tmp/vibe-manual-acceptance/manual-mobile.png",
    fullPage: true,
  });
  await evidence(info, "documentation-scope.json", {
    verified: [
      "manual navigation",
      "default storage implementation",
      "retention wording",
      "SHA command syntax",
      "390px manual layout",
    ],
    notCovered: [
      "real providers",
      "scanned PDF OCR",
      "native Vault",
      "DMG/NSIS/AppImage installation",
      "downloaded release asset SHA verification",
      "interactive grading (default mock emits no question)",
    ],
  });
});
