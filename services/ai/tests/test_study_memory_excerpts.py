import unittest
import json
import os
import subprocess
import sys
from types import SimpleNamespace

from app.services.study_memory import _build_candidates, build_memory_context, _tokenize, _embed, _cosine, retrieve_memory_hits


class StudyMemoryExcerptTests(unittest.TestCase):
    def test_retrieval_embeds_and_returns_query_selected_user_evidence(self):
        text = '复习地点青石，暗号晴鸟。' + '整理材料。' * 200 + '最终地点南门，全部暗号撤销。'
        turn = SimpleNamespace(learner_message=text, learner_message_kind='learner',
            assistant_reply='收到。', created_at='2026-09-12T00:00:00Z')
        session = SimpleNamespace(id='past', study_unit_id='unit', scene_profile=None, turns=[turn])
        observed = []
        def embed(texts):
            observed.extend(texts)
            return [[1.0] for _ in texts]
        hits = retrieve_memory_hits(sessions=[session], current_session_id='current',
            active_study_unit_id='unit', query='复习地点和暗号', active_scene_summary='', embed_texts=embed)
        self.assertEqual(len(hits), 1)
        self.assertIn('最终地点南门，全部暗号撤销。', hits[0].snippet)
        self.assertEqual(observed[1], hits[0].snippet)
        self.assertTrue(hits[0].snippet.startswith('用户原话：'))
        self.assertIn('助手回复：收到。', hits[0].snippet)
        self.assertLessEqual(len(hits[0].snippet.split('\n助手回复：')[0].removeprefix('用户原话：')), 800)

    def test_chinese_query_overlaps_paraphrased_memory(self):
        query = set(_tokenize('复习地点和暗号的最新约定'))
        update = set(_tokenize('更新复习约定：地点改为白桦阅览室，暗号已撤销。'))
        self.assertTrue({'复习', '地点', '暗号', '约定'} <= query & update)
        self.assertGreater(_cosine(_embed('复习地点暗号'), _embed('复习地点更新，暗号撤销')), 0)

    def test_french_accents_and_unicode_normalization_are_preserved(self):
        self.assertEqual(_tokenize('ÉCOLE Cafe\u0301'), ['école', 'café'])
        self.assertEqual(_tokenize('ＡＢＣ１２'), ['abc12'])

    def test_fallback_vector_is_stable_across_process_hash_seeds(self):
        code = "import json; from app.services.study_memory import _embed; print(json.dumps(_embed('复习地点 salle café')))"
        outputs = [subprocess.check_output([sys.executable, '-c', code],
            env={**os.environ, 'PYTHONHASHSEED': seed}, text=True) for seed in ('1', '2')]
        self.assertEqual(json.loads(outputs[0]), json.loads(outputs[1]))

    def test_initial_memory_context_retains_record_time(self):
        hit = SimpleNamespace(score=0.8, session_id='past', study_unit_id='unit',
                              scene_title='room', snippet='地点是白桦阅览室。',
                              created_at='2026-09-12T01:02:03+00:00')
        self.assertIn('created_at=2026-09-12T01:02:03+00:00', build_memory_context([hit]))

    def candidates(self, learner, assistant, kind='learner'):
        turn = SimpleNamespace(learner_message=learner, learner_message_kind=kind, assistant_reply=assistant, created_at='2026-09-12T00:00:00Z')
        session = SimpleNamespace(id='past', study_unit_id='unit', scene_profile=None, turns=[turn])
        return _build_candidates(sessions=[session], current_session_id='current')

    def test_long_user_update_survives_verbose_assistant_reply(self):
        update = '整理等式材料。' * 50 + '最新地点改为白桦阅览室；旧地点和暗号均撤销。'
        snippet = self.candidates(update, '我来复述教材。' * 100)[0].snippet
        self.assertIn('最新地点改为白桦阅览室；旧地点和暗号均撤销。', snippet)
        self.assertIn('用户原话：', snippet)
        self.assertIn('助手回复：', snippet)

    def test_assistant_suggestion_is_preserved_with_source_label(self):
        snippet = self.candidates('你建议在哪里见面？', '我建议白桦阅览室，尚待你确认。')[0].snippet
        self.assertIn('助手回复：我建议白桦阅览室，尚待你确认。', snippet)

    def test_automatic_inputs_are_not_attributed_to_the_learner(self):
        for kind in ('scheduled_follow_up', 'session_prelude'):
            snippet = self.candidates('提醒学习者核对方程。', '你求出x了吗？', kind)[0].snippet
            self.assertNotIn('用户原话：', snippet)
            self.assertTrue(snippet.startswith('自动输入（非用户发言）：'))

    def test_role_budgets_bound_large_turn_and_mark_truncation(self):
        snippet = self.candidates('甲' * 2000, '乙' * 2000)[0].snippet
        learner, assistant = snippet.split('\n助手回复：')
        self.assertEqual(len(learner.removeprefix('用户原话：')), 800)
        self.assertEqual(len(assistant), 160)
        self.assertTrue(learner.endswith('...'))
        self.assertTrue(assistant.endswith('...'))
