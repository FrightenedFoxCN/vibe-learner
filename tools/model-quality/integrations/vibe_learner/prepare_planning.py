"""Prepare 12 bounded synthetic planning comparisons, never dispatch implicitly."""
import argparse
import json
from pathlib import Path
from model_quality.protocol import Campaign
from .fixtures import campaign as base

SOURCES = [
('equations', 'Chapter 1 Linear Equations\nA linear equation is ax + b = c, where a is nonzero.\nSubtract b, then divide by a. For 2x + 3 = 11, x = 4.\nDivision by zero is forbidden.\n---PAGE---\nChapter 2 Verification\nSubstitute x = 4: 2 times 4 plus 3 equals 11.\nFor a = 0, check whether b = c; never divide by a.\nExercise: solve 3x + 2 = 14 and verify the answer.', '先等式变形，再代入检验；强调 a 非零，禁止除零。'),
('probability', 'Chapter 1 A Bag Experiment\nA bag contains 2 red balls and 3 blue balls.\nDraw one ball uniformly: P(red) = 2/5.\nReturn the ball before the next draw.\n---PAGE---\nChapter 2 Changing the Rule\nWithout replacement, after one red ball, 1 red and 3 blue remain.\nThe next red probability is 1/4.\nWith replacement it remains 2/5. Compare these two experiments.', '先单次抽球，再比较放回与不放回；不能把第二次概率都写成 2/5。'),
('python', 'Chapter 1 Lists\nA list preserves item order. Indexing starts at zero.\nExample: names = ["Ada", "Lin"]; names[0] is "Ada".\nPractice access and append before loops.\n---PAGE---\nChapter 2 Dictionaries\nA dictionary maps unique keys to values.\nExample: scores = {"Ada": 8}; scores["Ada"] is 8.\nKeys are not list positions. Compare lookup by position and lookup by key.', '从零学习，先列表索引再字典键；不要求循环或编造后续章节。')]

def campaign(transport='fake', budget=None, identifier='planning-evidence-v1'):
    c = base('study', transport, identifier, budget).model_dump()
    c.update(adapter='vibe_learner.planning:run_sample', purpose='Three synthetic planning sources paired evidence-first versus unchanged planning; real admission and restart readback',
        concurrency=4, autoscale=None, repetitions=2, sample_wire_limit=8, sample_deadline_seconds=600, timeout_seconds=60,
        max_output_tokens=4096, input_reservation_tokens=100000, thinking='adaptive',
        cases=[{'id': name, 'family': name, 'lane': 'planning', 'provenance': 'synthetic-authored', 'source': source,
                'request': '请用中文，仅根据这两页教材安排学习。' + goal, 'gold': json.dumps({'source_pages': 2, 'goal': goal}, ensure_ascii=False),
                'rubric': 'planning-grounded-boundary-v1'} for name, source, goal in SOURCES],
        variants=[{'id': 'baseline', 'instruction': 'Unchanged production tool choice.'},
                  {'id': 'evidence-first', 'instruction': 'Force read_page_range_content on the first provider request only.'}])
    return Campaign.model_validate(c)

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--transport', choices=['fake', 'minimax'], default='fake'); p.add_argument('--budget-from', type=Path)
    p.add_argument('--id', default='planning-evidence-v1'); p.add_argument('--output', type=Path, required=True)
    a = p.parse_args(); budget = json.loads(a.budget_from.read_text())['budget'] if a.budget_from else None
    with a.output.open('x') as f: f.write(campaign(a.transport, budget, a.id).model_dump_json(indent=2) + '\n')
