"""Bounded synthetic multimedia Study experiments; all provider calls metered."""
from dataclasses import replace
import hashlib
import json
import re
import fitz
from fastapi.testclient import TestClient
from app.models.api import StudyChatOperationReceiptResponse
from app.models.study_chat_effect import StudyChatCommittedEffectBatchV1
from .common import Bridge, create_app, envelope, outcome, safe_traces, settings, source_manifest, traces
from .study_fixture import create_document, create_persona, create_session

SOURCE = 'A linear equation 2x + 3 = 11 has solution x = 4. Subtract 3, then divide by 2.'
CASES = [
 ('multiple-choice','question','请调用 ask_multiple_choice_question，为方程 2x+3=11 出一道求 x 的四选一题。等待我答题，不公布正确答案或解析。','ask_multiple_choice_question'),
 ('fill-blank','question','请调用 ask_fill_blank_question，出一道填空：2x+3=11，x=____。等待我答题，不公布答案或解析。','ask_fill_blank_question'),
 ('pdf-read','pdf','请投射上传的 PDF 第1页，调用 read_projected_pdf_content 读取文字，简短报告方程和解。不出题。','project_uploaded_pdf,read_projected_pdf_content'),
 ('pdf-highlight','pdf','请投射上传的 PDF 第1页，高亮原文 2x + 3 = 11，标签为原方程，保留高亮。不出题。','project_uploaded_pdf,highlight_projected_pdf_text'),
 ('image-box','image','请投射上传的图片，用矩形框选其中的 2x + 3 = 11，标签为原方程，保留框选。简短解释先减3的原因。不出题。','project_uploaded_image,annotate_projected_image_region'),
 ('image-clear','image','请投射上传的图片，用矩形框选其中的 2x + 3 = 11，然后清除图片所有标注。报告实际完成的操作，不出题。','project_uploaded_image,annotate_projected_image_region,clear_projected_image_overlays'),
]

def fixture():
    with fitz.open() as pdf:
        page=pdf.new_page(width=360,height=200)
        page.insert_text((40,85),'2x + 3 = 11',fontsize=24)
        page.insert_text((40,140),'Subtract 3; divide by 2.',fontsize=14)
        rect=page.search_for('2x + 3 = 11')[0]
        return pdf.tobytes(),page.get_pixmap(alpha=False).tobytes('png'),[rect.x0/360,rect.y0/200,rect.x1/360,rect.y1/200]

def run_sample(context,case,variant):
    kind=case.lane
    config=replace(settings(context),openai_chat_model_multimodal=kind=='image')
    def fake(payload):
        question=None
        if kind=='question':
            question={'question_type':'multiple_choice','prompt':'2x+3=11，x等于多少？','options':[{'key':k,'text':v} for k,v in zip('ABCD',['2','3','4','5'])],'answer_key':'C','call_back':True}
        return envelope(json.dumps({'text':'请完成题目。','mood':'calm','action':'idle','interactive_question':question}))
    bridge=Bridge(context,fake)
    evidence={'domain':'study-multimedia','case':case.id,'variant':variant.id,'image_generation_tested':False,'audio_video_tested':False}
    metrics={}
    attempt_input=None
    with bridge.installed():
        app=create_app(settings=config)
        with TestClient(app) as client:
            document,_=create_document(client,SOURCE)
            session=create_session(client,document,create_persona(client))
            sid=session['id'];rid='multimedia-'+context.transport.sample[:24]
            message=case.request+'\n'+variant.instruction
            pdf,png,target=fixture()
            evidence['synthetic_image']={'sha256':hashlib.sha256(png).hexdigest(),'bytes':len(png),'width':360,'height':200,'target_rect':target}
            if kind in ('pdf','image'):
                data,mime,name=(pdf,'application/pdf','equation.pdf') if kind=='pdf' else (png,'image/png','equation.png')
                response=client.post(f'/study-sessions/{sid}/chat-with-attachments',data={'client_request_id':rid,'expected_session_revision':str(session['revision']),'message':message},files={'files':(name,data,mime)})
            else:
                response=client.post(f'/study-sessions/{sid}/chat',json={'client_request_id':rid,'expected_session_revision':session['revision'],'message':message})
            recovery=client.get(f'/study-sessions/{sid}/chat-operations/{rid}')
            evidence['http_status']=response.status_code
            if recovery.status_code!=200:return outcome(context,{'operation_readable':False},evidence,status='infrastructure_failed')
            receipt=StudyChatOperationReceiptResponse.model_validate(recovery.json());evidence['receipt']=receipt.model_dump(mode='json')
            public=receipt.result.session.model_dump(mode='json') if receipt.result else None
            binding=app.state.container.study_chat_operation_repository.require_harness_operation(receipt.operation_id)
            terminal=traces(app.state.container,binding.harness_operation_id)
            evidence.update(harness_operation_id=binding.harness_operation_id,terminal_traces=safe_traces(terminal))
            operation=app.state.container.study_chat_operation_repository.get(session_id=sid,client_request_id=rid)
            raw=(operation.response_payload or {}).get('_committed_effect_batch')
            batch=StudyChatCommittedEffectBatchV1.model_validate(raw) if raw else None
            evidence['effect_batch']={'operation_id':batch.operation_id,'effect_batch_id':batch.effect_batch_id,'effect_kinds':[e.effect_kind for e in batch.effects]} if batch else None
            tools=[t for turn in (public or {}).get('turns',[]) for t in turn.get('tool_calls',[])]
            succeeded=[t['tool_name'] for t in tools if json.loads(t['result_json']).get('ok') is True]
            evidence.update(observed_tool_names=[t['tool_name'] for t in tools],successful_tool_names=succeeded)
            read=client.get(f'/study-sessions/{sid}')
            metrics.update(committed=receipt.status=='committed',readback_equal=public is not None and read.json()==public,typed_effect_batch=batch is not None,v3_committed=bool(terminal) and all(t.commit_evidence.status=='committed' for t in terminal),required_tools_succeeded=all(t in succeeded for t in case.gold.split(',')))
            if kind=='question':
                q=receipt.result.interactive_question.model_dump(mode='json') if receipt.result and receipt.result.interactive_question else None
                metrics['question_present']=q is not None
                metrics['public_grading_fields_absent']=q is not None and not(set(q)&{'grading_spec','answer_key','accepted_answers','explanation'})
                # Surface leakage is separately inspected by a human; this conservative guard is not semantic certification.
                reply=receipt.result.reply if receipt.result else ''
                metrics['no_explicit_answer_leak']=q is not None and re.search(r'x\s*[=＝]\s*4|答案[是为：:]\s*4',reply+' '+(q or {}).get('prompt',''))==None
                private=app.state.container.study_session_repository.get(sid)
                question=private.turns[-1].interactive_question if private.turns else None
                grading=question.grading_spec if question else None
                if grading and question.question_type=='multiple_choice':
                    correct=next((o.text for o in question.options if o.key==grading.correct_option_key),'')
                    metrics['grading_gold_correct']=re.fullmatch(r'(?:x\s*[=＝]\s*)?4',correct.strip()) is not None
                else:metrics['grading_gold_correct']=grading is not None and '4' in grading.accepted_answers
                if q and grading:
                    answer=grading.correct_option_key if question.question_type=='multiple_choice' else '999'
                    attempt_input={'turn_id':private.turns[-1].id,'expected_session_revision':public['revision'],'client_attempt_id':'multimedia-answer','submitted_answer':answer}
                    expected_correct=question.question_type=='multiple_choice'
            else:
                projection=(public or {}).get('projected_pdf')
                metrics['projection_present']=bool(projection)
                overlays=(projection or {}).get('overlays',[])
                evidence['projection']=projection
                metrics['projection_effect_committed']=batch is not None and any(e.effect_kind=='projection' for e in batch.effects)
                if case.id in ('pdf-highlight','image-box'):metrics['overlay_persisted']=len(overlays)==1
                if case.id=='image-clear':metrics['overlays_cleared']=len(overlays)==0
                if case.id=='image-box':
                    rects=overlays[0].get('rects',[]) if overlays else []
                    evidence['overlay_rects']=rects
                    if len(rects)==1:
                        r=rects[0];x0,y0,x1,y1=target
                        intersection=max(0,min(x1,r['x']+r['width'])-max(x0,r['x']))*max(0,min(y1,r['y']+r['height'])-max(y0,r['y']))
                        area=(x1-x0)*(y1-y0);box_area=r['width']*r['height']
                        coverage=intersection/area;iou=intersection/(area+box_area-intersection) if area+box_area-intersection else 0
                    else:coverage=iou=0
                    evidence['localization']={'target_coverage':coverage,'iou':iou,'minimum_coverage':.8,'minimum_iou':.45}
                    metrics['box_localization_pass']=coverage>=.8 and iou>=.45
                attachments=[a for t in (public or {}).get('turns',[]) for a in t.get('learner_attachments',[])]
                metrics['attachment_committed']=len(attachments)==1
            before=bridge.calls
        with TestClient(create_app(settings=config)) as restarted:
            rr=restarted.get(f'/study-sessions/{sid}/chat-operations/{rid}');rs=restarted.get(f'/study-sessions/{sid}')
            metrics['restart_equal']=rr.status_code==200 and rr.json()==recovery.json() and public is not None and rs.json()==public
            if kind=='question':
                metrics['answer_attempt_correctly_graded']=False
                metrics['answer_restart_equal']=False
                if attempt_input:
                    attempt=restarted.post(f'/study-sessions/{sid}/attempt',json=attempt_input)
                    evidence['answer_attempt']={'http_status':attempt.status_code,'expected_correct':expected_correct}
                    if attempt.status_code==200:
                        result=attempt.json();evidence['answer_attempt']['result']=result
                        metrics['answer_attempt_correctly_graded']=result.get('is_correct') is expected_correct
                        answered=restarted.get(f'/study-sessions/{sid}').json()
            else:answered=None
        if kind=='question' and attempt_input and attempt.status_code==200:
            with TestClient(create_app(settings=config)) as final_client:
                metrics['answer_restart_equal']=final_client.get(f'/study-sessions/{sid}').json()==answered
        metrics['recovery_no_provider_calls']=before==bridge.calls
    status='uncertain' if receipt.status=='uncertain' else 'infrastructure_failed' if bridge.failure else None
    evidence['bridge_response_projection']={'contract':'production-completed-tool-index-normalization','normalized_tool_indexes':bridge.normalized_tool_indexes}
    return outcome(context,metrics,evidence,status=status)
