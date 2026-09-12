"""Prepare a separate bounded summary-fact writing comparison."""
import argparse
import json
from pathlib import Path
from model_quality.protocol import Campaign
from .prepare_quality import matrix
from .summary_cases import cases


def campaign(transport='fake',budget=None,identifier='summary-facts-v1'):
    c=matrix(transport,budget,identifier).model_dump()
    c.update(adapter='vibe_learner.write_summary:run_sample',cases=cases(),repetitions=1,
        max_output_tokens=4096,thinking='adaptive',sample_wire_limit=8,
        purpose='Separate summary facts from verbatim character grading; 8 development scenarios, two instruction arms',
        variants=[{'id':'baseline','instruction':'遵守本轮要求。'},
                  {'id':'fact-focus','instruction':'先区分人物角色、事件时间和记录时间、未知值和未确认状态。摘要字段只能使用原话支持的事实，不把取消改成延期，也不把第三方经历改成我们的经历。实际写入并读回成功后再声称完成。'}])
    return Campaign.model_validate(c)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--transport',choices=['fake','minimax'],default='fake')
    p.add_argument('--budget-from',type=Path);p.add_argument('--id',default='summary-facts-v1');p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();budget=json.loads(a.budget_from.read_text())['budget'] if a.budget_from else None
    c=campaign(a.transport,budget,a.id)
    with a.output.open('x') as stream:stream.write(c.model_dump_json(indent=2)+'\n')
    print(a.output.resolve())


if __name__=='__main__':main()
