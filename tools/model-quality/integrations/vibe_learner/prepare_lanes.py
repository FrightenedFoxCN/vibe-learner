"""Freeze the priority citation and cross-session memory experiments."""
import argparse
import json
from pathlib import Path
from model_quality.protocol import Campaign
from .prepare_quality import matrix
from .citation_cases import cases as citation_cases
from .temporal_cases import cases as temporal_cases
from .write_cases import cases as write_cases


def campaign(lane,transport='fake',budget=None,identifier=None):
    c=matrix(transport,budget,identifier or 'priority-'+lane).model_dump()
    c.update(adapter='vibe_learner.'+lane+':run_sample',repetitions=1,max_output_tokens=4096,thinking='adaptive',
        sample_wire_limit=12,sample_deadline_seconds=600,purpose='Priority '+lane+' development diagnostic; synthetic independently authored sources, not independently reviewed holdout')
    c['cases']=(citation_cases()+temporal_cases()+write_cases()) if lane=='mixed' else {'citation':citation_cases,'temporal':temporal_cases,'verbatim':write_cases}[lane]()
    if lane=='mixed':
        c['cases']=[{**case,'id':case['lane']+'-'+case['id'],'family':case['lane']+'-'+case['family']} for case in c['cases']]
    c['variants']=[{'id':name,'instruction':'遵守本轮要求。'} for name in
        {'citation':('baseline','normalized'),'temporal':('baseline','oracle-context'),'verbatim':('baseline','source-binding'),'mixed':('baseline','candidate')}[lane]]
    if budget is None:c['budget'].update(wire_limit=2000,token_limit=50000000)
    if lane=='mixed':c['adapter']='vibe_learner.priority:run_sample'
    if lane=='verbatim':c['adapter']='vibe_learner.write_binding:run_sample'
    return Campaign.model_validate(c)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--lane',choices=['citation','temporal','verbatim','mixed'],required=True)
    parser.add_argument('--transport',choices=['fake','minimax'],default='fake')
    parser.add_argument('--budget-from',type=Path)
    parser.add_argument('--id')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    budget=json.loads(args.budget_from.read_text())['budget'] if args.budget_from else None
    c=campaign(args.lane,args.transport,budget,args.id)
    with args.output.open('x') as stream:stream.write(c.model_dump_json(indent=2)+'\n')
    print(args.output.resolve())


if __name__=='__main__':
    main()
