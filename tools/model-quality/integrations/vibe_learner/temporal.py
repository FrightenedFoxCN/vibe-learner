"""Cross-session admitted seeds, bounded retrieval, and an oracle-context diagnostic."""
import json
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.models.domain import MemoryTraceHitRecord
from app.services import pedagogy
from .common import Bridge,create_app,envelope,outcome,settings,source_manifest
from .study import TEXTBOOK
from .study_fixture import create_document,create_persona,create_session,exchange,restart_check,grade_json_answer


def run_sample(context,case,variant):
    if case.rubric!='temporal-facts-v1' or variant.id not in ('baseline','oracle-context'):
        return {'status':'data_failed','failure_owner':'data','error_code':'unsupported_temporal_case'}
    source=json.loads(case.source);gold=json.loads(case.gold)
    bridge=None
    def fake(payload):
        text='收到。' if bridge.call_kind=='seed' else json.dumps(gold,ensure_ascii=False)
        return envelope(json.dumps({'text':text,'mood':'calm','action':'idle','interactive_question':None}))
    bridge=Bridge(context,fake);config=settings(context)
    evidence={'domain':'temporal','rubric':case.rubric,'source':source,
        'retrieval_embedding':'production fallback local hash; network embeddings disabled', 'retrieval':[]}
    seed_ids=[]
    original=pedagogy.retrieve_memory_hits
    def retrieve(**kwargs):
        baseline=original(**kwargs)
        if variant.id=='oracle-context':
            selected=[MemoryTraceHitRecord(session_id=s.id,study_unit_id=s.study_unit_id,scene_title='未设置场景',
                snippet='用户原话：'+turn.learner_message,created_at=turn.created_at,score=1.0,source='retriever')
                for s in kwargs['sessions'] if s.id in seed_ids for turn in s.turns]
        else:selected=baseline
        text='\n'.join(hit.snippet for hit in selected)
        evidence['retrieval'].append({'baseline_session_ids':[hit.session_id for hit in baseline],
            'selected':[hit.model_dump(mode='json') for hit in selected],
            'covered_anchors':[anchor for anchor in source['anchors'] if anchor in text]})
        return selected
    with bridge.installed():
        app=create_app(settings=config)
        with TestClient(app) as client:
            document,_=create_document(client,TEXTBOOK)
            pid=create_persona(client)
            bridge.call_kind='seed'
            for index,record in enumerate(source['records']):
                session=create_session(client,document,pid);seed_ids.append(session['id'])
                receipt,operation=exchange(client,app,context,evidence,session,
                    '下面是需保留在本次会话原话中的第三方记录，不是我们共同经历。只确认收到，不出题、不添加或改写事实，不需要执行其他工具。\n'+record,
                    'seed-'+context.transport.sample[:20]+'-'+str(index))
                if receipt.status!='committed' or not operation['readback_equal']:
                    return outcome(context,{'seed_committed':False},evidence,status='uncertain' if receipt.status=='uncertain' else 'candidate_failed')
            bridge.call_kind='generation'
            session=create_session(client,document,pid)
            with patch.object(pedagogy,'retrieve_memory_hits',retrieve):
                receipt,operation=exchange(client,app,context,evidence,session,case.request,'query-'+context.transport.sample[:24])
            public=receipt.result.session.model_dump(mode='json') if receipt.result else {}
            turn=(public.get('turns') or [{}])[-1]
            shape,correct,decoded=grade_json_answer(turn.get('assistant_reply',''),gold)
            evidence.update(seed_session_ids=seed_ids,decoded_answer=decoded)
            before=bridge.calls
        with TestClient(create_app(settings=config)) as restarted:equal=restart_check(restarted,evidence)
    selection=evidence['retrieval'][-1] if evidence['retrieval'] else {'selected':[],'covered_anchors':[]}
    selected_ids={hit['session_id'] for hit in selection['selected']}
    metrics={'seed_committed':all(op['receipt']['status']=='committed' and op['readback_equal'] for op in evidence['operations'][:-1]),
        'committed':receipt.status=='committed','readback_equal':operation['readback_equal'],'v3_committed':operation['v3_committed'],
        'restart_equal':equal,'recovery_no_provider_calls':bridge.calls==before,'answer_schema':shape,'answer_exact':correct,
        'evidence_anchor_coverage':len(selection['covered_anchors'])==len(source['anchors']),
        'isolated_memory_sources':selected_ids<=set(seed_ids)}
    return outcome(context,metrics,evidence,status='uncertain' if receipt.status=='uncertain' else None)
