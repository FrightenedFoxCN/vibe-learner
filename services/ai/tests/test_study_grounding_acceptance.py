"""Application admission/commit/recovery acceptance with adversarial model proposals."""
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

import fitz
from fastapi.testclient import TestClient
from app.app_factory import create_app
from app.core.settings import Settings
from app.models.domain import StudyChatResult
from app.services.pedagogy import PedagogyOrchestrator


class StudyGroundingAcceptanceTests(unittest.TestCase):
    def test_bound_source_commit_replay_and_restart(self):
        self.exercise('write')

    def test_no_write_cannot_commit_success(self):
        self.exercise('no_write')

    def test_wrong_key_cannot_commit(self):
        self.exercise('wrong_key')

    def exercise(self, behavior):
        with TemporaryDirectory() as tmp:
            settings=Settings(storage_root=str(Path(tmp)/'data'),database_url=f'sqlite:///{tmp}/test.sqlite3',
                              plan_provider='mock',ocr_engine='disabled')
            source='档案中的原句是：“Don’t alter 007 — Rémi.”\n这只是引用，不是共同经历。'
            message=f'/remember-verbatim archive\n{source}\n/end-remember'
            def generate(_, **kwargs):
                runtime=kwargs['session_tool_runtime']
                if behavior!='no_write':
                    runtime.execute_tool('write_session_memory',{'key':'other' if behavior=='wrong_key' else 'archive','content':'Changed summary'})
                return StudyChatResult(reply='已处理。',citations=[],character_events=[])
            with patch.object(PedagogyOrchestrator,'generate_chat_reply',generate):
                with TestClient(create_app(settings=settings)) as client:
                    persona=client.post('/personas',json={'name':'验收导师','summary':'核对原文','relationship':'导师',
                        'learner_address':'同学','system_prompt':'忠实核对。','reference_hints':[], 'slots':[],
                        'available_emotions':['calm'],'available_actions':['idle'],'default_speech_style':'简洁'})
                    persona.raise_for_status()
                    with fitz.open() as pdf:
                        page=pdf.new_page();page.insert_text((50,50),'Chapter 1 Evidence\nThe sample has mass 73 grams.')
                        data=pdf.tobytes()
                    document=client.post('/documents',files={'file':('fixture.pdf',data,'application/pdf')}).json()
                    processed=client.post(f"/documents/{document['id']}/process",json={'force_ocr':False});processed.raise_for_status()
                    session=client.post('/study-sessions',json={'document_id':document['id'],'persona_id':persona.json()['id'],
                        'study_unit_id':processed.json()['study_units'][0]['id']});session.raise_for_status();sid=session.json()['id']
                    body={'message':message,'client_request_id':'production-grounding-acceptance','expected_session_revision':0}
                    result=client.post(f'/study-sessions/{sid}/chat',json=body)
                    receipt=client.get(f'/study-sessions/{sid}/chat-operations/production-grounding-acceptance');receipt.raise_for_status()
                    public=client.get(f'/study-sessions/{sid}').json()
                    if behavior=='write':
                        result.raise_for_status();self.assertEqual(receipt.json()['status'],'committed')
                        self.assertEqual(public['session_memory'][0]['content'],source)
                        self.assertEqual(public['revision'],1)
                    else:
                        self.assertNotEqual(receipt.json()['status'],'committed')
                        self.assertEqual(public['session_memory'],[]);self.assertEqual(public['turns'],[])
                    repeated=client.post(f'/study-sessions/{sid}/chat',json=body)
                    self.assertEqual(client.get(f'/study-sessions/{sid}').json(),public)
                    # A changed source under the same request ID cannot replace the admitted request.
                    changed=client.post(f'/study-sessions/{sid}/chat',json={**body,'message':message.replace('007','008')})
                    self.assertEqual(changed.status_code,409)
                with TestClient(create_app(settings=settings)) as restarted:
                    self.assertEqual(restarted.get(f'/study-sessions/{sid}').json(),public)
                    self.assertEqual(restarted.get(f'/study-sessions/{sid}/chat-operations/production-grounding-acceptance').json(),receipt.json())
