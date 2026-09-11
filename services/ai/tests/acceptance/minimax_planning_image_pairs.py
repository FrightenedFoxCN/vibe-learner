"""Same-source Planning image ablation; retain context equality, not source text."""
import argparse
import json
from pathlib import Path
from unittest.mock import patch

from app.services.provider_sdk import ProviderRequestAdapter
from tests.acceptance.minimax_planning_probe import run


OBJECTIVE = (
    "请只依据上传的一页扫描阅读片段，用中文安排一次30分钟的阅读活动，解释本页讨论的核心问题，"
    "并选择本页实际出现的例子来学习；不要扩展成整本书计划，不虚构不可辨认的中文内容或不存在的章节。"
    "活动方式应体现所选人格，保留材料中必要的英文词语以便核对。"
)


def compare(source, pdf, output, transcription=None, modes=None, objective=None, evidence_page=1):
    output.mkdir(parents=True, exist_ok=False)
    original = ProviderRequestAdapter.request_chat_completion
    baseline = None
    comparisons = []
    current = {}

    def observe(adapter, payload, *, request_kind, model):
        nonlocal baseline
        if not current.get("observed"):
            current["observed"] = True
            context = None
            for message in payload.get("messages", []):
                if message.get("role") != "user" or not isinstance(message.get("content"), str):
                    continue
                try:
                    candidate = json.loads(message["content"])
                except ValueError:
                    continue
                if isinstance(candidate, dict) and "learning_goal" in candidate and "persona" in candidate:
                    context = {k: v for k, v in candidate.items() if k != "persona"}
                    break
            if baseline is None and context is not None:
                baseline = context
            current["nonpersona_initial_context_equal"] = context is not None and context == baseline
            current["measurement_error"] = None if context is not None else "initial_context_not_found"
            current["offered_tools"] = [t.get("function", {}).get("name") for t in payload.get("tools", [])]
        return original(adapter, payload, request_kind=request_kind, model=model)

    cells = [("rigorous", "text"), ("explorer", "text_image"), ("explorer", "text"),
             ("rigorous", "text_image"), ("rigorous", "text_image_crops"), ("explorer", "text_image_crops")]
    if modes:
        cells = [(persona, mode) for persona, mode in cells if mode in modes]
    with patch.object(ProviderRequestAdapter, "request_chat_completion", observe):
        for persona, mode in cells:
            current = {"persona": persona, "mode": mode}
            root = output / f"{persona}-{mode}"
            run(root, 1, selected_case="document", pdf_path=pdf, objective_override=objective or OBJECTIVE,
                ocr_engine="onnxtr", multimodal=True, persona_variant=persona,
                page_evidence=mode, page_evidence_page=evidence_page, persona_domain="text",
                controlled_page_evidence=True, prepared_source_root=source, transcription_file=transcription)
            row = json.loads((root / "report.jsonl").read_text().splitlines()[0])
            current["operation_id"] = row.get("harness_operation_id")
            current["boundary_success"] = row.get("boundary_success")
            comparisons.append(dict(current))
            (output / "context-comparison.json").write_text(json.dumps({
                "scope": "SDK initial planning context equality after removing persona only; source content kept in memory, not this evidence",
                "limitations": "Same prepared source and five-tool catalog. Page images differ by experimental injection; not production retrieval adoption or independent quality certification.",
                "rows": comparisons,
            }, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--transcription", type=Path)
    parser.add_argument("--modes", nargs="+", choices=("text", "text_image", "text_image_crops"))
    parser.add_argument("--objective")
    parser.add_argument("--evidence-page", type=int, default=1)
    args = parser.parse_args()
    compare(args.source.resolve(), args.pdf.resolve(), args.output.resolve(), args.transcription, args.modes, args.objective, args.evidence_page)
