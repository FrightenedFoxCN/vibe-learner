"""Planning page excerpts respect the requested character budget including joins."""
import unittest

from app.models.domain import DocumentChunkRecord, DocumentDebugRecord
from app.models.planning import ReadPageRangeContentArgumentsV1
from app.services.plan_prompt import read_page_range_content


def report(texts):
    chunks = [DocumentChunkRecord(id=str(i), document_id='doc', section_id='section',
        page_start=1, page_end=1, char_count=len(text), text_preview=text, content=text)
        for i, text in enumerate(texts)]
    return DocumentDebugRecord(document_id='doc', parser_name='test', processed_at='test',
        page_count=1, total_characters=sum(len(t) for t in texts), extraction_method='native',
        pages=[], sections=[], chunks=chunks, warnings=[], dominant_language_hint='fr')


class PlanTextPageBudgetTests(unittest.TestCase):
    def test_first_large_chunk_respects_valid_model_budget(self):
        text = 'é中文' * 600
        args = ReadPageRangeContentArgumentsV1(page_start=1, page_end=1, max_chars=500)
        result = read_page_range_content(debug_report=report([text]), **args.model_dump())
        self.assertEqual(result['content'], text[:500])

    def test_separator_is_part_of_budget(self):
        result = read_page_range_content(debug_report=report(['a' * 800, 'b' * 800]),
                                         page_start=1, page_end=1, max_chars=1000)
        self.assertEqual(result['content'], 'a' * 800 + '\n\n' + 'b' * 198)
        self.assertEqual(result['chunk_count'], 2)

    def test_exact_fit_and_short_tail_policy(self):
        result = read_page_range_content(debug_report=report(['a' * 250, 'b' * 248]),
                                         page_start=1, page_end=1, max_chars=500)
        self.assertEqual(len(result['content']), 500)
        result = read_page_range_content(debug_report=report(['a' * 420, 'b' * 200]),
                                         page_start=1, page_end=1, max_chars=500)
        self.assertEqual(result['content'], 'a' * 420)

    def test_empty_and_unmatched_sources_stay_empty(self):
        for debug in (None, report(['text'])):
            result = read_page_range_content(debug_report=debug, page_start=2, page_end=2, max_chars=500)
            self.assertEqual(result['content'], '')
            self.assertEqual(result['chunk_count'], 0)
