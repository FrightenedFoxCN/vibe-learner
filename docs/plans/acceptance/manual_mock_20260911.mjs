// Run only with the disposable server manual_mock_server_20260911.py and frontend port 3430.
import assert from 'node:assert/strict';
import { chromium } from '../../../node_modules/playwright/index.mjs';
const browser=await chromium.launch({headless:true});
try {
 const page=await browser.newPage();
 await page.addInitScript(()=>{window.__VIBE_LEARNER_DESKTOP_CONFIG__={aiBaseUrl:'http://127.0.0.1:19001',isDesktop:false,platform:'unknown',secretStorageMode:'plain_text',vaultState:'unconfigured',vaultPath:'',storageRoot:'',startupError:''};});
 await page.goto('http://127.0.0.1:3430/plan');
 console.log('INITIAL',await page.locator('body').innerText());
 await page.getByRole('combobox',{name:/创建方式/}).selectOption('goal_only');
 await page.getByRole('textbox',{name:'学习目标',exact:true}).fill('用一周掌握 Python 循环，每天 30 分钟');
 await page.getByRole('button',{name:'按目标生成',exact:true}).click();
 await page.getByText('目标计划已生成，会话已创建。',{exact:true}).waitFor();
 await page.locator('a[href="/study"]').first().click();
 const input=page.getByRole('textbox',{name:'向Aurora提问',exact:true});
 await input.fill('请用简单例子解释 for 循环');
 const response=page.waitForResponse(r=>r.request().method()==='POST' && r.url().endsWith('/chat'));
 await page.getByRole('button',{name:'发送',exact:true}).click();
 const reply=await response; assert.equal(reply.status(),200); console.log('CHAT_STATUS',reply.status());
 await page.getByText('请用简单例子解释 for 循环',{exact:true}).waitFor();
 await page.reload();
 await page.getByText('请用简单例子解释 for 循环',{exact:true}).waitFor();
 console.log((await page.locator('body').innerText()).slice(-18000));
} finally {await browser.close();}
