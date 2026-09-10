import { installSyntheticFetch, measureTimeline } from './diagnostic-render-harness.mjs';
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
  await page.evaluate(installSyntheticFetch, {fixture, rich});
  await page.addScriptTag({ content: bundle.outputFiles[0].text });
  if (errors.length) throw new Error(`bundle-errors: ${JSON.stringify(errors)}`);
  const raw = await page.evaluate(measureTimeline);
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
