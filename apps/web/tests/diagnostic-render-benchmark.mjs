// Opt-in browser measurement of the actual production React timeline and decoder.
import { build } from 'esbuild';
import { chromium } from '@playwright/test';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import os from 'node:os';

const output = process.argv[2];
if (!output) throw new Error('usage: node tests/diagnostic-render-benchmark.mjs OUTPUT.json');
const rich = process.argv.includes('--rich');
const root = fileURLToPath(new URL('../', import.meta.url));
const fixture = JSON.parse(await readFile(new URL('../../../packages/shared/fixtures/diagnostics/query-pages-v1.json', import.meta.url), 'utf8'));
if (rich) fixture.events.items[0].event = JSON.parse(await readFile(new URL('./fixtures/diagnostic-render-rich-event.json', import.meta.url), 'utf8'));
const bundle = await build({
  stdin: { contents: `import React from 'react'; import {createRoot} from 'react-dom/client';
    import {DiagnosticTimeline} from './components/diagnostic-timeline';
    let root; window.mountTimeline=()=>{root=createRoot(document.getElementById('root'));root.render(React.createElement(DiagnosticTimeline));};
    window.unmountTimeline=()=>root.unmount();`, resolveDir: root, loader: 'tsx' },
  bundle: true, write: false, platform: 'browser', minify: true, jsx: 'automatic',
  define: { 'process.env.NODE_ENV': '"production"', 'process.env.NEXT_PUBLIC_AI_BASE_URL': '"https://diagnostic.test"' }, metafile: true,
});
// Budgets are declared before sampling. Each includes up to two 60-Hz frames.
const budgets = { initial_100_rows_ms: 150, append_to_500_rows_ms: 150, expand_row_ms: 100, unmount_500_rows_ms: 100 };
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('https://diagnostic.test/**', route => route.fulfill({ contentType: 'text/html', body: `<!doctype html><meta charset="utf-8"><title>Timeline benchmark</title><style>body{font:14px system-ui}#root{width:560px;height:720px;overflow:auto;--border:#ccc;--bg:white}*{box-sizing:border-box}</style><div id="root"></div>` }));
  await page.goto('https://diagnostic.test/');
  await page.evaluate(({fixture, rich}) => {
    window.benchmarkPageBytes = 0;
    window.fetch = async url => {
      const parsed = new URL(url);
      if (!parsed.pathname.endsWith('/diagnostics/events')) throw new Error('unexpected-query');
      const after = Number(parsed.searchParams.get('after') || 0);
      const result = structuredClone(fixture.events);
      result.items = Array.from({ length: 100 }, (_, i) => {
        const sequence = after + i + 1;
        return { sequence, event: { ...structuredClone(result.items[0].event),
          event_id: `benchmark-event-${sequence}`, request_id: `benchmark-request-${sequence}`,
          client_instance_id: 'synthetic-client', page_view_id: 'synthetic-page',
          flow_id: 'synthetic-flow', action_id: `synthetic-action-${sequence}`,
          span_id: `synthetic-span-${sequence}`, page_path: '/study', duration_ms: 10,
          status_code: 200, method: 'POST', route: '/study-sessions/{session_id}/chat' } };
      });
      result.next_cursor = after + 100;
      result.has_more = true; // UI must enforce the cap even if the server has more.
      result.retention.retained_events = 10000;
      result.retention.retained_payload_bytes = 10000000;
      if (rich) {
        // Fill the pattern-valid synthetic manifest label to approach the query
        // transport ceiling and decoder 4096-character fallback; this is
        // schema stress, not a registered tool.
        const available = 2 * 1024 * 1024 - 4096 - new TextEncoder().encode(JSON.stringify(result)).length;
        if (available < 0) throw new Error('fixture-over-budget');
        const padding = 'x'.repeat(Math.min(Math.floor(available / 100), 4096 - result.items[0].event.tool_metric.manifest_key.length));
        for (const item of result.items) item.event.tool_metric.manifest_key += padding;
      }
      window.benchmarkPageBytes = Math.max(window.benchmarkPageBytes, new TextEncoder().encode(JSON.stringify(result)).length);
      return Response.json(result);
    };
  }, {fixture, rich});
  await page.addScriptTag({ content: bundle.outputFiles[0].text });
  if (errors.length) throw new Error(`bundle-errors: ${JSON.stringify(errors)}`);
  const raw = await page.evaluate(async () => {
    const frame = () => new Promise(resolve => requestAnimationFrame(resolve));
    const ready = async predicate => {
      const deadline = performance.now() + 5000;
      while (!predicate()) {
        if (performance.now() > deadline) throw new Error('render-timeout');
        await frame();
      }
      // Layout plus two animation boundaries: a paint opportunity, not GPU proof.
      document.getElementById('root').getBoundingClientRect();
      await frame(); await frame();
    };
    const button = text => [...document.querySelectorAll('button')].find(item => item.textContent === text);
    const rows = () => document.querySelectorAll('article').length;
    const raw = { initial_100_rows_ms: [], append_to_500_rows_ms: [], expand_row_ms: [], unmount_500_rows_ms: [] };
    for (let sample = 0; sample < 33; sample++) {
      let started = performance.now();
      window.mountTimeline();
      await ready(() => rows() === 100 && button('刷新诊断')?.disabled === false);
      const initial = performance.now() - started;
      let append;
      for (let count = 200; count <= 500; count += 100) {
        started = performance.now();
        button('读取下一页事件').click();
        await ready(() => rows() === count && button('刷新诊断')?.disabled === false);
        append = performance.now() - started;
      }
      if (!button('读取下一页事件').disabled) throw new Error('capacity-not-enforced');
      if (!document.body.textContent.includes('已显示 500 条事件')) throw new Error('capacity-message');
      started = performance.now();
      const detail = document.querySelector('article details');
      detail.querySelector('summary').click();
      await ready(() => detail.open);
      const expand = performance.now() - started;
      started = performance.now();
      window.unmountTimeline();
      await ready(() => document.getElementById('root').childElementCount === 0);
      const unmount = performance.now() - started;
      if (sample >= 3) {
        raw.initial_100_rows_ms.push(initial);
        raw.append_to_500_rows_ms.push(append);
        raw.expand_row_ms.push(expand);
        raw.unmount_500_rows_ms.push(unmount);
      }
    }
    return raw;
  });
  if (errors.length) throw new Error(`browser-errors: ${JSON.stringify(errors)}`);
  const summary = Object.fromEntries(Object.entries(raw).map(([key, values]) => {
    const sorted = [...values].sort((a, b) => a - b);
    return [key, { count: sorted.length, p50: sorted[Math.ceil(sorted.length * .5) - 1], p95: sorted[Math.ceil(sorted.length * .95) - 1], max: sorted.at(-1), budget_ms: budgets[key], passed: sorted[Math.ceil(sorted.length * .95) - 1] <= budgets[key] }];
  }));
  const report = { schema_version: 'diagnostic-react-render-benchmark-v1', timestamp: new Date().toISOString(),
    profile: rich ? 'wide-nested-bounded-label' : 'small-transport', response_page_bytes: await page.evaluate(() => window.benchmarkPageBytes),
    platform: `${os.platform()} ${os.arch()}`, browser: browser.version(), viewport: [1280, 900], panel: [560, 720], warmups: 3,
    bundle_sha256: createHash('sha256').update(bundle.outputFiles[0].contents).digest('hex'),
    bundled_inputs: Object.keys(bundle.metafile.inputs).sort(),
    scope: 'Production React timeline, strict query decoder, pagination and layout in headless Chromium; synthetic 100-row response pages; backend/network, Next shell, native WebView and GPU completion excluded.',
    gate_rationale: 'P95 mount/page append below 150 ms, local expansion/unmount below 100 ms, including two frame boundaries; budget leaves headroom within a 200 ms interactive response target. Not a universal platform SLO.',
    capacity_verified: 500, passed: Object.values(summary).every(value => value.passed), summary, raw };
  await writeFile(output, JSON.stringify(report, null, 2) + '\n');
  if (!report.passed) throw new Error('render-budget-exceeded');
} finally { await browser.close(); }
