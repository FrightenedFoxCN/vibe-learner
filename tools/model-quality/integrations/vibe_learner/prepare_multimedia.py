"""Freeze twelve paired multimedia development cases."""
import argparse,json
from pathlib import Path
from model_quality.protocol import Campaign
from .fixtures import campaign
from .multimedia import CASES,SOURCE

def main():
    p=argparse.ArgumentParser();p.add_argument('--budget-from',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--transport',default='minimax',choices=['fake','minimax'])
    a=p.parse_args();c=campaign('study',a.transport,'m3-multimedia-pairs-20260912',json.loads(a.budget_from.read_text())['budget']).model_dump()
    c.update(adapter='vibe_learner.multimedia:run_sample',concurrency=4,autoscale=None,repetitions=1,max_inline_images=4,max_output_tokens=4096,input_reservation_tokens=100000,sample_wire_limit=8,timeout_seconds=60,sample_deadline_seconds=600,thinking='adaptive',temperature=.1,
        purpose='Six synthetic multimedia tasks paired baseline/evidence-first; actual tool execution, typed effect and restart readback; development diagnostics, no independent heldout certification.',
        cases=[{'id':i,'family':'linear-equation-single-source','lane':kind,'provenance':'synthetic-authored','source':SOURCE,'request':request,'gold':gold,'rubric':'multimedia-effects-v1'} for i,kind,request,gold in CASES],
        variants=[{'id':'baseline','instruction':'遵守本轮要求。'},{'id':'evidence-first','instruction':'先检查当前任务目标及实际附件信息。依次完成必要工具，逐条核对工具 ok 和返回内容；prepared 仅表示待提交，最终回复应提交本轮结果，不提前声称已提交。框选坐标以实际图片尺寸归一化到 0..1。互动题的答案与解析只留在服务端评分字段，最终 text 不复述答案。最后只交付本轮明确要求的内容。'}])
    a.output.write_text(Campaign.model_validate(c).model_dump_json(indent=2)+'\n')
if __name__=='__main__':main()
