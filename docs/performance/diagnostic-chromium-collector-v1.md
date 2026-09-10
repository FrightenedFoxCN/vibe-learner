# Chromium collector microbenchmark

The production `apps/web/lib/diagnostics.ts` module is bundled unchanged with
esbuild and executed in headless Chromium on an isolated secure-origin page.
The report records source/bundle SHA-256, browser/platform, all raw samples and
nearest-rank P50/P95. There is no React UI, backend or real network in this probe.

After 1,000 request-pair warmups, 60 samples each create 100 contexts/flows and
200 events into saturated 1,000-entry history/pending rings. Another 60 samples
copy the full snapshot 100 times. Thirty samples flush 1,000 queued events in ten
100-event batches, with a local fetch stub parsing JSON and returning an actual
Response object. Flush timing includes serialization/filtering but excludes network.
Retention, positive overflow drops and exactly 30,000 uploaded events are asserted.

The collection gate is P95 <= 16.7 ms for the 200-event synchronous burst: one
60 Hz frame's time budget for collection alone. It is not a full UI frame budget,
network or native acceptance gate. The observed P95 was 1.400 ms (max 1.800 ms).
Snapshot P95 was 0.400 ms per 100 copies; mock-transport flush P95 was 1.800 ms per
1,000 events. Timer quantization can produce zero samples; raw values are retained.

Reproduce from repository root:

```sh
node apps/web/tests/diagnostic-collector-benchmark.mjs /tmp/diagnostic-chromium-collector.json
```

[Raw report](diagnostic-chromium-collector-v1.json). This establishes local collector
cost under synthetic burst/overflow load. React rendering, complete user workflows,
Tauri/Stronghold/native spool overhead and other platforms remain separate gates.
