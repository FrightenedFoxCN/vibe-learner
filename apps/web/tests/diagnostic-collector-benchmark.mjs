// Opt-in Chromium microbenchmark of the production collector (no app UI/network).
import { build } from 'esbuild';
import { chromium } from '@playwright/test';
import { createHash } from 'node:crypto';
import { readFile, writeFile } from 'node:fs/promises';
import { fileURLToPath } from 'node:url';
import os from 'node:os';

const output = process.argv[2];
if (!output) throw new Error('usage: node tests/diagnostic-collector-benchmark.mjs OUTPUT.json');
const entry = fileURLToPath(new URL('../lib/diagnostics.ts', import.meta.url));
const bundle = await build({ entryPoints: [entry], bundle: true, write: false, platform: 'browser', format: 'iife', globalName: 'collector', minify: true });
const browser = await chromium.launch();
try {
  const page = await browser.newPage();
  await page.route('https://diagnostic.test/**', route => route.fulfill({ contentType: 'text/html', body: '<!doctype html><title>Collector benchmark</title>' }));
  await page.goto('https://diagnostic.test/');
  await page.addScriptTag({ content: bundle.outputFiles[0].text });
  const raw = await page.evaluate(async () => {
    const c = window.collector;
    c.registerDiagnosticPage('/study');
    const emitPair = () => {
      const context = c.diagnosticContext(c.createDiagnosticId());
      c.emitDiagnostic('request_started', context, { request_id: null, duration_ms: null, status_code: null, method: 'POST' });
      c.emitDiagnostic('request_finished', context, { request_id: 'synthetic-request', duration_ms: 1, status_code: 200, method: 'POST' });
    };
    for (let index = 0; index < 1000; index++) emitPair();
    const collection = [], snapshots = [], flush = [];
    for (let sample = 0; sample < 60; sample++) {
      await new Promise(resolve => requestAnimationFrame(resolve));
      let start = performance.now();
      for (let index = 0; index < 100; index++) emitPair();
      collection.push(performance.now() - start);
      start = performance.now();
      for (let index = 0; index < 100; index++) c.diagnosticSnapshot();
      snapshots.push(performance.now() - start);
    }
    const overloaded = c.diagnosticSnapshot();
    const originalFetch = window.fetch;
    let uploaded = 0;
    window.fetch = async (_url, init) => {
      const items = JSON.parse(init.body).events;
      if (items.length !== 100) throw new Error('batch-size');
      uploaded += items.length;
      return Response.json({ dropped: 0 });
    };
    try {
      for (let sample = 0; sample < 30; sample++) {
        while (c.diagnosticSnapshot().pending < 1000) emitPair();
        const start = performance.now();
        for (let batch = 0; batch < 10; batch++) await c.flushDiagnostics('https://diagnostic.test');
        flush.push(performance.now() - start);
        if (c.diagnosticSnapshot().pending !== 0) throw new Error('not-drained');
      }
    } finally { window.fetch = originalFetch; }
    return { collection_200_events_ms: collection, snapshot_100_copies_ms: snapshots,
      flush_1000_events_mock_transport_ms: flush, retained_events: overloaded.events.length,
      pending_at_overload: overloaded.pending, observed_drops: overloaded.dropped, uploaded_events: uploaded };
  });
  if (raw.retained_events !== 1000 || raw.pending_at_overload !== 1000 || raw.observed_drops <= 0 || raw.uploaded_events !== 30000) throw new Error('collector-accounting');
  const summary = {};
  for (const key of ['collection_200_events_ms', 'snapshot_100_copies_ms', 'flush_1000_events_mock_transport_ms']) {
    const sorted = [...raw[key]].sort((a, b) => a - b);
    summary[key] = { count: sorted.length, p50: sorted[Math.ceil(sorted.length * .5) - 1], p95: sorted[Math.ceil(sorted.length * .95) - 1], max: sorted.at(-1) };
  }
  const report = { schema_version: 'diagnostic-chromium-collector-benchmark-v1', timestamp: new Date().toISOString(),
    platform: `${os.platform()} ${os.arch()}`, browser: browser.version(), source_sha256: createHash('sha256').update(await readFile(entry)).digest('hex'),
    bundle_sha256: createHash('sha256').update(bundle.outputFiles[0].contents).digest('hex'),
    scope: 'Production collector in headless Chromium; saturated ring; no React rendering, backend, network, Tauri or full-workflow timing.',
    gate: { budget_ms: 16.7, rationale: 'P95 collection of a 100-request/200-event synchronous burst within one 60 Hz frame; collection only.', passed: summary.collection_200_events_ms.p95 <= 16.7 }, summary, raw };
  await writeFile(output, JSON.stringify(report, null, 2) + '\n');
  if (!report.gate.passed) throw new Error('collector-frame-budget-exceeded');
} finally { await browser.close(); }
