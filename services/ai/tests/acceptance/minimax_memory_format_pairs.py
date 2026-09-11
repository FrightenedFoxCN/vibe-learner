"""Fixed-seed Study format experiment; explicit two-line request shape only."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

from app.services import provider_study
from tests.acceptance.minimax_memory_excerpt_probe import run

SHAPE = (
    '\n本实验本轮用户明确要求只用两条Markdown无序列表。text字段必须恰好两行，'
    '每行以减号和空格开头；不得再有标题、开场、结尾、空白行或嵌套列表。'
    '需要报告的多项事实可用分号合并在同一行，不能为满足两行而遗漏撤销信息。'
    'text的形状是「- 第一项内容\\n- 第二项内容」，这不是要照抄的内容。'
    '称呼可置于列表项内，动作和情绪仍放在各自字段。'
)


FACT_SCOPE = (
    '\n读取记忆证据时，将每条事实绑定到原文明确的对象和时间范围。'
    '地点或约定改变后，不要把旧对象的经历状态自动转移给新对象。'
    '原文未记录某事发生，不等于证明它从未发生；节选没有覆盖的经历应保持未知。'
    '不需要回答的经历可以省略，需要回答时区分明确否定与没有证据。'
)


def compare(source: Path, output: Path, *, ablation: bool = False, fact_scope: bool = False):
    output.mkdir(parents=True, exist_ok=False)
    original = provider_study._chat_prompt_sections
    rows = []
    baseline_evidence = None
    conditions = (["baseline", "outer_only", "shape_only", "combined", "combined", "shape_only", "outer_only", "baseline"]
                  if ablation else ["baseline", "combined", "combined", "baseline"])
    if fact_scope:
        conditions = ["combined", "scoped", "scoped", "combined"]
    for i, condition in enumerate(conditions):
        candidate = condition != "baseline"
        def sections():
            result = original()
            if not candidate:
                return result
            return {key: (value.replace('不要 markdown', '不要在JSON对象外使用Markdown')
                          if condition in {'outer_only', 'combined', 'scoped'} else value) +
                    (SHAPE if condition in {'shape_only', 'combined', 'scoped'} and
                     key in {'system', 'tool_followup', 'recovery'} else '') +
                    (FACT_SCOPE if condition == 'scoped' and key in {'system', 'tool_followup', 'recovery'} else '')
                    for key, value in result.items()}
        cell = output / f'{i}-{int(candidate)}'
        with patch.object(provider_study, '_chat_prompt_sections', sections):
            run(source, cell, 1, production=True)
        row = json.loads((cell/'report.jsonl').read_text())
        evidence = row['candidate_excerpts']
        if baseline_evidence is None:
            baseline_evidence = evidence
        row.update(format_candidate=candidate, format_condition=condition,
                   experimental_shape_instruction=SHAPE if condition in {"shape_only", "combined", "scoped"} else None,
                   experimental_fact_scope=FACT_SCOPE if condition == "scoped" else None,
                   fixed_seed_excerpts_equal=evidence==baseline_evidence)
        row['trace_limitation'] += '; candidate prompt changes are experimental, not production adoption.'
        rows.append(row)
        (output/'report.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
        print(json.dumps({'cell':i,'candidate':candidate,'boundary_success':row['boundary_success']}),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--ablation', action='store_true')
    p.add_argument('--fact-scope', action='store_true')
    args=p.parse_args();compare(args.source.resolve(),args.output.resolve(), ablation=args.ablation, fact_scope=args.fact_scope)
