import { test, expect } from "@playwright/test";
import { observeRequests } from "./api-fixture";
const routes = [
  ["/", "学习"], ["/plan", "学习"], ["/study", "学习"],
  ["/tavern", "角色与世界"], ["/persona-spectrum", "角色与世界"], ["/scene-setup", "角色与世界"], ["/sensory-tools", "角色与世界"],
  ["/settings", "系统"], ["/model-usage", "系统"], ["/manual", "系统"],
];
for (const width of [390,760,1440]) {
  test(`independent navigation: all ten entries and current semantics at ${width}px`, async ({ page }, info) => {
    await page.setViewportSize({width,height:844}); await observeRequests(page);
    const errors:string[]=[]; page.on("pageerror",e=>errors.push(e.message));
    const evidence:any[]=[];
    for (const [path,group] of routes) {
      await page.goto(path); await page.waitForLoadState("networkidle");
      const aside=page.getByRole("complementary",{name:"Primary navigation"});
      const nav=aside.getByRole("navigation",{name:"主要导航"});
      if(width<=760) {
        const toggle=aside.getByRole("button",{name:/全部导航/});
        await expect(toggle).toHaveAttribute("aria-expanded","false");
        await expect(toggle).toContainText(group);
        await toggle.click(); await expect(toggle).toHaveAttribute("aria-expanded","true");
      }
      await expect(nav.getByRole("group")).toHaveCount(3);
      await expect(nav.getByRole("group",{name:`${group}，当前分组`,exact:true})).toBeVisible();
      const links=nav.getByRole("link"); await expect(links).toHaveCount(10);
      expect((await links.evaluateAll(els=>els.map(el=>el.getAttribute("href")))).sort()).toEqual(routes.map(r=>r[0]).sort());
      const current=nav.locator('[aria-current="page"]'); await expect(current).toHaveCount(1); await expect(current).toHaveAttribute("href",path);
      for(const link of await links.all()) await expect(link).toBeVisible();
      const layout=await nav.evaluate(el=>({width:el.clientWidth,scrollWidth:el.scrollWidth,links:[...el.querySelectorAll("a")].map(a=>({text:a.textContent,width:a.getBoundingClientRect().width,height:a.getBoundingClientRect().height,left:a.getBoundingClientRect().left,right:a.getBoundingClientRect().right}))}));
      expect(layout.scrollWidth).toBeLessThanOrEqual(layout.width);
      if(width<=760) expect(layout.links.every(l=>l.width>=44&&l.height>=44&&l.left>=0&&l.right<=width)).toBe(true);
      if(path === "/") {
        await links.first().focus();
        for(let i=0;i<10;i++) {
          await expect(links.nth(i)).toBeFocused();
          const bounds=await links.nth(i).boundingBox();
          expect(bounds!.y).toBeGreaterThanOrEqual(0); expect(bounds!.y+bounds!.height).toBeLessThanOrEqual(844);
          if(i<9) await page.keyboard.press("Tab");
        }
        for(let i=9;i>=0;i--) {
          await expect(links.nth(i)).toBeFocused();
          if(i>0) await page.keyboard.press("Shift+Tab");
        }
        if(width===390||width===1440) await page.screenshot({path:`/Users/ffox/vibe-learner/docs/acceptance/navigation-${width}-2026-09-11.png`});
      }
      evidence.push({path,group,layout});
    }
    expect(errors).toEqual([]);
    await info.attach("navigation-layout.json",{body:JSON.stringify({width,evidence}),contentType:"application/json"});
  });
}

test("independent navigation: mobile Enter Escape and Tab-away preserve predictable focus", async ({page})=>{
  await page.setViewportSize({width:390,height:844}); await observeRequests(page); await page.goto("/plan");
  const aside=page.getByRole("complementary",{name:"Primary navigation"});
  const toggle=aside.getByRole("button",{name:/全部导航/}); const nav=aside.getByRole("navigation",{name:"主要导航"});
  await toggle.focus(); await page.keyboard.press("Enter"); await page.keyboard.press("Tab");
  await expect(nav.getByRole("link").first()).toBeFocused();
  await page.keyboard.press("Escape"); await expect(toggle).toBeFocused(); await expect(toggle).toHaveAttribute("aria-expanded","false");
  await page.keyboard.press("Enter"); await nav.getByRole("link").last().focus(); await page.keyboard.press("Tab");
  await expect(toggle).toHaveAttribute("aria-expanded","false");
  expect(await aside.evaluate(el=>el.contains(document.activeElement))).toBe(false);
});

test("independent navigation: collapsed desktop survives mobile boundary without hiding labels or losing focus",async({page})=>{
  await page.setViewportSize({width:1440,height:844}); await observeRequests(page); await page.goto("/study");
  const aside=page.getByRole("complementary",{name:"Primary navigation"});
  await aside.getByRole("button",{name:"Collapse navigation",exact:true}).click();
  const current=aside.locator('[aria-current="page"]'); await current.focus();
  await page.setViewportSize({width:760,height:844});
  const toggle=aside.getByRole("button",{name:/全部导航/}); await expect(toggle).toBeFocused();
  await toggle.click(); await expect(aside.locator(".app-nav-label").filter({hasText:"章节对话"})).toBeVisible();
  await page.keyboard.press("Escape"); await expect(toggle).toBeFocused();
  await page.setViewportSize({width:761,height:844}); await expect(current).toBeFocused();
  await expect(aside.getByRole("button",{name:"Expand navigation",exact:true})).toBeVisible();
  await expect(toggle).toBeHidden();
});

test("independent navigation: browser history updates page and group while mobile menu closes",async({page})=>{
  await page.setViewportSize({width:390,height:844}); await observeRequests(page); await page.goto("/plan");
  const aside=page.getByRole("complementary",{name:"Primary navigation"}); const toggle=aside.getByRole("button",{name:/全部导航/});
  await toggle.click(); await aside.locator('a[href="/scene-setup"]').click(); await expect(page).toHaveURL(/\/scene-setup$/);
  await expect(toggle).toHaveAttribute("aria-expanded","false"); await expect(toggle).toContainText("角色与世界");
  await page.goBack(); await expect(page).toHaveURL(/\/plan$/); await expect(toggle).toContainText("学习");
  await page.goForward(); await expect(page).toHaveURL(/\/scene-setup$/); await expect(toggle).toContainText("角色与世界");
  await toggle.click(); await expect(aside.locator('[aria-current="page"]')).toHaveAttribute("href","/scene-setup");
});

test("independent navigation: unconfigured Vault exposes only Settings as actionable navigation",async({page})=>{
  await page.setViewportSize({width:390,height:844}); await observeRequests(page); await page.goto("/settings");
  await page.evaluate(()=>{
    Object.assign(window.__VIBE_LEARNER_DESKTOP_CONFIG__!,{isDesktop:true,vaultState:"unconfigured"});
    window.dispatchEvent(new Event("vibe-learner:desktop-vault-state-change"));
  });
  const aside=page.getByRole("complementary",{name:"Primary navigation"}); await aside.getByRole("button",{name:/全部导航/}).click();
  const nav=aside.getByRole("navigation",{name:"主要导航"}); await expect(nav.getByRole("link")).toHaveCount(1);
  await expect(nav.getByRole("link")).toHaveAttribute("href",/\/settings\/?$/);
  await expect(nav.locator('[aria-disabled="true"]')).toHaveCount(9);
  await nav.locator('[aria-disabled="true"]').first().click(); await expect(page).toHaveURL(/\/settings$/);
});

test("independent navigation: resize rescues focus from desktop collapse control",async({page})=>{
  await page.setViewportSize({width:1440,height:844}); await observeRequests(page); await page.goto("/plan");
  const aside=page.getByRole("complementary",{name:"Primary navigation"});
  await page.waitForLoadState("networkidle");
  await aside.getByRole("button",{name:"Collapse navigation",exact:true}).focus();
  await expect(aside.getByRole("button",{name:"Collapse navigation",exact:true})).toBeFocused();
  await page.setViewportSize({width:390,height:844});
  await expect(aside.getByRole("button",{name:/全部导航/})).toBeFocused();
});

test("independent navigation: external view toggle closes mobile menu without hidden focus",async({page})=>{
  await page.setViewportSize({width:390,height:844}); await observeRequests(page); await page.goto("/plan");
  const aside=page.getByRole("complementary",{name:"Primary navigation"}); const toggle=aside.getByRole("button",{name:/全部导航/});
  await toggle.click(); await aside.locator('a[href="/study"]').focus();
  await page.evaluate(()=>window.dispatchEvent(new Event("vibe:view:toggle-nav")));
  await expect(toggle).toHaveAttribute("aria-expanded","false"); await expect(toggle).toBeFocused();
});

test("independent navigation: resizing after intentional focus departure does not steal focus",async({page})=>{
  await page.setViewportSize({width:1440,height:844}); await observeRequests(page); await page.goto("/plan"); await page.waitForLoadState("networkidle");
  const aside=page.getByRole("complementary",{name:"Primary navigation"});
  await aside.getByRole("button",{name:"Collapse navigation",exact:true}).focus();
  const outside=page.getByRole("textbox",{name:"学习目标",exact:true}); await outside.focus();
  await page.setViewportSize({width:390,height:844}); await expect(outside).toBeFocused();
});
