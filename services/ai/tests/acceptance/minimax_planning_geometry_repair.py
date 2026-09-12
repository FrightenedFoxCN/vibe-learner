"""Live M3 repair with a synthetic invalid initial proposal and real domain admission."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.models.domain import PlanGenerationTraceRecord
from app.models.planning import LearningPlanProposalV1
from app.services.provider_planning import RemotePlanningProvider
from tests.acceptance.minimax_planning_probe import run


def invalid_geometry(unit, kind):
    def chapter(start, end):
        return {'title': f'第{start}至{end}页阅读', 'anchor_page_start': start, 'anchor_page_end': end,
                'source_section_ids': [], 'content_slices': [{'page_start': start, 'page_end': end, 'source_section_ids': []}]}
    if kind == 'chapter_order':
        chapters = [chapter(2,2), chapter(1,1)]
    else:
        chapters = [chapter(1,2)]
        chapters[0]['content_slices'] = [chapter(2,2)['content_slices'][0], chapter(1,1)['content_slices'][0]]
    proposal = {'schema_name':'learning-plan-proposal', 'schema_version':'learning-plan-proposal-v1',
                'course_title':'两页阅读活动', 'overview':'核对正文、插图与推测的边界。',
                'today_tasks':['根据学习目标安排各阶段，并核对页码与证据。'],
                'schedule':[{'unit_id':unit.id, 'title':'阅读与核对', 'focus':'按目标安排阅读活动。',
                             'activity_type':'learn', 'schedule_chapters':chapters}]}
    # It is strict schema-valid; only the cross-chapter/slice order is intentionally wrong.
    return LearningPlanProposalV1.model_validate(proposal).model_dump_json()


def compare(source, pdf, output):
    output.mkdir(parents=True, exist_ok=False)
    objective = json.loads((source/'report.jsonl').read_text().splitlines()[0])['objective']
    original = RemotePlanningProvider._run_plan_model
    rows = []
    for kind in ('chapter_order', 'slice_order'):
        invocations = []
        def injected(provider, **kwargs):
            invocations.append({'tools_enabled': kwargs['tool_runtime'].has_tools(),
                                'repair_request': '上一次最终计划未通过' in str(kwargs['messages'][-1].get('content'))})
            if len(invocations) == 1:
                units = kwargs['tool_runtime'].current_study_units()
                assert len(units) == 1 and units[0].page_start == 1 and units[0].page_end == 2
                return SimpleNamespace(content=invalid_geometry(units[0], kind), tool_messages=[],
                    trace=PlanGenerationTraceRecord(document_id=kwargs['document_id'], model='synthetic-invalid-proposal',
                        created_at=datetime.now(timezone.utc).isoformat()))
            return original(provider, **kwargs)
        cell = output/kind
        with patch.object(RemotePlanningProvider, '_run_plan_model', injected):
            run(cell, 1, selected_case='document', pdf_path=pdf, objective_override=objective,
                multimodal=True, persona_variant='rigorous', persona_domain='text',
                page_evidence='text_image', page_evidence_page=2, page_evidence_dpi=144,
                controlled_page_evidence=True, prepared_source_root=source)
        row = json.loads((cell/'report.jsonl').read_text())
        row['fault_injection'] = {'kind':kind, 'synthetic_initial_proposal':True,
                                 'runner_invocations':invocations, 'real_provider_calls':len(row['calls'])}
        row['trace_limitation'] = ('Fault-injected schema-valid initial proposal, not natural M3 generation. '
            'Only repair calls are real; production domain admission/validation/commit/readback remain exercised. '
            'Page image is experimental SDK injection; no independent quality certification.')
        rows.append(row)
        (output/'report.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
        print(json.dumps({'kind':kind,'boundary_success':row['boundary_success'],'real_calls':len(row['calls'])}),flush=True)


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source',type=Path,required=True);p.add_argument('--pdf',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    compare(a.source.resolve(),a.pdf.resolve(),a.output.resolve())
