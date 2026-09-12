"""Shared synthetic Study setup and checkpointed operation evidence for lab lanes."""
import json
import re
import fitz
from app.models.api import StudyChatOperationReceiptResponse
from model_quality.runner import atomic_json
from .common import persona, safe_traces, traces


def create_document(client, source):
    with fitz.open() as pdf:
        page=pdf.new_page()
        font='china-s' if re.search(r'[\u4e00-\u9fff]',source) else 'helv'
        remaining=page.insert_textbox(fitz.Rect(40,40,555,800),'Chapter 1 Reference\n'+source,fontsize=12,fontname=font)
        if remaining < 0:
            raise ValueError('synthetic_pdf_does_not_fit')
        extracted=page.get_text()
        if re.sub(r'\s+','',source) not in re.sub(r'\s+','',extracted):
            raise ValueError('synthetic_pdf_source_extraction_mismatch')
        data=pdf.tobytes()
    uploaded=client.post('/documents',files={'file':('synthetic.pdf',data,'application/pdf')})
    uploaded.raise_for_status()
    did=uploaded.json()['id']
    processed=client.post(f'/documents/{did}/process',json={'force_ocr':False})
    processed.raise_for_status()
    document=processed.json()
    if not document['study_units']:
        raise ValueError('synthetic_document_has_no_units')
    debug=client.get(f'/documents/{did}/debug');debug.raise_for_status()
    return document,debug.json()


def create_persona(client):
    response=client.post('/personas',json=persona());response.raise_for_status()
    return response.json()['id']


def create_session(client,document,persona_id):
    response=client.post('/study-sessions',json={'document_id':document['id'],'persona_id':persona_id,
        'study_unit_id':document['study_units'][0]['id']})
    response.raise_for_status()
    return response.json()


def exchange(client,app,context,evidence,session,message,request_id):
    sid=session['id']
    admitted={'session_id':sid,'client_request_id':request_id,'expected_revision':session['revision']}
    evidence.setdefault('admissions',[]).append(admitted)
    atomic_json(context.storage/'domain-evidence.json',evidence)
    response=client.post(f'/study-sessions/{sid}/chat',json={'client_request_id':request_id,
        'expected_session_revision':session['revision'],'message':message})
    recovery=client.get(f'/study-sessions/{sid}/chat-operations/{request_id}')
    recovery.raise_for_status()
    receipt=StudyChatOperationReceiptResponse.model_validate(recovery.json())
    binding=app.state.container.study_chat_operation_repository.require_harness_operation(receipt.operation_id)
    terminal=traces(app.state.container,binding.harness_operation_id)
    public=receipt.result.session.model_dump(mode='json') if receipt.result else None
    readback=client.get(f'/study-sessions/{sid}')
    item={'http_status':response.status_code,'receipt':receipt.model_dump(mode='json'),
        'harness_operation_id':binding.harness_operation_id,'terminal_traces':safe_traces(terminal),
        'readback_equal':readback.status_code==200 and public is not None and readback.json()==public,
        'v3_committed':bool(terminal) and all(t.status in ('passed','repaired') and t.commit_evidence.status=='committed' for t in terminal)}
    evidence.setdefault('operations',[]).append(item)
    atomic_json(context.storage/'domain-evidence.json',evidence)
    return receipt,item


def restart_check(client,evidence):
    results=[]
    for operation in evidence.get('operations',[]):
        receipt=operation['receipt'];sid=receipt['session_id']
        result=client.get(f"/study-sessions/{sid}/chat-operations/{receipt['client_request_id']}")
        session=client.get(f'/study-sessions/{sid}')
        public=(receipt.get('result') or {}).get('session')
        results.append(result.status_code==200 and result.json()==receipt and public is not None and session.status_code==200 and session.json()==public)
    return bool(results) and all(results)


def unique_object(pairs):
    value={}
    for key,item in pairs:
        if key in value:raise ValueError('duplicate_json_key')
        value[key]=item
    return value


def grade_json_answer(text,gold):
    value=text.strip()
    if value.startswith('```json\n') and value.endswith('\n```'):
        value=value[8:-4].strip()
    elif value.startswith('```\n') and value.endswith('\n```'):
        value=value[4:-4].strip()
    try:
        actual=json.loads(value,object_pairs_hook=unique_object)
    except (ValueError,TypeError):
        return False,False,None
    shape=isinstance(actual,dict) and set(actual)==set(gold) and all(isinstance(v,str) for v in actual.values())
    return shape,shape and actual==gold,actual if shape else None
