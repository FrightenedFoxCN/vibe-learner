import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from fastapi import HTTPException
from pydantic import ValidationError
from app.services.study_grounding import citation_tokens, parse_verbatim_memory
from app.services.study_session_chat_runtime import StudySessionChatToolRuntime
from app.services.pedagogy import _tokenize, _build_grounded_citations


class StudyGroundingTests(unittest.TestCase):
    def test_multilingual_matching_without_substring_false_positive(self):
        for question, source in [
            ('Quelle est la température du réservoir?', 'Le réservoir contient de l’eau.'),
            ('控制阀是否关闭？', '控制阀已关闭。'),
            ('ＡＬＰＨＡ mass?', 'Alpha has mass 42 grams.'),
        ]:
            self.assertTrue(citation_tokens(question) & citation_tokens(source))
        self.assertFalse(citation_tokens('What is the art?') & citation_tokens('The cart is here.'))
        self.assertFalse(citation_tokens('Quelle est la date?') & citation_tokens('La valve est fermée.'))
        self.assertEqual(_tokenize('控制阀是否关闭'), ['控制阀是否关闭'])

    def test_explicit_source_and_quoted_commands(self):
        source='“Don’t rewrite.”\n路径 C:\\Study\\notes; 007; 张三。'
        command=f'/remember-verbatim archive_1\n{source}\n/end-remember'
        bound=parse_verbatim_memory(command, 'learner')
        self.assertEqual(bound.content, source)
        self.assertEqual(bound.key, 'archive_1')
        self.assertIsNone(parse_verbatim_memory(command, 'auto_follow_up'))
        self.assertIsNone(parse_verbatim_memory('Quoted:\n'+command, 'learner'))
        self.assertIsNone(parse_verbatim_memory('请总结这段话', 'learner'))
        for bad in ['/remember-verbatim k\n text\n/end-remember',
                    '/remember-verbatim k\ntext \n/end-remember',
                    '/remember-verbatim k\ntext',
                    '/remember-verbatim k\n'+'x'*4001+'\n/end-remember']:
            with self.assertRaises(ValueError):parse_verbatim_memory(bad, 'learner')

    def test_only_valid_tool_and_authorized_key_can_prepare_original(self):
        collector=Mock()
        collector.prepare_memory_upsert.return_value=SimpleNamespace(effect_id='effect')
        collector.preview_session_memory.return_value=[{'key':'archive','content':'original'}]
        runtime=StudySessionChatToolRuntime(session_service=SimpleNamespace(
            require_session=lambda _: SimpleNamespace(session_memory=[])),
            plan_service=Mock(), session_id='session', effect_collector=collector)
        runtime.verbatim_memory_source=parse_verbatim_memory('/remember-verbatim archive\noriginal\n/end-remember','learner')
        result=runtime.execute_tool('write_session_memory',{'key':'archive','content':'paraphrase'})
        self.assertEqual(collector.prepare_memory_upsert.call_args.args[0].content,'original')
        self.assertFalse(result['committed'])
        collector.reset_mock()
        with self.assertRaises(HTTPException):runtime.execute_tool('write_session_memory',{'key':'other','content':'bad'})
        with self.assertRaises(ValidationError):runtime.execute_tool('write_session_memory',{'key':'archive','content':'bad','unknown':True})
        collector.prepare_memory_upsert.assert_not_called()

    def test_multiple_pages_rank_evidence_and_exclude_word_fragments(self):
        chunks=[SimpleNamespace(section_id='unit',page_start=i,page_end=i,text_preview='',content=text)
                for i,text in enumerate(['The cart carries stones.', 'The art depicts a harbor.',
                                         'Le réservoir contient de l’eau.'],1)]
        report=SimpleNamespace(study_units=[SimpleNamespace(id='unit',title='Evidence',page_start=1,page_end=3,source_section_ids=[])],sections=[],chunks=chunks)
        for question,pages in [('What does the art depict?', [2]),('Que contient le réservoir?', [3]),('火星轨道的周期是多少？', [])]:
            citations=_build_grounded_citations(debug_report=report,study_unit_id='unit',study_unit_title='Evidence',message=question)
            self.assertEqual([c.page_start for c in citations],pages)

    def test_legacy_snapshot_decode_is_read_only(self):
        import json
        from app.services.study_v3 import decode_study_snapshot, StudyV3SnapshotService
        from tests.test_study_v3_runtime import StudyV3RuntimeTests
        payload=StudyV3RuntimeTests()._protected_payload()
        payload['schema_version']='study-chat-protected-snapshot-v1'
        payload['dependencies'].pop('learner_message')
        self.assertEqual(decode_study_snapshot(json.dumps(payload).encode()),payload)
        with self.assertRaisesRegex(ValueError,'registration_version'):
            StudyV3SnapshotService(Mock()).register_session_snapshot(operation_binding=Mock(),payload=payload)
