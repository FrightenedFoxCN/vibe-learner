"""Application-owned, source-bound chart delivery for the bounded role experiment.

This is not a production attachment contract or a general natural-language checker.
Only structured questions are delivered in the chart lane; prose remains a proposal.
"""
import hashlib
import html
import json
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, ConfigDict, StrictInt, StrictStr, TypeAdapter, model_validator

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)

class ChartSource(StrictModel):
    kind: Literal['bar-chart-source-v1']
    labels: list[StrictStr]
    values: list[StrictInt]
    @model_validator(mode='after')
    def valid(self):
        if (not 2 <= len(self.labels) <= 8 or len(set(self.labels)) != len(self.labels)
                or len(self.values) != len(self.labels) or any(not x or len(x)>24 for x in self.labels)
                or any(not 0 <= x <= 100 for x in self.values) or max(self.values) == 0):
            raise ValueError('invalid_chart_source')
        return self

class ChartQuestion(StrictModel):
    operation: Literal['maximum', 'difference']
    labels: list[StrictStr]

class ArtifactRequirement(StrictModel):
    kind: Literal['bar-chart-delivery-v1'] = 'bar-chart-delivery-v1'
    source_sha256: StrictStr
    source: ChartSource
    required_questions: list[ChartQuestion]

class Delivery(StrictModel):
    version: Literal['role-chart-delivery-v1'] = 'role-chart-delivery-v1'
    source_sha256: StrictStr
    prompt: StrictStr
    questions: list[ChartQuestion]
    chart_path: Literal['chart.svg'] = 'chart.svg'
    chart_sha256: StrictStr
    data_path: Literal['chart-data.json'] = 'chart-data.json'
    data_sha256: StrictStr
    page_path: Literal['learner.html'] = 'learner.html'
    page_sha256: StrictStr

def digest(value):
    return hashlib.sha256(value).hexdigest()

def canonical(source):
    return (json.dumps(source.model_dump(), ensure_ascii=False, sort_keys=True, separators=(',', ':'))+'\n').encode()

def requirement(source):
    # Explicit source-data marker belongs to controlled application case input,
    # never grading facts or a provider-authored artifact reference.
    marker='\nCHART_SOURCE_JSON:\n'
    if marker not in source:
        return None
    data, separator, question_data=source.split(marker, 1)[1].partition('\nCHART_QUESTION_REQUIREMENTS_JSON:\n')
    if not separator:
        raise ValueError('missing_chart_question_requirements')
    parsed=ChartSource.model_validate_json(data)
    questions=TypeAdapter(list[ChartQuestion]).validate_json(question_data,strict=True)
    render_prompt(parsed,questions)
    return ArtifactRequirement(source_sha256=digest(source.encode()),source=parsed,required_questions=questions)

def render_chart(source):
    bars=[]
    for i,(label,value) in enumerate(zip(source.labels,source.values)):
        x=70+i*70; height=value/max(source.values)*200
        bars.append(f'<rect x="{x}" y="{250-height:g}" width="42" height="{height:g}" fill="#315b9a"/><text x="{x+21}" y="{240-height:g}" text-anchor="middle">{value}</text><text x="{x+21}" y="275" text-anchor="middle">{html.escape(label)}</text>')
    width=100+70*len(source.labels)
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="310" viewBox="0 0 {width} 310"><rect width="100%" height="100%" fill="white"/><g font-family="sans-serif" font-size="16" fill="#182333"><text x="20" y="25">Chart reading</text><path d="M50 40V250H{width-10}" stroke="#182333" fill="none"/><text x="35" y="255">0</text>'+''.join(bars)+'</g></svg>').encode()

def render_prompt(source, questions):
    if not questions:
        raise ValueError('missing_chart_questions')
    parts=[]
    for q in questions:
        if any(label not in source.labels for label in q.labels):
            raise ValueError('unknown_chart_label')
        if q.operation=='maximum':
            if q.labels != source.labels:
                raise ValueError('maximum_requires_all_source_labels')
            parts.append('Using the attached chart, which category has the largest value?')
        elif len(q.labels)==2 and q.labels[0]!=q.labels[1]:
            parts.append(f'Using the attached chart, calculate the value of {q.labels[0]} minus {q.labels[1]}.')
        else:
            raise ValueError('difference_requires_two_distinct_labels')
    return '\n'.join(parts)

def render_page(prompt):
    return ('<!doctype html><html lang="en"><meta charset="utf-8"><title>Chart reading activity</title><main><h1>Chart reading activity</h1><img src="chart.svg" alt="Bar chart with category labels and numeric values"><p>'+html.escape(prompt).replace('\n','</p><p>')+'</p></main></html>').encode()

def build_delivery(root, req, questions):
    root=Path(root)
    if questions != req.required_questions:
        raise ValueError('chart_task_questions_incomplete_or_changed')
    prompt=render_prompt(req.source,questions)
    chart=render_chart(req.source); data=canonical(req.source); page=render_page(prompt)
    for name,content in [('chart.svg',chart),('chart-data.json',data),('learner.html',page)]:
        (root/name).write_bytes(content)
    delivery=Delivery(source_sha256=req.source_sha256,prompt=prompt,questions=questions,
        chart_sha256=digest(chart),data_sha256=digest(data),page_sha256=digest(page))
    (root/'delivery.json').write_text(delivery.model_dump_json(indent=2)+'\n')
    return delivery

def validate_delivery(root, req):
    """Read back manifest and actual files; recompute expected rendering from source.

A file/digest or model claim alone cannot establish delivery or correct data.
"""
    root=Path(root)
    try:
        delivery=Delivery.model_validate_json((root/'delivery.json').read_text())
        if delivery.source_sha256!=req.source_sha256:
            raise ValueError('source_binding_mismatch')
        if delivery.questions != req.required_questions:
            raise ValueError('chart_task_questions_incomplete_or_changed')
        prompt=render_prompt(req.source,delivery.questions)
        if delivery.prompt!=prompt:
            raise ValueError('prompt_dependency_mismatch')
        expected=[('chart.svg',render_chart(req.source),delivery.chart_sha256),
                  ('chart-data.json',canonical(req.source),delivery.data_sha256),
                  ('learner.html',render_page(prompt),delivery.page_sha256)]
        for name,content,sha in expected:
            path=root/name
            if path.is_symlink() or path.read_bytes()!=content or digest(content)!=sha:
                raise ValueError('artifact_content_mismatch')
        return {'valid':True,'error':None}
    except (ValueError,OSError) as exc:
        return {'valid':False,'error':str(exc)}

def export_delivery_bundle(root, req):
    """Export actual validated UTF-8 assets inside runner-compatible JSON evidence."""
    root=Path(root)
    check=validate_delivery(root,req)
    if not check['valid']:
        raise ValueError('cannot_export_invalid_delivery')
    delivery=Delivery.model_validate_json((root/'delivery.json').read_text())
    files=[]
    for name,mime,sha in [('chart.svg','image/svg+xml',delivery.chart_sha256),
            ('chart-data.json','application/json',delivery.data_sha256),
            ('learner.html','text/html',delivery.page_sha256)]:
        content=(root/name).read_bytes()
        if digest(content)!=sha:
            raise ValueError('artifact_changed_during_export')
        files.append({'path':name,'mime_type':mime,'encoding':'utf-8',
                      'sha256':sha,'content':content.decode('utf-8')})
    bundle={'version':'role-chart-artifact-bundle-v1','requirement':req.model_dump(),
            'delivery':delivery.model_dump(),'files':files}
    (root/'artifact-bundle.json').write_text(json.dumps(bundle,ensure_ascii=False,indent=2)+'\n')
    return bundle
