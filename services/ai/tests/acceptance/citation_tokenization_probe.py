"""Diagnostic lexical precision/recall examples; not semantic citation grading."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

from app.services.study_memory import _tokenize as memory_tokens
from tests.test_study_citation_evidence import cite, report


CASES = [
    ('zh_relevant', '请解释一元一次方程。', '一元一次方程含有一个未知数，未知数的次数为一。', True),
    ('zh_shared_polite_phrase', '请说明这个约定的取消时间。', '这个等式的两边同时减去三，结果不变。', False),
    ('en_relevant', 'Explain subtracting.', 'Balance both sides when subtracting.', True),
    ('en_shared_function_words', 'What is the cancellation date?', 'A linear equation is written with one variable.', False),
    ('fr_relevant', 'Expliquez la dérivée.', 'La dérivée mesure le taux de variation.', True),
    ('fr_unrelated_substring', 'Quand Camille a annulé le rendez-vous ?', 'Une variable peut prendre plusieurs valeurs.', False),
    ('unrelated_memory', '请核对林舟与阿岚的取消发生时间和记录时间。', 'A linear equation has one variable.', False),
]


def diagnose():
    rows = []
    for name, query, text, relevant in CASES:
        for variant in ('current', 'memory_tokenizer'):
            if variant == 'memory_tokenizer':
                with patch('app.services.pedagogy._tokenize', memory_tokens):
                    citations = cite(report([text]), query)
            else:
                citations = cite(report([text]), query)
            rows.append({'case': name, 'variant': variant, 'query': query, 'source': text,
                         'relevant': relevant, 'cited': bool(citations),
                         'matches_reviewed_relevance': bool(citations) == relevant})
    return {'scope': 'Synthetic lexical diagnostic only; no provider or domain commit',
            'limitation': 'Curated counterexamples, not representative precision/recall estimates.',
            'rows': rows}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.output.open('x') as stream:
        json.dump(diagnose(), stream, ensure_ascii=False, indent=2)
        stream.write('\n')
