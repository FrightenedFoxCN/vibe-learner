import { test, expect, type APIResponse } from "@playwright/test";
import { writeFileSync, readFileSync } from "node:fs";
import { cpus, platform, release, arch } from "node:os";
import { createHash } from "node:crypto";
import { execFileSync } from "node:child_process";

const api = process.env.TAVERN_PROFILE_API_URL;
test.skip(!api, "Requires the disposable 1000-room fixture and next build --profile with NEXT_PUBLIC_TAVERN_ROOM_PROFILING=1");
const positions = [{ name: "beginning", offset: 0 }, { name: "middle", offset: 450 }, { name: "end", offset: 940 }];
const percentile = (values: number[], p: number) => [...values].sort((a,b) => a-b)[Math.ceil(values.length * p) - 1];
test("independent Tavern room React append commits satisfy all three regional gates", async ({ browser, request }, info) => {
  test.setTimeout(600_000);
  const root = api!;
  const output = process.env.TAVERN_PROFILE_OUTPUT ?? "/tmp/tavern-room-react-profile.json";
  async function pageAt(offset: number) {
    let cursor: string | null = null;
    let consumed = 0;
    while (consumed < offset) {
      const response: APIResponse = await request.get(`${root}/tavern/rooms`, { params: { limit: Math.min(50, offset-consumed), ...(cursor ? { cursor } : {}) } });
      expect(response.ok()).toBe(true);
      const page: any = await response.json(); consumed += page.items.length; cursor = page.next_cursor;
      expect(page.items.length).toBeGreaterThan(0);
    }
    return cursor;
  }
  const report: any = { contract: "tavern-room-react-profiler-independent-v1", fixture_seed: "vibe-learner-tavern-1000-v1", fixture_contract: "tavern-room-list-fixture-v1",
    created_at: new Date().toISOString(), source_commit: execFileSync("git", ["rev-parse", "HEAD"], {encoding:"utf8"}).trim(),
    source_includes_uncommitted_instrumentation: true, source_hashes: Object.fromEntries(["components/tavern-workspace.tsx", "lib/tavern-workspace-state.ts", "next.config.mjs", "app/globals.css", "tests/browser/tavern-room-profile.spec.ts"].map(path => [path,createHash("sha256").update(readFileSync(path)).digest("hex")])),
    build_id: readFileSync(".next/BUILD_ID", "utf8").trim(), environment: { platform: platform(), os_release: release(), architecture: arch(), cpu: cpus()[0]?.model, logical_cpus: cpus().length, node: process.version, browser: browser.version(), viewport: {width:1440,height:1000}, cpu_throttling: "none" },
    selection: "Only actual React Profiler update callbacks with exact post-append 60 Room IDs; per trial take maximum actualDuration if multiple matching commits. All callbacks retained; mount/loading-only excluded. First API page alone starts at a real cursor; actual Load More fetch/appending path unchanged.", positions: [] };
  for (const position of positions) {
    const cursor = await pageAt(position.offset);
    const firstResponse = await request.get(`${root}/tavern/rooms`, { params: {limit:30, ...(cursor ? {cursor} : {})} });
    const first = await firstResponse.json();
    const second = await (await request.get(`${root}/tavern/rooms`, { params: {limit:30,cursor:first.next_cursor} })).json();
    expect(first.items).toHaveLength(30); expect(second.items).toHaveLength(30);
    const expectedIds = [...first.items, ...second.items].map(item => item.id);
    expect(new Set(expectedIds).size).toBe(60);
    const regional: any = { ...position, initial_cursor: cursor, initial_room_ids: first.items.map((item:any) => item.id), appended_room_ids: second.items.map((item:any) => item.id), trials: [] };
    for (let iteration = 0; iteration < 35; iteration++) {
      const context = await browser.newContext({ viewport: {width:1440,height:1000} });
      const page = await context.newPage();
      await page.addInitScript(root => { window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl: root, isDesktop:false, platform:"unknown", secretStorageMode:"plain_text",vaultState:"unconfigured",vaultPath:"",storageRoot:"",startupError:"" }; }, root);
      let firstList = true;
      const listRequests: string[] = [];
      await page.route(url => url.origin === root && url.pathname === "/tavern/rooms", async route => {
        let url = route.request().url();
        if (firstList) { firstList = false; const target = new URL(url); if (cursor) target.searchParams.set("cursor", cursor); url = target.toString(); }
        listRequests.push(url);
        const upstream = await route.fetch({ url }); await route.fulfill({ response: upstream });
      });
      await page.goto("/tavern"); await expect(page.getByText(/酒馆已就绪 · revision/)).toBeVisible(); await page.waitForLoadState("networkidle");
      const panel = page.getByRole("region", {name:"最近酒馆",exact:true});
      await expect(panel.locator("button.tavern-room-item")).toHaveCount(30);
      const before = await page.evaluate(() => ((window as any).__tavernRoomProfileSamples ?? []).length);
      expect(before).toBeGreaterThan(0);
      await panel.getByRole("button",{name:"载入更多房间",exact:false}).click();
      await expect(panel.locator("button.tavern-room-item")).toHaveCount(60);
      await page.waitForLoadState("networkidle");
      const commits: any[] = await page.evaluate(() => (window as any).__tavernRoomProfileSamples);
      const candidates = commits.slice(before).filter(s => s.phase !== "mount" && JSON.stringify(s.roomIds) === JSON.stringify(expectedIds));
      expect(candidates.length).toBeGreaterThan(0);
      expect(candidates.every(s => s.id === "TavernSessionPanel" && Number.isFinite(s.actualDuration) && s.actualDuration >= 0 && s.commitTime >= s.startTime)).toBe(true);
      expect(commits.every(s => s.roomIds.length <= 100)).toBe(true);
      const actual = Math.max(...candidates.map(s => s.actualDuration));
      regional.trials.push({ iteration, warmup: iteration < 5, actual_duration_ms: actual, rendered_room_buttons: await panel.locator("button.tavern-room-item").count(), api_list_requests: listRequests, candidates: candidates.length, all_commits: commits });
      await context.close();
    }
    const values = regional.trials.filter((t:any) => !t.warmup).map((t:any) => t.actual_duration_ms);
    regional.aggregate = { count: values.length, p50_ms: percentile(values,.5), p95_ms: percentile(values,.95), maximum_ms: Math.max(...values), threshold_ms:50 };
    report.positions.push(regional);
    writeFileSync(output, JSON.stringify(report,null,2));
  }
  const selectedId = report.positions[2].appended_room_ids.at(-1);
  const capContext = await browser.newContext({ viewport: {width:1440,height:1000} });
  const capPage = await capContext.newPage();
  await capPage.addInitScript(({root, selectedId}) => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl:root,isDesktop:false,platform:"unknown",secretStorageMode:"plain_text",vaultState:"unconfigured",vaultPath:"",storageRoot:"",startupError:"" };
    localStorage.setItem("vibe-learner:tavern:active-room",selectedId);
  }, {root,selectedId});
  await capPage.goto("/tavern"); await expect(capPage.getByText(/酒馆已就绪 · revision/)).toBeVisible(); await capPage.waitForLoadState("networkidle");
  const capPanel = capPage.getByRole("region", {name:"最近酒馆",exact:true});
  await expect(capPanel.locator("button.tavern-room-item")).toHaveCount(31);
  const domCounts = [31];
  for (const count of [61,91,100]) {
    await capPanel.getByRole("button",{name:"载入更多房间",exact:false}).click();
    await expect(capPanel.locator("button.tavern-room-item")).toHaveCount(count);
    domCounts.push(await capPanel.locator("button.tavern-room-item").count());
  }
  await expect(capPanel.getByText("已显示最近 100 个房间",{exact:true})).toBeVisible();
  await expect(capPanel.locator('button.tavern-room-item[aria-pressed="true"]')).toHaveCount(1);
  const capCommits: any[] = await capPage.evaluate(() => (window as any).__tavernRoomProfileSamples);
  expect(capCommits.every(s => s.roomIds.length <= 100)).toBe(true);
  expect(capCommits.at(-1).roomIds).toContain(selectedId);
  report.structural = {selected_outside_initial_page:selectedId,dom_counts:domCounts,maximum:Math.max(...domCounts),selected_retained:true,all_commits:capCommits};
  await capContext.close();
  report.passed = report.positions.every((p:any) => p.aggregate.count === 30 && p.aggregate.p95_ms <= 50);
  writeFileSync(output, JSON.stringify(report,null,2));
  await info.attach("react-profile-raw.json", {body:JSON.stringify(report),contentType:"application/json"});
  expect(report.passed).toBe(true);
});

test("independent Tavern room cap controls stop pagination at 100", async ({ page, request }, info) => {
  const root = api!;
  const raw = JSON.parse(readFileSync(process.env.TAVERN_PROFILE_OUTPUT ?? "/tmp/tavern-room-react-profile.json", "utf8"));
  const selectedId = raw.structural.selected_outside_initial_page;
  expect((await request.get(`${root}/tavern/rooms/${selectedId}?tail=true&limit=40`)).ok()).toBe(true);
  await page.addInitScript(({root,selectedId}) => {
    window.__VIBE_LEARNER_DESKTOP_CONFIG__ = { aiBaseUrl:root,isDesktop:false,platform:"unknown",secretStorageMode:"plain_text",vaultState:"unconfigured",vaultPath:"",storageRoot:"",startupError:"" };
    localStorage.setItem("vibe-learner:tavern:active-room",selectedId);
  },{root,selectedId});
  await page.goto("/tavern"); await expect(page.getByText(/酒馆已就绪 · revision/)).toBeVisible();
  const panel = page.getByRole("region",{name:"最近酒馆",exact:true});
  await expect(panel.locator("button.tavern-room-item")).toHaveCount(31);
  for (const count of [61,91,100]) {
    await panel.getByRole("button",{name:"载入更多房间",exact:false}).click();
    await expect(panel.locator("button.tavern-room-item")).toHaveCount(count);
  }
  await expect(panel.getByRole("button",{name:"载入更多房间",exact:false})).toHaveCount(0);
  await expect(panel.locator('button.tavern-room-item[aria-pressed="true"]')).toHaveCount(1);
  await info.attach("cap-control.json",{body:JSON.stringify({count:100,load_more_absent:true,selected_id:selectedId}),contentType:"application/json"});
});
