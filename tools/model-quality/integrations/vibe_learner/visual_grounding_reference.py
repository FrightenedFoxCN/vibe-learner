"""Coordinate-reference diagnostic for private academic-book page localization."""
import base64
import hashlib
import io
import json
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from model_quality.runner import atomic_json
from .visual_grounding import Direct, decode, grade, source_manifest
from .visual_grounding_book_detector import propose_book


def _font(size: int):
    for path in (
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/System/Library/Fonts/Supplemental/Helvetica.ttc",
    ):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def coordinate_grid(png: bytes) -> bytes:
    image = Image.open(io.BytesIO(png)).convert("RGBA")
    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    width, height = image.size
    font = _font(max(12, round(min(width, height) * 0.017)))
    for index in range(1, 10):
        x = round(width * index / 10)
        y = round(height * index / 10)
        draw.line((x, 0, x, height), fill=(202, 45, 67, 150), width=2)
        draw.line((0, y, width, y), fill=(28, 110, 215, 150), width=2)
        draw.rectangle((x + 3, 3, x + 45, 3 + font.size + 5), fill=(255, 255, 255, 220))
        draw.text((x + 6, 5), f"x.{index}", fill=(152, 20, 38, 255), font=font)
        draw.rectangle((3, y + 3, 48, y + font.size + 8), fill=(255, 255, 255, 220))
        draw.text((6, y + 5), f"y.{index}", fill=(12, 77, 160, 255), font=font)
    marked = Image.alpha_composite(image, overlay).convert("RGB")
    out = io.BytesIO()
    marked.save(out, format="PNG", optimize=True)
    return out.getvalue()


def run_sample(context, case, variant):
    evidence = {
        "version": "visual-grounding-coordinate-reference-v1",
        "case": case.id,
        "variant": variant.id,
        "scope": "private book-page coordinate-reference diagnostic; no domain effects/commit",
    }

    def finish(status, metrics, code=None):
        evidence.update(status=status, metrics=metrics, error_code=code)
        atomic_json(context.storage / "coordinate-reference-evidence.json", evidence)
        return {
            "status": status,
            "failure_owner": None if status == "completed" else status.removesuffix("_failed"),
            "error_code": code,
            "metrics": metrics,
            "evidence": [{"path": "coordinate-reference-evidence.json", "contract": "visual-grounding-coordinate-reference-v1"}],
        }

    try:
        source = json.loads(case.source)
        gold = json.loads(case.gold)
        png = Path(source["path"]).read_bytes()
        if variant.id not in ("reference-plain", "coordinate-grid") or hashlib.sha256(png).hexdigest() != source["sha256"]:
            raise ValueError("invalid_source")
        image = Image.open(io.BytesIO(png))
        width, height = image.size
        if (width, height) != (gold["width"], gold["height"]):
            raise ValueError("dimensions")
        _, ocr = propose_book(png)
        marked = coordinate_grid(png) if variant.id == "coordinate-grid" else None
    except (OSError, ValueError, KeyError):
        return finish("data_failed", {}, "invalid_coordinate_reference_fixture")

    if variant.id == "coordinate-grid":
        instruction = (
            "Locate the requested target on the full page. Image 1 is the untouched page. Image 2 is the same page "
            "with a 0.1-spaced coordinate grid: red vertical lines label x and blue horizontal lines label y, both "
            "measured from the top-left of the full image. Use the grid only to map the visually identified target "
            "to coordinates. Return one JSON DATA INSTANCE: {\"status\":\"found\",\"box\":[x0,y0,x1,y1]} with "
            "0..1 full-page coordinates. The box must enclose the whole requested element. For absent, ambiguous, or "
            "unlocalized return box:null. No prose."
        )
    else:
        instruction = (
            "Locate the requested target on the untouched full page. Return one JSON DATA INSTANCE: "
            "{\"status\":\"found\",\"box\":[x0,y0,x1,y1]} with 0..1 full-page coordinates measured from "
            "the top-left. The box must enclose the whole requested element. For absent, ambiguous, or unlocalized "
            "return box:null. No prose."
        )
    text = (
        case.request
        + f"\nFull page size: {width} x {height} pixels."
        + "\nUncorrected image-only OCR; verify against the images:\n"
        + "\n".join(f"{index + 1}: {line}" for index, line in enumerate(ocr["full_ocr_lines"]))
    )
    content = [{"type": "text", "text": text}]
    image_meta = []
    images = [("source.png", png)]
    if marked is not None:
        images.append(("coordinate-grid.png", marked))
    for name, payload in images:
        (context.storage / name).write_bytes(payload)
        image_meta.append({"file": name, "sha256": hashlib.sha256(payload).hexdigest(), "bytes": len(payload)})
        content.append({"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(payload).decode()}})
    campaign = context.transport.campaign
    payload = {
        "model": campaign.model,
        "max_tokens": campaign.max_output_tokens,
        "temperature": campaign.temperature,
        "messages": [{"role": "system", "content": instruction}, {"role": "user", "content": content}],
        "response_format": {"type": "json_object"},
    }
    evidence.update(
        request=case.request,
        source_sha256=source["sha256"],
        ocr_lines=ocr["full_ocr_lines"],
        wire_images=image_meta,
        wire_input={**payload, "thinking": {"type": campaign.thinking}, "reasoning_split": True, "stream": False},
    )
    atomic_json(context.storage / "coordinate-reference-evidence.json", evidence)
    fake = {
        "choices": [{"message": {"content": json.dumps({"status": "found", "box": [0.1, 0.1, 0.2, 0.2]})}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
    }
    started = time.monotonic()
    raw = context.transport.request(payload, fake_response=fake if campaign.transport == "fake" else None)
    evidence["provider_wall_seconds"] = time.monotonic() - started
    try:
        if raw["choices"][0].get("finish_reason") != "stop":
            raise ValueError("incomplete")
        prediction = decode(raw["choices"][0]["message"]["content"], Direct)
        box = None
        if prediction.status == "found":
            box = [prediction.box[0] * width, prediction.box[1] * height, prediction.box[2] * width, prediction.box[3] * height]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        evidence["decode_error_type"] = type(exc).__name__
        return finish("candidate_failed", {"schema_valid": False}, "invalid_coordinate_reference_output")
    metrics = grade(prediction.status, box, gold, [])
    metrics["schema_valid"] = True
    evidence.update(prediction=prediction.model_dump(), box_px=box, gold=gold)
    return finish("completed" if metrics["task_pass"] else "candidate_failed", metrics)
