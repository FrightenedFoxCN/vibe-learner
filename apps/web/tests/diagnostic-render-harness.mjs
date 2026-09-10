// Shared browser/native measurement functions; no production application hooks.
export function installSyntheticFetch({fixture, rich}) {
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

}

export async function measureTimeline() {
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

}
