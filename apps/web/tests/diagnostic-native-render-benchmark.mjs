// Opt-in actual Tauri/WKWebView host using the same React/decoder harness as Chromium.
import { build } from 'esbuild';
import { createServer } from 'node:http';
import { spawn } from 'node:child_process';
import { createHash, randomUUID } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import os from 'node:os';
import { installSyntheticFetch, measureTimeline } from './diagnostic-render-harness.mjs';
const output = process.argv[2];
if (!output) throw new Error('output path required');
const rich = process.argv.includes('--rich');
const root = fileURLToPath(new URL('../', import.meta.url));
const binary = fileURLToPath(new URL('../../desktop/src-tauri/target/debug/examples/diagnostic_render', import.meta.url));
const fixture = JSON.parse(await readFile(new URL('../../../packages/shared/fixtures/diagnostics/query-pages-v1.json', import.meta.url), 'utf8'));
if (rich) fixture.events.items[0].event = JSON.parse(await readFile(new URL('./fixtures/diagnostic-render-rich-event.json', import.meta.url), 'utf8'));
const bundle = await build({stdin:{contents:`import React from 'react'; import {createRoot} from 'react-dom/client';
import {DiagnosticTimeline} from './components/diagnostic-timeline'; let root;
window.mountTimeline=()=>{root=createRoot(document.getElementById('root'));root.render(React.createElement(DiagnosticTimeline));};
window.unmountTimeline=()=>root.unmount();`,resolveDir:root,loader:'tsx'},bundle:true,write:false,platform:'browser',minify:true,jsx:'automatic',define:{'process.env.NODE_ENV':'"production"','process.env.NEXT_PUBLIC_AI_BASE_URL':'"https://diagnostic.test"'},metafile:true});
const budgets = {initial_100_rows_ms:150,append_to_500_rows_ms:150,expand_row_ms:100,unmount_500_rows_ms:100};
const token = randomUUID();
let resolveResult, rejectResult, child, timer;
const result = new Promise((resolve,reject)=>{resolveResult=resolve;rejectResult=reject;});
const errors = [];
const runScript = `const nativeFetch=window.fetch.bind(window); const errors=[];
addEventListener('error',e=>errors.push(e.message)); addEventListener('unhandledrejection',e=>errors.push(String(e.reason)));
(${installSyntheticFetch.toString()})(${JSON.stringify({fixture,rich})});
(async()=>{try {const raw=await (${measureTimeline.toString()})();
await nativeFetch('/${token}/result',{method:'POST',body:JSON.stringify({raw,errors,user_agent:navigator.userAgent,page_bytes:window.benchmarkPageBytes,viewport:[innerWidth,innerHeight],visibility:document.visibilityState})});
} catch(e) {await nativeFetch('/${token}/result',{method:'POST',body:JSON.stringify({error:String(e),errors})});}})();`;
const server=createServer(async(req,res)=>{
 if(req.url===`/${token}/` && req.method==='GET') {res.setHeader('Content-Type','text/html; charset=utf-8');res.end(`<!doctype html><meta charset="utf-8"><title>Native timeline benchmark</title><style>body{font:14px system-ui}#root{width:560px;height:720px;overflow:auto;--border:#ccc;--bg:white}*{box-sizing:border-box}</style><div id="root"></div><script src="bundle.js"></script><script src="run.js"></script>`);}
 else if(req.url===`/${token}/bundle.js`) {res.setHeader('Content-Type','text/javascript');res.end(bundle.outputFiles[0].text);}
 else if(req.url===`/${token}/run.js`) {res.setHeader('Content-Type','text/javascript');res.end(runScript);}
 else if(req.url===`/${token}/result` && req.method==='POST') {
  try {let body='';for await(const part of req){body+=part;if(body.length>1024*1024)throw new Error('report-too-large');} const data=JSON.parse(body);res.end('ok');resolveResult(data);}catch(e){res.writeHead(400).end();rejectResult(e);}
 } else res.writeHead(404).end();
});
try {
 await new Promise(resolve=>server.listen(0,'127.0.0.1',resolve));
 child=spawn(binary,[`http://127.0.0.1:${server.address().port}/${token}/`],{stdio:['ignore','ignore','pipe']});
 child.stderr.on('data',data=>{if(errors.length<20)errors.push(String(data).slice(0,2000));});
 child.once('error',rejectResult);child.once('exit',code=>rejectResult(new Error(`native-host-exited:${code}`)));
 timer=setTimeout(()=>rejectResult(new Error('native-render-timeout')),60000);
 const observation=await result;
 if(observation.error || observation.errors.length)throw new Error(JSON.stringify(observation));
 if(observation.visibility!=='visible')throw new Error('native-window-not-visible');
 const summary=Object.fromEntries(Object.entries(budgets).map(([key,budget])=>{
  const values=observation.raw[key];if(values?.length!==30 || values.some(v=>!Number.isFinite(v)||v<0))throw new Error('invalid-sample');
  const sorted=[...values].sort((a,b)=>a-b);return [key,{count:30,p50:sorted[14],p95:sorted[28],max:sorted[29],budget_ms:budget,passed:sorted[28]<=budget}];
 }));
 const report={schema_version:'diagnostic-native-webview-render-v1',timestamp:new Date().toISOString(),platform:`${os.platform()} ${os.arch()}`,profile:rich?'wide-nested-bounded-label':'small-transport',...observation,summary,passed:Object.values(summary).every(v=>v.passed),warmups:3,panel:[560,720],capacity_verified:500,bundle_sha256:createHash('sha256').update(bundle.outputFiles[0].contents).digest('hex'),native_binary_sha256:createHash('sha256').update(await readFile(binary)).digest('hex'),bundled_inputs:Object.keys(bundle.metafile.inputs).sort(),scope:'Actual visible Tauri native WebView with production React timeline and strict decoder; synthetic local responses. No production shell/sidecar/Vault, network/provider latency or GPU completion claim.'};
 await writeFile(output,JSON.stringify(report,null,2)+'\n');
 if(!report.passed)throw new Error('native-render-budget-exceeded');
} finally {clearTimeout(timer);child?.kill('SIGTERM');server.closeAllConnections();await new Promise(resolve=>server.close(resolve));}
