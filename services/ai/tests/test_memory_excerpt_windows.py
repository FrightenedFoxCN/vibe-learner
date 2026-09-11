"""Regression checks for bounded original-text memory excerpts."""
import re
import unittest

from functools import partial
from app.services.memory_excerpt import select_memory_excerpt
from app.services.study_memory import _tokenize

budgeted_query_windows = partial(select_memory_excerpt, tokenize=_tokenize)


class MemoryExcerptWindowTests(unittest.TestCase):
    def test_four_updates_and_offsets_fit_one_budget(self):
        facts = ['青石阅览室，暗号晴鸟', '红杉阅览室，暗号晨星', '白桦阅览室，暗号春风', '南门阅览室，暗号全部撤销']
        text = ''.join('整理材料。' * 150 + '复习地点改为' + fact + '。' for fact in facts)
        out = budgeted_query_windows(text, '复习地点和暗号')
        self.assertLessEqual(len(out), 800)
        for fact in facts:
            self.assertIn(fact, out)
        compact = ' '.join(text.split())
        previous_end = 0
        for line in out.splitlines()[1:]:
            match = re.fullmatch(r'\[字符(\d+):(\d+)\] (.*)', line)
            self.assertIsNotNone(match)
            start, end = int(match[1]), int(match[2])
            self.assertGreaterEqual(start, previous_end)
            self.assertEqual(match[3], compact[start:end])
            previous_end = end

    def test_archive_qualification_remains_next_to_old_quote(self):
        text = '复习地点白桦，暗号已撤销。' + '整理材料。' * 200 + '以下只引用旧记录，不恢复约定。复习地点青石，暗号晴鸟。归档引用完毕。'
        out = budgeted_query_windows(text, '复习地点和暗号')
        self.assertIn('以下只引用旧记录，不恢复约定。复习地点青石，暗号晴鸟。归档引用完毕。', out)
        self.assertIn('复习地点白桦，暗号已撤销。', out)

    def test_french_revocation_is_retained_without_translation(self):
        text = 'Le lieu est la salle Pierre-Verte. Le mot de passe est Oiseau.' + ' Exercice de calcul.' * 200 + 'Correction : le lieu devient la salle Bouleau. Le mot de passe est révoqué, sans remplacement.'
        out = budgeted_query_windows(text, 'lieu et mot de passe actuel')
        self.assertLessEqual(len(out), 800)
        self.assertIn('salle Bouleau', out)
        self.assertIn('révoqué, sans remplacement', out)

    def test_no_match_and_short_text_do_not_invent_facts(self):
        self.assertEqual(budgeted_query_windows('  A short note.  ', '地点'), 'A short note.')
        out = budgeted_query_windows('x' * 2000, '地点')
        self.assertEqual(out, 'x' * 797 + '...')
