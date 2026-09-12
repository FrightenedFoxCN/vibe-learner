"""Actual Study citation precision/recall and literal fact-answer contrast."""
from contextlib import nullcontext
import json
import re
import unicodedata
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.services import pedagogy
from .common import Bridge,create_app,envelope,outcome,settings,source_manifest
from .study_fixture import create_document,create_persona,create_session,exchange,restart_check,grade_json_answer


STOP = set('the a an is are of to in and for with what when who which how does do this that current note unrelated only return answer unknown de la le les un une des du et est en pour quelle quel qui ce cette au aux avec par son sa source sans rapport'.split())


def normalized_tokens(text):
    value=unicodedata.normalize('NFKC',text).casefold()
    han=re.findall(r'[\u4e00-\u9fff]+',value)
    tokens=[token for token in re.findall(r'[^\W_]+',re.sub(r'[\u4e00-\u9fff]+',' ',value)) if len(token)>1 and token not in STOP]
    # An experimental retrieval candidate, not an entailment verifier.
    for run in han:tokens.extend(run[i:i+2] for i in range(max(1,len(run)-1)))
    return tokens


def run_sample(context,case,variant):
    if case.rubric!='citation-facts-v1' or variant.id not in ('baseline','normalized'):
        return {'status':'data_failed','failure_owner':'data','error_code':'unsupported_citation_case'}
    source=json.loads(case.source);gold=json.loads(case.gold)
    bridge=Bridge(context,lambda payload:envelope(json.dumps({'text':json.dumps(gold,ensure_ascii=False),'mood':'calm','action':'idle','interactive_question':None})))
    config=settings(context);evidence={'domain':'citation','rubric':case.rubric,'source':source}
    original=pedagogy._build_grounded_citations
    observed=[]
    def citations(**kwargs):
        baseline=original(**kwargs)
        if variant.id=='normalized':
            with patch.object(pedagogy,'_tokenize',normalized_tokens):result=original(**kwargs)
        else:result=baseline
        observed.append({'baseline':[c.model_dump(mode='json') for c in baseline],'selected':[c.model_dump(mode='json') for c in result]})
        return result
    with bridge.installed(),patch.object(pedagogy,'_build_grounded_citations',citations):
        app=create_app(settings=config)
        with TestClient(app) as client:
            document,debug=create_document(client,source['text'])
            evidence['document_debug']=debug
            session=create_session(client,document,create_persona(client))
            receipt,operation=exchange(client,app,context,evidence,session,case.request,'citation-'+context.transport.sample[:24])
            public=receipt.result.session.model_dump(mode='json') if receipt.result else {}
            turn=(public.get('turns') or [{}])[-1]
            returned=turn.get('citations',[])
            shape,answer,decoded=grade_json_answer(turn.get('assistant_reply',''),gold)
            evidence.update(citation_selection=observed,decoded_answer=decoded)
            before=bridge.calls
        with TestClient(create_app(settings=config)) as restarted:equal=restart_check(restarted,evidence)
    relevant=source['relevant']
    valid_citations=all(c['page_start']==1 and c['page_end']==1 for c in returned)
    metrics={'committed':receipt.status=='committed','readback_equal':operation['readback_equal'],
        'v3_committed':operation['v3_committed'],'restart_equal':equal,'recovery_no_provider_calls':bridge.calls==before,
        'answer_schema':shape,'answer_exact':answer,'citation_recall_or_correct_abstention':receipt.status=='committed' and (bool(returned) if relevant else not returned),
        'citation_precision':receipt.status=='committed' and valid_citations and (relevant or not returned)}
    return outcome(context,metrics,evidence,status='uncertain' if receipt.status=='uncertain' else None)
