"""Two-level book-diagram grounding over frozen DocLayout-YOLO proposals."""
import base64
import hashlib
import io
import json
import math
import time
from pathlib import Path
from typing import Literal

from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, ConfigDict, StrictInt

from model_quality.runner import atomic_json
from .visual_grounding import grade, mark, overlap, source_manifest as visual_source_manifest
from .visual_grounding_book_detector import propose_book


class PictureRefinement(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    status: Literal["found", "absent", "ambiguous", "unlocalized"]
    proposal_id: StrictInt | None
    local_box: list[float] | None


def source_manifest():
    manifest = visual_source_manifest()
    manifest["doclayout_role"] = (
        "Frozen Picture proposals only. OCR owns text, inline formula anchors, and single characters; "
        "the model selects a Picture proposal and refines a subfigure inside it."
    )
    return manifest


def _decode(content):
    if not isinstance(content, str):
        raise ValueError("content_type")
    obj = json.loads(content, parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")))
    result = PictureRefinement.model_validate(obj)
    if result.status == "found":
        box = result.local_box
        if result.proposal_id is None or result.proposal_id < 1 or box is None or len(box) != 4:
            raise ValueError("missing_found_fields")
        if any(type(value) not in (int, float) or not math.isfinite(value) for value in box):
            raise ValueError("invalid_local_box")
        if not 0 <= box[0] < box[2] <= 1 or not 0 <= box[1] < box[3] <= 1:
            raise ValueError("local_box_range")
    elif result.proposal_id is not None or result.local_box is not None:
        raise ValueError("abstain_fields")
    return result


def _font(size):
    for path in ("/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            pass
    return ImageFont.load_default()


def _crop_sheet(png, proposals):
    source = Image.open(io.BytesIO(png)).convert("RGB")
    panel_width = 720
    label_height = 42
    panels = []
    for proposal in proposals:
        x0, y0, x1, y1 = proposal["box_px"]
        crop = source.crop((math.floor(x0), math.floor(y0), math.ceil(x1), math.ceil(y1)))
        scale = min(1.0, panel_width / max(1, crop.width), 520 / max(1, crop.height))
        crop = crop.resize((max(1, round(crop.width * scale)), max(1, round(crop.height * scale))), Image.Resampling.LANCZOS)
        panels.append((proposal, crop))
    height = 20 + sum(label_height + crop.height + 24 for _, crop in panels)
    sheet = Image.new("RGB", (panel_width + 40, max(100, height)), "white")
    draw = ImageDraw.Draw(sheet)
    font = _font(25)
    y = 15
    for proposal, crop in panels:
        draw.text((20, y), f"Picture proposal {proposal['id']} — crop content begins below", fill="#111827", font=font)
        y += label_height
        sheet.paste(crop, (20, y))
        draw.rectangle((19, y - 1, 20 + crop.width, y + crop.height), outline="#0f766e", width=3)
        y += crop.height + 24
    out = io.BytesIO()
    sheet.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _load_proposals(source, png):
    path = Path(source["doclayout_candidates_path"])
    payload = path.read_bytes()
    if hashlib.sha256(payload).hexdigest() != source["doclayout_candidates_sha256"]:
        raise ValueError("candidate_digest_changed")
    data = json.loads(payload)
    if data["page_sha256"] != source["sha256"]:
        raise ValueError("candidate_page_mismatch")
    width, height = Image.open(io.BytesIO(png)).size
    proposals = []
    for index, row in enumerate((row for row in data["detections"] if row["label"] == "Picture"), 1):
        box = row["box_px"]
        if len(box) != 4 or not 0 <= box[0] < box[2] <= width or not 0 <= box[1] < box[3] <= height:
            raise ValueError("candidate_box")
        proposals.append({"id": index, "kind": "picture", "text": "Picture", "confidence": row["confidence"], "box_px": box})
    return proposals, data


def run_sample(context, case, variant):
    evidence = {
        "version": "visual-grounding-doclayout-refine-v1",
        "case": case.id,
        "variant": variant.id,
        "scope": "Private development pages; frozen DocLayout-YOLO Picture proposal selection plus model subfigure refinement; no public export.",
    }

    def finish(status, metrics, code=None):
        evidence.update(status=status, metrics=metrics, error_code=code)
        atomic_json(context.storage / "doclayout-refine-evidence.json", evidence)
        return {"status": status, "failure_owner": None if status == "completed" else status.removesuffix("_failed"),
                "error_code": code, "metrics": metrics,
                "evidence": [{"path": "doclayout-refine-evidence.json", "contract": "visual-grounding-doclayout-refine-v1"}]}

    try:
        if variant.id != "picture-refine":
            raise ValueError("variant")
        source = json.loads(case.source)
        gold = json.loads(case.gold)
        png = Path(source["path"]).read_bytes()
        if hashlib.sha256(png).hexdigest() != source["sha256"]:
            raise ValueError("source_digest_changed")
        image = Image.open(io.BytesIO(png))
        width, height = image.size
        if (width, height) != (gold["width"], gold["height"]):
            raise ValueError("dimensions")
        proposals, detector = _load_proposals(source, png)
        if not proposals:
            return finish("candidate_failed", {"schema_valid": True, "proposal_count": 0}, "no_picture_proposals")
        _, ocr = propose_book(png)
        marked = mark(png, proposals, max_bytes=context.transport.campaign.max_inline_image_bytes)
        crops = _crop_sheet(png, proposals)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return finish("data_failed", {}, "invalid_doclayout_fixture")

    instruction = (
        "You localize a requested subfigure in two levels. Image 1 is the original page. Image 2 marks every allowed "
        "DocLayout Picture mother-region with a proposal ID. Image 3 shows enlarged crops of those same regions. "
        "Choose the one mother-region containing the requested target, then return a tight box around only the requested "
        "subfigure. local_box=[x0,y0,x1,y1] uses 0..1 coordinates relative to the chosen crop content inside its green "
        "border, with top-left origin. It is NOT relative to the page or the crop sheet. Return exactly one JSON data "
        "instance: {\"status\":\"found\",\"proposal_id\":N,\"local_box\":[x0,y0,x1,y1]}. If the target is visible "
        "but none of the Picture regions contains it, use unlocalized with null fields. Use absent only when truly absent, "
        "and ambiguous only for indistinguishable targets. No prose."
    )
    table = [{"id": p["id"], "label": "Picture", "confidence": p["confidence"], "box_px": p["box_px"]} for p in proposals]
    prompt = (case.request + f"\nFull page size: {width} x {height} pixels.\nAllowed labels: [Picture]."
              + "\nComplete Picture proposal table: " + json.dumps(table, ensure_ascii=False)
              + "\nUncorrected image-only OCR may help distinguish labels; verify visually:\n"
              + "\n".join(f"{i + 1}: {line}" for i, line in enumerate(ocr["full_ocr_lines"])))
    images = [("source.png", png), ("picture-proposals.png", marked), ("picture-crops.png", crops)]
    content = [{"type": "text", "text": prompt}]
    image_meta = []
    for name, blob in images:
        (context.storage / name).write_bytes(blob)
        image_meta.append({"file": name, "sha256": hashlib.sha256(blob).hexdigest(), "bytes": len(blob)})
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(blob).decode()}})
    campaign = context.transport.campaign
    payload = {"model": campaign.model, "max_tokens": campaign.max_output_tokens, "temperature": campaign.temperature,
               "messages": [{"role": "system", "content": instruction}, {"role": "user", "content": content}],
               "response_format": {"type": "json_object"}}
    evidence.update(request=case.request, source_sha256=source["sha256"], proposals=proposals,
                    detector={k: detector[k] for k in ("model", "revision", "weight_sha256", "imgsz", "conf")},
                    wire_images=image_meta, wire_input={**payload, "thinking": {"type": campaign.thinking}, "reasoning_split": True, "stream": False})
    atomic_json(context.storage / "doclayout-refine-evidence.json", evidence)
    fake = {"choices": [{"message": {"content": json.dumps({"status": "found", "proposal_id": 1, "local_box": [0.1, 0.1, 0.9, 0.9]})}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}}
    started = time.monotonic()
    raw = context.transport.request(payload, fake_response=fake if campaign.transport == "fake" else None)
    evidence["provider_wall_seconds"] = time.monotonic() - started
    try:
        if raw["choices"][0].get("finish_reason") != "stop":
            raise ValueError("incomplete")
        prediction = _decode(raw["choices"][0]["message"].get("content"))
        box = None
        if prediction.status == "found":
            matches = [proposal for proposal in proposals if proposal["id"] == prediction.proposal_id]
            if len(matches) != 1:
                raise ValueError("proposal_id")
            parent = matches[0]["box_px"]
            local = prediction.local_box
            box = [parent[0] + local[0] * (parent[2] - parent[0]), parent[1] + local[1] * (parent[3] - parent[1]),
                   parent[0] + local[2] * (parent[2] - parent[0]), parent[1] + local[3] * (parent[3] - parent[1])]
    except (ValueError, KeyError, IndexError, TypeError):
        return finish("candidate_failed", {"schema_valid": False}, "invalid_doclayout_refinement")
    metrics = grade(prediction.status, box, gold, proposals)
    metrics.update(schema_valid=True, proposal_count=len(proposals),
                   selected_proposal_contains_gold=next((overlap(p["box_px"], gold["target_px"])["coverage"] >= gold["minimum_coverage"]
                                                         for p in proposals if p["id"] == prediction.proposal_id), False)
                   if prediction.status == "found" else False)
    evidence.update(prediction=prediction.model_dump(), box_px=box, gold=gold)
    return finish("completed" if metrics["task_pass"] else "candidate_failed", metrics)
