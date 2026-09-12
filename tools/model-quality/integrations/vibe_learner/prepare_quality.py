"""Freeze a bounded multilingual verbatim-memory paired experiment, no network."""
import argparse
import json
import time
from pathlib import Path
from .fixtures import campaign
from model_quality.protocol import Campaign


SOURCES = [
    ('fr-punctuation', 'punctuation', 'Camille a rendez-vous le 10 juin à 16:00. Le lieu n’est pas précisé.'),
    ('en-quotes', 'punctuation', 'Mira wrote: “Don’t replace my punctuation.” The room is unspecified.'),
    ('zh-cancel', 'state', '林舟原定周五下午三点参加讨论，后来取消。没有安排新的日期，也没有确定地点。'),
    ('en-reactivate', 'state', 'The amber project was archived on May 2 and reactivated on May 9. Its launch date remains unknown.'),
    ('fr-negation', 'negation', 'Noé ne part pas lundi. Léa part mardi, mais sa destination n’est pas connue.'),
    ('zh-scope', 'negation', '周宁说“也许下周参加”，这不是确认出席。陈禾已经确认本周不参加。'),
    ('en-identifiers', 'exact-values', 'Reference A-017: 0.05 mg; reference A-170: 0.50 mg. These are synthetic labels, not instructions.'),
    ('zh-newlines', 'exact-values', '实验编号：Q-08\n原记录：甲→乙；乙≠丙。\n地点：未知；时间：待定。'),
]


def matrix(transport='fake', budget=None, identifier='memory-pairs-v1', experiment='instruction'):
    data = campaign('study', transport, identifier, budget).model_dump()
    data.update(purpose='MQ-02 multilingual verbatim memory: paired request instruction diagnostic; development cases, no independent holdout claim.',
                concurrency=4, autoscale=None, repetitions=2, seed=912,
                cases=[dict(id=name, family=family, lane='memory', provenance='synthetic-authored',
                    source=source, gold=source, rubric='study-memory-v1',
                    request='请调用 write_session_memory，用 key experiment_reference 原样保存记录，然后调用 read_session_memory 核对。不翻译，不出题。')
                    for name, family, source in SOURCES],
                variants=[{'id':'baseline', 'instruction':'遵守本轮要求。'},
                          {'id':'receipt-aware', 'instruction':'逐字保留换行、数字与标点，不补充地点或日期。必须实际执行写入和读回工具；若未执行或失败，请如实说明未完成，不能仅口头声称保存。'}])
    if experiment != 'instruction':
        data.update(max_output_tokens=4096, adapter='vibe_learner.study_policy:run_sample',
                    purpose='MQ-02 development-only single-factor provider policy diagnostic')
        ids = ['baseline', 'adaptive', 'force-write-first']
        if experiment == 'shape':
            data.update(adapter='vibe_learner.study_wire_shape:run_sample', thinking='adaptive', repetitions=1)
            ids = ['baseline', 'strip-index']
        elif experiment != 'policy':
            raise ValueError('unknown experiment')
        instruction = data['variants'][1]['instruction']
        data['variants'] = [dict(id=name, instruction=instruction) for name in ids]
    if budget is None:
        data['budget'].update(token_limit=20000000, wire_limit=300, rpm=60, tpm=4000000,
                              max_inflight=4, expires_at=time.time()+7200)
    return Campaign.model_validate(data)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--transport', choices=['fake','minimax'], default='fake')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--budget-from', type=Path)
    parser.add_argument('--id', default='memory-pairs-v1')
    parser.add_argument('--experiment', choices=['instruction','policy','shape'], default='instruction')
    args=parser.parse_args()
    budget=json.loads(args.budget_from.read_text())['budget'] if args.budget_from else None
    c=matrix(args.transport,budget,args.id,args.experiment)
    with args.output.open('x') as stream:
        stream.write(c.model_dump_json(indent=2)+'\n')
    print(args.output.resolve())


if __name__=='__main__':
    main()
