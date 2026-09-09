"""Read back only this acceptance's synthetic objects and content-free traces."""
import argparse
import json
import sqlite3
from pathlib import Path
import httpx

p = argparse.ArgumentParser()
p.add_argument('--url', required=True)
p.add_argument('--phase', default='final')
a = p.parse_args()
root = Path(__file__).parent
c = httpx.Client(base_url=a.url, timeout=20)
def get(route):
    r = c.get(route); r.raise_for_status(); return r.json()

data = {
    'personas': [x for x in get('/personas')['items'] if x['name'].startswith('Wave45 M3')],
    'scenes': [x for x in get('/scene-library')['items'] if x['scene_name'].startswith('Wave45 M3')],
    'usage': [x for x in get('/model-usage/stats')['records'] if x['created_at'] >= '2026-09-09T11:00' and x['model'] == 'MiniMax-M3'],
}
conn = sqlite3.connect('file:/Users/ffox/Library/Application Support/com.vibelearner.desktop/ai-data/vibe_learner.db?mode=ro', uri=True)
conn.row_factory = sqlite3.Row
data['traces'] = []
for r in conn.execute("SELECT workflow,stage,state,trace_id,created_at,terminal_trace FROM harness_runtime_executions WHERE created_at >= ? AND workflow IN ('persona','scene') ORDER BY created_at", ('2026-09-09T11:00',)):
    d = dict(r); t = json.loads(d.pop('terminal_trace') or '{}')
    d.update(trace_status=t.get('status'), checks=t.get('checks'))
    data['traces'].append(d)
(root / f'{a.phase}-readback.json').write_text(json.dumps(data, ensure_ascii=False, indent=2))
print(json.dumps({'personas':len(data['personas']), 'scenes':len(data['scenes']), 'usage_calls':len(data['usage']), 'traces':len(data['traces'])}))
