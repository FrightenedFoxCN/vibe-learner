"""JSON-only DocLayout-YOLO worker used through an explicit subprocess boundary."""
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from PIL import Image


def _rows(result, model, allowed):
    rows = []
    for xyxy, confidence, class_id in zip(
        result.boxes.xyxy.cpu().tolist(),
        result.boxes.conf.cpu().tolist(),
        result.boxes.cls.cpu().tolist(),
    ):
        label = model.names[int(class_id)]
        if label in allowed:
            rows.append({
                "label": label,
                "confidence": float(confidence),
                "box_px": [float(value) for value in xyxy],
            })
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--model", type=Path, required=True)
    parser.add_argument("--labels", required=True)
    parser.add_argument("--imgsz", type=int, default=1120)
    parser.add_argument("--conf", type=float, default=0.05)
    parser.add_argument("--recursive-picture", action="store_true")
    args = parser.parse_args()
    allowed = tuple(label for label in args.labels.split(",") if label)
    if not allowed or any(label not in {"Picture", "Formula"} for label in allowed):
        raise ValueError("document_layout_labels_invalid")

    from doclayout_yolo import YOLOv10

    model = YOLOv10(str(args.model))
    original = Image.open(args.image).convert("RGB")
    result = model.predict(
        str(args.image), imgsz=args.imgsz, conf=args.conf, device="cpu", verbose=False
    )[0]
    roots = _rows(result, model, allowed)
    rows = [{**row, "depth": 0, "parent_index": None} for row in roots]
    if args.recursive_picture and "Picture" in allowed:
        for parent_index, parent in enumerate(roots):
            if parent["label"] != "Picture":
                continue
            x0, y0, x1, y1 = parent["box_px"]
            left, top = max(0, math.floor(x0)), max(0, math.floor(y0))
            right, bottom = min(original.width, math.ceil(x1)), min(original.height, math.ceil(y1))
            if right - left < 8 or bottom - top < 8:
                continue
            crop = original.crop((left, top, right, bottom))
            child_result = model.predict(
                crop, imgsz=args.imgsz, conf=args.conf, device="cpu", verbose=False
            )[0]
            for child in _rows(child_result, model, allowed):
                cx0, cy0, cx1, cy1 = child["box_px"]
                rows.append({
                    **child,
                    "box_px": [cx0 + left, cy0 + top, cx1 + left, cy1 + top],
                    "depth": 1,
                    "parent_index": parent_index,
                })
    print(json.dumps({"width": original.width, "height": original.height, "detections": rows}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

