"""Provider-free synthetic diagnostics; expose known excerpt limits without hiding failures."""
import argparse
import json
import time
from pathlib import Path

from app.services.memory_excerpt import select_memory_excerpt
from app.services.study_memory import _tokenize

FRENCH = ('Le lieu est la salle Pierre-Verte. Le mot de passe est Oiseau.' +
          ' Exercice de calcul.' * 200 +
          'Correction : le lieu devient la salle Bouleau. Le mot de passe est révoqué, sans remplacement.')
CASES = [
    ('unpunctuated_chinese', '复习地点青石暗号晴鸟' + '整理材料' * 600 + '地点改为南门暗号全部撤销', '复习地点和暗号', '南门'),
    ('oversized_preceding_sentence', '复习地点青石，暗号晴鸟。' + '整理材料' * 600 + '。地点改为南门，暗号全部撤销。', '复习地点和暗号', '南门'),
    ('cross_language_query', FRENCH, '复习地点和暗号', 'Bouleau'),
    ('same_language_control', FRENCH, 'lieu et mot de passe actuel', 'Bouleau'),
]


def diagnose():
    rows = []
    for name, text, query, expected in CASES:
        start = time.perf_counter()
        excerpt = select_memory_excerpt(text, query, tokenize=_tokenize)
        rows.append(dict(case=name, input_chars=len(text), query=query, expected_fragment=expected,
                         retained=expected in excerpt, excerpt_chars=len(excerpt),
                         elapsed_ms=round((time.perf_counter()-start)*1000, 3), excerpt=excerpt))
    return rows


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    with args.output.open('x') as stream:
        json.dump(diagnose(), stream, ensure_ascii=False, indent=2)
        stream.write('\n')
