"""Write a frozen four-sample manifest; does not send any provider requests."""
import argparse
import json
from pathlib import Path
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--transport', choices=['fake', 'minimax'], default='fake')
parser.add_argument('--id', default='preflight-v1')
args = parser.parse_args()
manifest = {
    'version': 'quality-campaign-v1', 'id': args.id,
    'purpose': 'Verify isolated workers, native wire accounting and resume; no model-quality adoption claim.',
    'transport': args.transport, 'concurrency': 4, 'seed': 42,
    'sample_wire_limit': 1, 'input_reservation_tokens': 4096, 'max_output_tokens': 256,
    'budget': {'token_limit': 20000, 'wire_limit': 4, 'rpm': 4, 'tpm': 20000,
               'max_inflight': 4, 'expires_at': time.time()+3600, 'stop_buffer_seconds': 900},
    'cases': [
        {'id': 'en-control', 'family': 'en-control', 'lane': 'preflight',
         'provenance': 'synthetic-authored', 'source': 'This is a synthetic connectivity test.',
         'request': 'Reply with exactly the two ASCII letters OK, with no other characters.',
         'gold': 'OK', 'rubric': 'exact-text-v1'},
        {'id': 'zh-control', 'family': 'zh-control', 'lane': 'preflight',
         'provenance': 'synthetic-authored', 'source': '这是合成连通性测试。',
         'request': '请只回复两个 ASCII 字母 OK，不添加其他字符。',
         'gold': 'OK', 'rubric': 'exact-text-v1'}],
    'variants': [{'id': 'baseline', 'instruction': 'Follow the user request.'},
                 {'id': 'precise', 'instruction': 'Follow the user request exactly, including its output format.'}]
}
args.output.parent.mkdir(parents=True, exist_ok=True)
with args.output.open('x', encoding='utf-8') as stream:
    json.dump(manifest, stream, ensure_ascii=False, indent=2)
    stream.write('\n')
print(args.output.resolve())
