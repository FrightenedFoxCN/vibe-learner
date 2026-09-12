from __future__ import annotations

import hashlib
import base64
import io
import json
import subprocess
import sys
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from app.models.document_layout import (
    DocumentLayoutBoxV1,
    DocumentLayoutCandidateV1,
    DocumentLayoutDetectionV1,
    DocumentLayoutLabel,
)


DOCLAYOUT_MODEL_ID = "juliozhao/DocLayout-YOLO-DocLayNet-Docsynth300K_pretrained"
DOCLAYOUT_MODEL_REVISION = "51b2c54a642013022382c3d2bd76e84b07656b4a"
DOCLAYOUT_WEIGHT_SHA256 = "0ddfc7f411ec23aab661091ca8da6b25abe7bdce6afa3a515811c92d7ccfb1db"
_ALLOWED_LABELS = ("Picture", "Formula")


class DocumentLayoutService:
    def __init__(
        self,
        *,
        engine: str = "disabled",
        python_executable: str = "",
        model_path: str = "",
        model_sha256: str = "",
        runtime_temp_root: Path | None = None,
        timeout_seconds: int = 90,
        max_candidates: int = 32,
        runner: Callable[[bytes, tuple[DocumentLayoutLabel, ...], bool], dict[str, Any]] | None = None,
    ) -> None:
        self.engine = engine.strip().lower() or "disabled"
        self.python_executable = python_executable.strip() or sys.executable
        self.model_path = Path(model_path).expanduser() if model_path.strip() else None
        self.model_sha256 = model_sha256.strip().lower()
        self.runtime_temp_root = runtime_temp_root
        self.timeout_seconds = max(5, min(int(timeout_seconds), 300))
        self.max_candidates = max(1, min(int(max_candidates), 128))
        self._runner = runner
        self._verified_model = False

    @property
    def enabled(self) -> bool:
        return self.engine == "doclayout-yolo" and (self._runner is not None or self.model_path is not None)

    def detect_png(
        self,
        png: bytes,
        *,
        labels: Sequence[DocumentLayoutLabel],
        recursive_picture: bool = True,
    ) -> DocumentLayoutDetectionV1:
        source_sha = hashlib.sha256(png).hexdigest()
        width, height = self._image_dimensions(png)
        normalized_labels = self._normalize_labels(labels)
        if not self.enabled:
            return DocumentLayoutDetectionV1(
                status="disabled", engine="disabled", source_sha256=source_sha,
                width=width, height=height, labels=normalized_labels,
                recursive_picture=recursive_picture, warning="document_layout_disabled",
            )
        try:
            raw = self._runner(png, normalized_labels, recursive_picture) if self._runner else self._run_worker(
                png, normalized_labels, recursive_picture
            )
            candidates = self._normalize_candidates(raw, width=width, height=height)
            return DocumentLayoutDetectionV1(
                status="completed", engine="doclayout-yolo", model_id=DOCLAYOUT_MODEL_ID,
                model_revision=DOCLAYOUT_MODEL_REVISION, source_sha256=source_sha,
                width=width, height=height, labels=normalized_labels,
                recursive_picture=recursive_picture, candidates=tuple(candidates),
            )
        except (OSError, ValueError, KeyError, json.JSONDecodeError, subprocess.SubprocessError) as exc:
            return DocumentLayoutDetectionV1(
                status="unavailable", engine="doclayout-yolo", model_id=DOCLAYOUT_MODEL_ID,
                model_revision=DOCLAYOUT_MODEL_REVISION, source_sha256=source_sha,
                width=width, height=height, labels=normalized_labels,
                recursive_picture=recursive_picture,
                warning=f"document_layout_unavailable:{type(exc).__name__}",
            )

    def evidence_images(
        self,
        png: bytes,
        detection: DocumentLayoutDetectionV1,
    ) -> list[dict[str, Any]]:
        """Return original, numbered candidates, and enlarged Picture parents for the provider only."""
        if detection.status != "completed":
            return []
        source = Image.open(io.BytesIO(png)).convert("RGB")
        marked = source.copy()
        draw = ImageDraw.Draw(marked)
        font = self._font(max(14, round(min(source.size) * 0.018)))
        for candidate in detection.candidates:
            box = candidate.box
            xyxy = (
                box.x * source.width,
                box.y * source.height,
                (box.x + box.width) * source.width,
                (box.y + box.height) * source.height,
            )
            color = "#0f766e" if candidate.depth == 0 else "#ea580c"
            draw.rectangle(xyxy, outline=color, width=4 if candidate.depth == 0 else 3)
            draw.text((xyxy[0] + 2, max(0, xyxy[1] - font.size - 3)), candidate.candidate_id, fill=color, font=font)
        parents = [candidate for candidate in detection.candidates if candidate.depth == 0 and candidate.label == "Picture"]
        sheets = []
        if parents:
            panel_width, label_height = 720, 40
            crops = []
            for parent in parents:
                box = parent.box
                crop = source.crop((
                    int(box.x * source.width), int(box.y * source.height),
                    max(1, round((box.x + box.width) * source.width)),
                    max(1, round((box.y + box.height) * source.height)),
                ))
                scale = min(1.0, panel_width / max(1, crop.width), 480 / max(1, crop.height))
                crop = crop.resize((max(1, round(crop.width * scale)), max(1, round(crop.height * scale))), Image.Resampling.LANCZOS)
                crops.append((parent, crop))
            sheet = Image.new("RGB", (panel_width + 40, 20 + sum(label_height + crop.height + 20 for _, crop in crops)), "white")
            sheet_draw = ImageDraw.Draw(sheet)
            sheet_font = self._font(23)
            y = 12
            for parent, crop in crops:
                sheet_draw.text((20, y), f"{parent.candidate_id} Picture parent", fill="#111827", font=sheet_font)
                y += label_height
                sheet.paste(crop, (20, y))
                sheet_draw.rectangle((19, y - 1, 20 + crop.width, y + crop.height), outline="#0f766e", width=3)
                y += crop.height + 20
            sheets.append(("layout-parent-crops", sheet))
        return [
            self._image_payload("layout-original", source),
            self._image_payload("layout-candidates", marked),
            *(self._image_payload(name, image) for name, image in sheets),
        ]

    @staticmethod
    def _font(size: int):
        for path in ("/System/Library/Fonts/Supplemental/Arial.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                pass
        return ImageFont.load_default()

    @staticmethod
    def _image_payload(role: str, image: Image.Image) -> dict[str, Any]:
        output = io.BytesIO()
        image.save(output, format="PNG", optimize=True)
        raw = output.getvalue()
        return {
            "role": role,
            "width": image.width,
            "height": image.height,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "image_url": "data:image/png;base64," + base64.b64encode(raw).decode(),
        }
    @staticmethod
    def _normalize_labels(labels: Sequence[DocumentLayoutLabel]) -> tuple[DocumentLayoutLabel, ...]:
        normalized = tuple(dict.fromkeys(labels))
        if not normalized or any(label not in _ALLOWED_LABELS for label in normalized):
            raise ValueError("document_layout_labels_invalid")
        return normalized

    @staticmethod
    def _image_dimensions(png: bytes) -> tuple[int, int]:
        image = Image.open(io.BytesIO(png))
        if image.format != "PNG" or image.width > 20_000 or image.height > 20_000:
            raise ValueError("document_layout_image_invalid")
        return image.width, image.height

    def _verify_model(self) -> None:
        if self._verified_model:
            return
        if self.model_path is None or not self.model_path.is_file():
            raise OSError("document_layout_model_missing")
        expected = self.model_sha256 or DOCLAYOUT_WEIGHT_SHA256
        if expected != DOCLAYOUT_WEIGHT_SHA256:
            raise ValueError("document_layout_model_digest_not_reviewed")
        actual = hashlib.sha256(self.model_path.read_bytes()).hexdigest()
        if actual != expected:
            raise ValueError("document_layout_model_digest_mismatch")
        self._verified_model = True

    def _run_worker(self, png: bytes, labels: tuple[DocumentLayoutLabel, ...], recursive_picture: bool) -> dict[str, Any]:
        self._verify_model()
        kwargs: dict[str, str] = {"prefix": "vibe-layout-", "suffix": ".png"}
        if self.runtime_temp_root is not None:
            self.runtime_temp_root.mkdir(parents=True, exist_ok=True)
            kwargs["dir"] = str(self.runtime_temp_root)
        path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, **kwargs) as handle:
                handle.write(png)
                path = Path(handle.name)
            worker = Path(__file__).resolve().parents[1] / "workers" / "document_layout_worker.py"
            command = [self.python_executable, str(worker), "--image", str(path), "--model", str(self.model_path),
                       "--labels", ",".join(labels), "--imgsz", "1120", "--conf", "0.05"]
            if recursive_picture and "Picture" in labels:
                command.append("--recursive-picture")
            completed = subprocess.run(command, capture_output=True, text=True, timeout=self.timeout_seconds, check=True)
            return json.loads(completed.stdout)
        finally:
            if path is not None:
                path.unlink(missing_ok=True)

    def _normalize_candidates(self, raw: dict[str, Any], *, width: int, height: int) -> list[DocumentLayoutCandidateV1]:
        if raw.get("width") != width or raw.get("height") != height or not isinstance(raw.get("detections"), list):
            raise ValueError("document_layout_worker_shape")
        rows = []
        for source_index, item in enumerate(raw["detections"]):
            label = item.get("label")
            box = item.get("box_px")
            depth = item.get("depth")
            if label not in _ALLOWED_LABELS or depth not in (0, 1) or not isinstance(box, list) or len(box) != 4:
                raise ValueError("document_layout_candidate_invalid")
            x0, y0, x1, y1 = (float(value) for value in box)
            x0, y0, x1, y1 = max(0.0, x0), max(0.0, y0), min(float(width), x1), min(float(height), y1)
            if x1 <= x0 or y1 <= y0:
                continue
            rows.append({
                "source_index": source_index, "label": label, "confidence": float(item.get("confidence")),
                "depth": depth, "parent_index": item.get("parent_index"), "box_px": (x0, y0, x1, y1),
            })
        rows.sort(key=lambda row: (row["depth"], row["box_px"][1], row["box_px"][0], -row["confidence"]))
        kept = []
        for row in rows:
            if any(row["label"] == other["label"] and row["depth"] == other["depth"] and self._iou(row["box_px"], other["box_px"]) >= 0.92 for other in kept):
                continue
            kept.append(row)
            if len(kept) >= self.max_candidates:
                break
        id_by_source = {row["source_index"]: f"layout-{index:03d}" for index, row in enumerate(kept, 1)}
        candidates = []
        for index, row in enumerate(kept, 1):
            x0, y0, x1, y1 = row["box_px"]
            parent_id = id_by_source.get(row["parent_index"]) if row["depth"] == 1 else None
            if row["depth"] == 1 and parent_id is None:
                continue
            candidates.append(DocumentLayoutCandidateV1(
                candidate_id=f"layout-{index:03d}", label=row["label"], confidence=row["confidence"],
                box=DocumentLayoutBoxV1(x=x0 / width, y=y0 / height, width=(x1 - x0) / width, height=(y1 - y0) / height),
                depth=row["depth"], parent_candidate_id=parent_id,
            ))
        return candidates

    @staticmethod
    def _iou(first, second) -> float:
        x0, y0 = max(first[0], second[0]), max(first[1], second[1])
        x1, y1 = min(first[2], second[2]), min(first[3], second[3])
        intersection = max(0.0, x1 - x0) * max(0.0, y1 - y0)
        first_area = (first[2] - first[0]) * (first[3] - first[1])
        second_area = (second[2] - second[0]) * (second[3] - second[1])
        union = first_area + second_area - intersection
        return intersection / union if union else 0.0
