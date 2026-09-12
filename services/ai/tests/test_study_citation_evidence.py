"""A current chapter is not itself evidence for an unrelated answer."""
import unittest

from app.models.domain import DocumentChunkRecord, DocumentDebugRecord, StudyUnitRecord
from app.services.pedagogy import _build_grounded_citations


def report(chunks):
    return DocumentDebugRecord(document_id='doc', parser_name='test', processed_at='2026-06-01T00:00:00Z',
        page_count=2, total_characters=100, extraction_method='text', pages=[], sections=[],
        study_units=[StudyUnitRecord(id='unit', document_id='doc', title='Equations', page_start=1, page_end=2,
                                    source_section_ids=['section'])], chunks=[
            DocumentChunkRecord(id=f'chunk-{i}', document_id='doc', section_id='section',
                page_start=i + 1, page_end=i + 1, char_count=len(text), text_preview=text, content=text)
            for i, text in enumerate(chunks)], warnings=[], dominant_language_hint='en')


def cite(source, message):
    return _build_grounded_citations(debug_report=source, study_unit_id='unit',
                                     study_unit_title='Equations', message=message)


class StudyCitationEvidenceTests(unittest.TestCase):
    def test_no_document_cannot_supply_a_page_citation(self):
        self.assertEqual(cite(None, 'Explain equations'), [])

    def test_memory_request_does_not_cite_unrelated_equations(self):
        self.assertEqual(cite(report(['A linear equation has one variable.']),
            '请核对林舟与阿岚的取消发生时间和记录时间。'), [])

    def test_no_chunks_cannot_supply_a_unit_range_as_evidence(self):
        self.assertEqual(cite(report([]), 'Explain equations'), [])

    def test_matched_chunk_does_not_drag_in_zero_match_neighbor(self):
        result = cite(report(['Balance both sides when subtracting.', 'Graph coordinates on paper.']), 'subtracting')
        self.assertEqual([(c.page_start, c.page_end) for c in result], [(1, 1)])
