"""Small synthetic adapter acceptance matrices; no production data or test imports."""
import time
from model_quality.protocol import Campaign


def campaign(domain, transport='fake', identifier=None, budget=None):
    source = 'Camille a rendez-vous le 10 juin à 16:00. Le lieu n’est pas précisé.' if domain == 'study' else '这是初次见面的合成场景。'
    return Campaign.model_validate({
        'version': 'quality-campaign-v1', 'id': identifier or ('domain-' + domain), 'purpose': 'Domain adapter admission/read-back acceptance',
        'adapter': 'vibe_learner.' + domain + ':run_sample', 'transport': transport, 'concurrency': 2,
        'autoscale': {'max_concurrency': 4}, 'max_output_tokens': 2048, 'input_reservation_tokens': 100000,
        'sample_wire_limit': 6, 'timeout_seconds': 60, 'sample_deadline_seconds': 300,
        'budget': budget or {'token_limit': 2000000, 'wire_limit': 30, 'rpm': 30, 'tpm': 1000000, 'max_inflight': 4,
                             'expires_at': time.time()+3600, 'stop_buffer_seconds': 900},
        'cases': [{'id': domain + '-' + str(i), 'family': 'infra-fixture', 'lane': domain,
                   'provenance': 'synthetic-authored', 'source': source,
                   'request': '请调用 write_session_memory，用 key experiment_reference 原样保存记录，然后调用 read_session_memory 核对。不翻译，不出题。' if domain == 'study' else '请在 text 字段只回复：收到。不要添加其他文字。',
                   'gold': source if domain == 'study' else '收到。', 'rubric': 'study-memory-v1' if domain == 'study' else 'tavern-text-v1'} for i in range(2)],
        'variants': [{'id': 'baseline', 'instruction': '遵守本轮要求。'}]})
