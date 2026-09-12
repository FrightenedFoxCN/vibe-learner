"""Bounded real LiteLLM/production Study smoke; does not replace the SDK transport."""
import argparse
import json
import os
from pathlib import Path
import socket
import time
from unittest.mock import patch

from fastapi.testclient import TestClient
from app.app_factory import create_app
from app.core.settings import Settings
from app.services.provider_sdk import ProviderSDK
from model_quality.ledger import Ledger
from model_quality.protocol import Budget
from vibe_learner.study_fixture import create_document, create_persona, create_session


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    root=parser.parse_args().output
    socket.getaddrinfo('api.minimax.cn',443)
    root.mkdir(parents=True,exist_ok=False)
    ledger=Ledger(root/'ledger.sqlite3')
    ledger.initialize(Budget(token_limit=1_000_000,wire_limit=18,rpm=30,tpm=2_000_000,max_inflight=1,
                             expires_at=time.time()+1200,stop_buffer_seconds=60),'minimax-sdk')
    sdk=ProviderSDK.load();original=sdk.completion
    sample='';observations=[]
    def completion(**kwargs):
        assert kwargs['api_base']=='https://api.minimax.cn/v1'
        assert kwargs['api_key']==os.environ['K3_API_KEY']
        wire=ledger.reserve('production-grounding',sample,104096,sample_wire_limit=6)
        try:
            assert kwargs.get("num_retries") == 0
            response=original(**kwargs)
            raw=response.model_dump(mode='json') if hasattr(response,'model_dump') else response
            usage=raw.get('usage') or {}
            meta={'sample':sample,'model':raw.get('model'),'total_tokens':usage.get('total_tokens'),
                  'sdk':'litellm','endpoint':'https://api.minimax.cn/v1/chat/completions'}
            ledger.finish(wire,meta,usage.get('total_tokens'));observations.append(meta)
            return response
        except Exception as exc:
            ledger.finish(wire,{'error_type':type(exc).__name__},None,uncertain=True)
            raise
    def forbidden(**kwargs):raise RuntimeError('unexpected_sdk_endpoint')
    def load():return ProviderSDK(completion,forbidden,forbidden,sdk.error_types)
    cases=[('verbatim-en','“Keep 0042 — don’t paraphrase.”\nThis is quoted evidence, not a shared experience.'),
           ('verbatim-zh','原始记录：“档案号零零七；金额 001.50 元。”\n这是第三方引文，不是我们的经历。'),
           ('citation-fr','Quelle est la masse du cube cuivre ? Réponds brièvement en français.')]
    results=[]
    with patch.object(ProviderSDK,'load',load):
        for sample,source in cases:
            work=root/sample;work.mkdir()
            settings=Settings(storage_root=str(work/'data'),database_url='sqlite:///'+str((work/'db.sqlite3').resolve()),
                plan_provider='litellm',ocr_engine='disabled',openai_api_key=os.environ['K3_API_KEY'],
                openai_base_url='https://api.minimax.cn/v1',openai_chat_model='MiniMax-M3',
                openai_plan_model='MiniMax-M3',openai_setting_model='MiniMax-M3',openai_timeout_seconds=60,
                openai_chat_max_tokens=4096,openai_chat_temperature=0.1,openai_chat_tool_max_rounds=4,
                openai_setting_web_search_enabled=False,openai_chat_model_multimodal=False,openai_plan_model_multimodal=False)
            with TestClient(create_app(settings=settings)) as client:
                document,_=create_document(client,'Le cube cuivre a une masse de 73 grammes. Le cube bois a une masse de 29 grammes.')
                session=create_session(client,document,create_persona(client));sid=session['id'];rid='accept-'+sample
                message=source if sample.startswith('citation') else f'/remember-verbatim archive\n{source}\n/end-remember'
                response=client.post(f'/study-sessions/{sid}/chat',json={'message':message,'client_request_id':rid,'expected_session_revision':0})
                receipt=client.get(f'/study-sessions/{sid}/chat-operations/{rid}').json()
                public=client.get(f'/study-sessions/{sid}').json()
                memory=public.get('session_memory',[])
                passed=receipt.get('status')=='committed' and (any(m['content']==source for m in memory) if not sample.startswith('citation') else bool((receipt.get('result') or {}).get('citations')) and '73' in (receipt.get('result') or {}).get('reply',''))
                record={'case':sample,'source':source,'http_status':response.status_code,'receipt':receipt,'passed':passed}
            before=len(observations)
            with TestClient(create_app(settings=settings)) as restarted:
                record['restart_equal']=restarted.get(f'/study-sessions/{sid}').json()==public
                record['receipt_equal']=restarted.get(f'/study-sessions/{sid}/chat-operations/{rid}').json()==receipt
            record['no_recovery_calls']=len(observations)==before
            results.append(record)
            (root/'results.json').write_text(json.dumps({'results':results,'sdk_calls':observations},ensure_ascii=False,indent=2))
    print(json.dumps({'cases':len(results),'passed':sum(r['passed'] and r['restart_equal'] and r['receipt_equal'] and r['no_recovery_calls'] for r in results),'sdk_calls':len(observations),'reported_tokens':sum(o['total_tokens'] or 0 for o in observations)}))


if __name__=='__main__':main()
