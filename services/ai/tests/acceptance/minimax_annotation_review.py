"""Post-hoc geometry review for the synthetic equation attachment fixture only."""
import argparse
import json
from pathlib import Path

import fitz


def run(roots, output):
    rows = []
    for root in roots:
        pdfs = list((root / "data/uploads").glob("*.pdf"))
        if len(pdfs) != 1:
            raise ValueError("Expected one source PDF for the synthetic fixture")
        with fitz.open(pdfs[0]) as source:
            page = source[0]
            matches = page.search_for("2x + 3 = 11")
            if len(matches) != 1:
                raise ValueError("Synthetic target must have exactly one occurrence")
            box = matches[0]
            expected = fitz.Rect(box.x0/page.rect.width, box.y0/page.rect.height,
                box.x1/page.rect.width, box.y1/page.rect.height)
        for line in (root / "report.jsonl").read_text().splitlines():
            row = json.loads(line)
            result = (row.get("receipt") or {}).get("result") or {}
            state = (result.get("session") or {}).get("projected_pdf") or {}
            rects = [r for overlay in state.get("overlays", []) for r in overlay.get("rects", [])]
            scores = []
            for r in rects:
                actual = fitz.Rect(r["x"], r["y"], r["x"]+r["width"], r["y"]+r["height"])
                area = (actual & expected).get_area()
                union = actual.get_area() + expected.get_area() - area
                scores.append({"rect": r, "target_coverage": area/expected.get_area(), "iou": area/union if union else 0})
            best = max((s["iou"] for s in scores), default=0)
            rows.append({"case_id": row["case_id"], "repetition": row["repetition"],
                "operation_id": row.get("harness_operation_id"), "boundary_success": row.get("boundary_success"),
                "visual_variant": row.get("visual_context_variant", "original"),
                "target_normalized_xyxy": list(expected), "boxes": scores,
                "single_box_iou_at_least_half": bool(row.get("boundary_success")) and len(scores)==1 and best>=0.5})
    output.write_text(json.dumps({"scope": "synthetic PDF-to-image geometry review; not general image grounding certification",
        "oracle": "Exact source PDF text bounds; attachment is the same fixture rasterized at 144 DPI. Oracle never supplied to candidate.",
        "criterion": "Committed response, exactly one rectangle, IoU >= 0.5. Also retain target coverage and raw rectangles.",
        "rows": rows}, ensure_ascii=False, indent=2)+"\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--roots", nargs="+", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.roots, args.output)
