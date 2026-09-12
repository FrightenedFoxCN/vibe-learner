"""Replay source selection on frozen synthetic debug DTOs, without model calls."""
import argparse
from collections import Counter
import json
from pathlib import Path
from unittest.mock import patch
from app.models.domain import DocumentDebugRecord
from app.services import pedagogy
from vibe_learner.citation import normalized_tokens


def audit(root):
    manifest=json.loads((root/'manifest.json').read_text());report=json.loads((root/'report.json').read_text())
    cases={c['id']:c for c in manifest['config']['cases']}
    groups={};rows=[]
    for sample in report['samples']:
        case=cases[sample['case']]
        if case['lane']!='citation':continue
        source=json.loads(case['source']);variant=sample['variant']
        e=json.loads((root/sample['case']/variant/str(sample['repetition'])/'storage/domain-evidence.json').read_text())
        debug=DocumentDebugRecord.model_validate(e['document_debug']);unit=debug.study_units[0]
        kwargs={'debug_report':debug,'study_unit_id':unit.id,'study_unit_title':unit.title,'message':case['request']}
        if variant=='candidate':
            with patch.object(pedagogy,'_tokenize',normalized_tokens):selected=pedagogy._build_grounded_citations(**kwargs)
        else:selected=pedagogy._build_grounded_citations(**kwargs)
        serialized=[c.model_dump(mode='json') for c in selected]
        observed=e.get('citation_selection',[])
        agree=None if not observed else serialized==observed[-1]['selected']
        if agree is False:raise ValueError('post-hoc selector differs from actual execution')
        receipt=e['operations'][-1]['receipt'];committed=receipt['status']=='committed'
        public=((receipt.get('result') or {}).get('session') or {}).get('turns',[])
        returned=public[-1]['citations'] if public else []
        g=groups.setdefault(variant,{'offline':Counter(),'committed':Counter(),'unavailable':0})
        def label(citations):return ('positive_hit' if citations else 'positive_miss') if source['relevant'] else ('irrelevant_citation' if citations else 'correct_no_citation')
        g['offline'][label(serialized)]+=1
        if committed:g['committed'][label(returned)]+=1
        else:g['unavailable']+=1
        rows.append({'case':sample['case'],'variant':variant,'sample_id':sample['sample_id'],'relevant':source['relevant'],
            'committed':committed,'offline_citations':serialized,'matches_observed_selector':agree,
            'persisted_citations':returned if committed else None,
            'effective_citation_metric_eligible':committed})
    return {'version':'citation-selection-replay-v1','groups':groups,'rows':rows,
        'scope':'Post-hoc deterministic source-selection replay; no provider calls or new domain effects. Task relevance is gold-labelled source relevance, not an independent NLI/entailment annotation. Noncommitted samples are unavailable, never correct abstentions.'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--campaign-dir',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.write_text(json.dumps(audit(a.campaign_dir),ensure_ascii=False,indent=2)+'\n');print(a.output.resolve())


if __name__=='__main__':main()
