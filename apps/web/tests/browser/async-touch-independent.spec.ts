import { test, expect } from "@playwright/test";
import { observeRequests } from "./api-fixture";
import { tavernFixture } from "./tavern-copy-fixture";
import { writeFileSync } from "node:fs";

for (const path of ["/persona-spectrum","/scene-setup","/sensory-tools","/tavern"]) {
  test(`independent async touch inventory ${path}`,async({page},info)=>{
    await page.setViewportSize({width:390,height:844}); await observeRequests(page); if(path==="/sensory-tools") await sensory(page);
    if(path==="/tavern") await tavernFixture(page,"partial"); else await page.goto(path); await page.waitForLoadState("networkidle");
    if(path==="/persona-spectrum") {const add=page.getByRole("button",{name:"添加",exact:true});if(await add.count())await add.first().click();}

    const items:any[]=[];
    for(const state of ["default","expanded"]) {
    if(state==="expanded"&&path==="/persona-spectrum") {
      await page.getByRole("button",{name:"附加系统约束（可选）",exact:true}).click();
      await page.getByRole("button",{name:"长文本提取",exact:true}).click();
      for(const name of ["卡片库","人格库"]){const b=page.getByRole("button",{name,exact:true});if(await b.getAttribute("aria-expanded")==="false")await b.click();}
      await page.getByRole("button",{name:"AI 重写",exact:true}).first().click();
    }
    if(state==="expanded"&&path==="/scene-setup"){
      await page.getByRole("button",{name:"添加物体",exact:true}).first().click();
      for(const name of ["可复用节点库","已保存场景"]){const b=page.getByRole("button",{name,exact:true});if(await b.getAttribute("aria-expanded")==="false")await b.click();}
      await page.getByRole("button",{name:"长文本提取",exact:true}).click();
      await page.getByRole("button",{name:/^AI 重写/}).first().click();
    }
    const controls=page.locator('main button, main input:not([type="hidden"]), main select, main textarea, main summary');
    for(const control of await controls.all()) {
      if(!await control.isVisible()) continue;
      const dimensions=await control.evaluate(el=>{
        const input=el as HTMLInputElement;
        const target=(input.type==="checkbox"||input.type==="radio") ? input.closest("label")??el : el;
        const r=target.getBoundingClientRect(); return {tag:el.tagName,type:input.type,text:(el.getAttribute("aria-label")||el.textContent||"").trim().slice(0,100),width:r.width,height:r.height,disabled:input.disabled};
      });
      const accessibility=await control.ariaSnapshot();
      items.push({state,...dimensions,accessibility});
      expect.soft(dimensions.width, `${path} ${accessibility} width`).toBeGreaterThanOrEqual(44);
      expect.soft(dimensions.height, `${path} ${accessibility} height`).toBeGreaterThanOrEqual(44);
      expect.soft(accessibility, `${path} accessible name`).toMatch(/(?:button|textbox|combobox|checkbox|radio|slider|spinbutton) \".+\"|text:/);
    }
    }
    const data={path,viewport:{width:390,height:844},items};
    writeFileSync(`/tmp/async-touch-${path.slice(1)}.json`,JSON.stringify(data,null,2));
    await page.screenshot({path:`/tmp/async-touch-${path.slice(1)}.png`,fullPage:true});
    await info.attach("touch-inventory.json",{body:JSON.stringify(data),contentType:"application/json"});
  });
}

const api="http://127.0.0.1:18999";
async function sensory(page:any) {
 const config={updated_at:"2026-09-11T00:00:00Z",stages:[{name:"study",label:"学习工具",description:"Independent populated fixture",stage_enabled:true,audit_basis:[],stage_disabled_reason:"",tools:[{name:"read",label:"独立阅读工具",description:"Read",category:"reading",category_label:"阅读",enabled:true,available:true,effective_enabled:true,audit_basis:[],unavailable_reason:""}]}]};
 await page.route(`${api}/model-tools/config`,(r:any)=>r.fulfill({json:config})); return config;
}
for(const kind of ["persona","scene","sensory","tavern"]){
 for(const outcome of (kind==="persona"?["success","failure","moved-focus","residual-error"]:["success","failure","moved-focus"])){
 test(`independent async ${kind} ${outcome}`,async({page})=>{
 await page.setViewportSize({width:390,height:844}); await observeRequests(page);
 const success=outcome==="success"||outcome==="residual-error";
 let release!:()=>void;const gate=new Promise<void>(r=>release=r);
 let savedPersona:any; let endpoint="";let trigger:any;let other:any;let config:any;
 if(kind==="tavern"){
  await tavernFixture(page,"partial");endpoint="/tavern/rooms/copy-room/turns";
  for(const box of await page.getByRole("region",{name:"角色与目标",exact:true}).getByRole("checkbox").all())await box.check();
  other=page.getByRole("textbox",{name:"你的消息",exact:true});await other.fill("Independent round");
  trigger=page.getByRole("button",{name:"发送并回应",exact:false});
 }else{
  if(kind==="sensory")config=await sensory(page);
  await page.goto(kind==="persona"?"/persona-spectrum":kind==="scene"?"/scene-setup":"/sensory-tools");
  if(kind==="persona"){
   await page.getByRole("button",{name:"新建人格草稿",exact:true}).click();other=page.getByRole("textbox",{name:"名称",exact:true});await other.fill("Independent async persona");
   trigger=page.getByRole("button",{name:"创建人格",exact:true});endpoint="/personas";
   if(outcome==="residual-error") {await page.getByRole("button",{name:"根据关键词生成人格卡片",exact:true}).click();await expect(page.getByRole("alert").filter({hasText:"请先输入关键词"})).toBeVisible();}
  }else if(kind==="scene"){
   trigger=page.getByRole("button",{name:"保存到场景库",exact:true});other=page.getByRole("textbox",{name:"场景生成关键词",exact:true});endpoint="/scene-library";
  }else {trigger=page.getByRole("checkbox",{name:"独立阅读工具",exact:true});other=page.getByRole("button",{name:"返回首页",exact:true});endpoint="/model-tools/config";}
 }
 await page.route(`${api}${endpoint}`,async route=>{
  if(route.request().method()==="GET")return kind==="persona"&&savedPersona?route.fulfill({json:{items:[savedPersona]}}):route.fallback();
  await gate;
  if(!success)return route.fulfill({status:500,json:{detail:"Independent asynchronous failure"}});
  if(kind==="tavern")return route.fallback();
  const body=route.request().postDataJSON();
  if(kind==="persona"){savedPersona={...body,id:"independent-persona",revision:1,source:"user"};return route.fulfill({json:savedPersona});}
  if(kind==="sensory"){config.stages[0].tools[0].enabled=false;config.stages[0].tools[0].effective_enabled=false;return route.fulfill({json:config});}
  const find=(nodes:any[],path:string[]=[]):any=>{for(const n of nodes){if(n.id===body.selected_layer_id)return {node:n,path:[...path,n.title]};const hit=find(n.children,[...path,n.title]);if(hit)return hit;}};
  const selected=find(body.scene_layers);
  const profile={scene_name:body.scene_name,summary:body.scene_summary,scene_id:body.selected_layer_id,title:selected.node.title,tags:typeof selected.node.tags==="string"?selected.node.tags.split(/[,，]/).map((v:string)=>v.trim()).filter(Boolean):selected.node.tags,selected_path:selected.path,focus_object_names:selected.node.objects.slice(0,4).map((o:any)=>o.name),scene_tree:body.scene_layers};
  return route.fulfill({json:{...body,scene_id:"independent-scene",config_id:"independent-scene",revision:1,scene_profile:profile,created_at:"2026-09-11T00:00:00Z",updated_at:"2026-09-11T00:00:00Z"}});
 });
 const sent=page.waitForRequest(r=>r.method()!=="GET"&&r.url()===`${api}${endpoint}`);
 await trigger.click();await sent;
 await expect(page.getByRole("status").filter({hasText:/正在|生成中|发送|保存|提交|请求已交给服务器/}).first()).toBeVisible();
 if(outcome==="moved-focus") {if(kind==="sensory"||kind==="tavern")other=page.getByRole('button',{name:/全部导航/});await other.focus();await expect(other).toBeFocused();}
 release();
 if(!success){
  const alert=page.getByRole("alert").filter({hasText:/失败|错误|无法|Independent|未完整返回/}).first();await expect(alert).toBeVisible();
  if(outcome==="failure"){await expect(alert).toBeFocused();await expect(alert).toBeInViewport();}
  else await expect(other).toBeFocused();
 }else if(kind==="persona"){
 await expect(page.getByRole("status").filter({hasText:"已创建人格"}).first()).toBeVisible();
 if(outcome==="residual-error")expect(await page.evaluate(()=>document.activeElement?.getAttribute("role"))).not.toBe("alert");
 }
 else if(kind==="scene")await expect(page.getByRole("status").filter({hasText:"已保存场景"})).toBeVisible();
 else if(kind==="sensory"){await expect(page.getByRole("status").filter({hasText:"工具配置已保存"})).toBeVisible();await expect(trigger).not.toBeChecked();}
 else await expect(page.getByText("Committed actor reply",{exact:true})).toBeVisible();
 });
 }
}

for(const kind of ["sensory","tavern"]){
 test(`independent background ${kind} failure preserves user focus`,async({page})=>{
  await page.setViewportSize({width:390,height:844});await observeRequests(page);
  let release!:()=>void;const gate=new Promise<void>(r=>release=r);
  await page.route(kind==="sensory"?`${api}/model-tools/config`:`${api}/tavern/rooms?*`,async route=>{await gate;await route.fulfill({status:500,json:{detail:"Independent background failure"}});});
  await page.goto(kind==="sensory"?"/sensory-tools":"/tavern");
  const nav=page.getByRole("button",{name:/全部导航/});await nav.focus();await expect(nav).toBeFocused();release();
  await expect(page.getByRole("alert").first()).toBeVisible();await expect(nav).toBeFocused();
 });
}
