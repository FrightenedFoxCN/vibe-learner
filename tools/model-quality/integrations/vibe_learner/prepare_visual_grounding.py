"""Prepare immutable development fixtures/campaign; never calls a provider."""
import argparse,json
from pathlib import Path
from model_quality.protocol import Campaign
from .visual_grounding_fixtures import build_fixtures

def main():
    p=argparse.ArgumentParser();p.add_argument('--budget-from',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--fixtures',type=Path,required=True);p.add_argument('--id',default='m3-visual-grounding-20260912-v1');p.add_argument('--transport',choices=['fake','minimax'],default='fake');p.add_argument('--cases',default='');a=p.parse_args()
    if a.output.exists() or a.fixtures.exists():raise ValueError('new_output_and_fixture_paths_required')
    cases=build_fixtures(a.fixtures,include_diagnostic='gray-circle' in a.cases.split(','))
    if a.cases:
        ids=set(a.cases.split(','));cases=[c for c in cases if c['id'] in ids]
        if len(cases)!=len(ids):raise ValueError('unknown_case')
    data=dict(version='quality-campaign-v1',id=a.id,purpose='New synthetic visual grounding: direct normalized box versus real image-only OCR/color component proposals and numbered selection; proposal-only development, no expert/heldout certification.',transport=a.transport,adapter='vibe_learner.visual_grounding:run_sample',concurrency=4,repetitions=1,seed=912,timeout_seconds=60,sample_deadline_seconds=180,sample_wire_limit=1,max_output_tokens=2048,input_reservation_tokens=100000,max_inline_images=2,thinking='adaptive',temperature=.1,budget=json.loads(a.budget_from.read_text())['budget'],cases=cases,variants=[dict(id='direct',instruction='Direct full-image bounding box'),dict(id='som',instruction='Image-only local proposals and numbered model selection')])
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(Campaign.model_validate(data).model_dump_json(indent=2)+'\n')
if __name__=='__main__':main()
