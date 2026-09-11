import unittest
from types import SimpleNamespace

from app.services.study_memory import _build_candidates


class StudyMemoryExcerptTests(unittest.TestCase):
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
