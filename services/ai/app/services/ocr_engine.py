from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import fitz

from app.core.logging import get_logger

logger = get_logger("vibe_learner.ocr")


@dataclass(slots=True)
class OcrPageResult:
    text: str = ""
    status: str = "unavailable"
    engine_name: str | None = None
    model_id: str | None = None
    warning: str = ""
    language_hint: str | None = None


class OnnxtrOcrEngine:
    def __init__(self, *, runtime_temp_root: Path | None = None, model_dir: str = "") -> None:
        self._runtime_temp_root = runtime_temp_root
        self._model_dir = Path(model_dir).expanduser() if model_dir else None
        self._predictor: Any | None = None
        self._model_id: str | None = None
        self._load_error = ""
        self._load_attempted = False

    @property
    def engine_name(self) -> str:
        return "onnxtr"

    @property
    def model_id(self) -> str | None:
        return self._model_id

    def extract_page_text(self, page: fitz.Page) -> OcrPageResult:
        predictor = self._ensure_predictor()
        if predictor is None:
            return OcrPageResult(
                status="unavailable",
                engine_name=self.engine_name,
                model_id=self._model_id,
                warning=self._load_error or "onnxtr_ocr_unavailable",
                language_hint="multilingual",
            )

        image_path: Path | None = None
        temp_file_kwargs: dict[str, str] = {
            "prefix": "vibe-learner-onnxtr-",
            "suffix": ".png",
        }
        if self._runtime_temp_root is not None:
            self._runtime_temp_root.mkdir(parents=True, exist_ok=True)
            temp_file_kwargs["dir"] = str(self._runtime_temp_root)

        try:
            with tempfile.NamedTemporaryFile(delete=False, **temp_file_kwargs) as handle:
                image_path = Path(handle.name)
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            pixmap.save(image_path)

            from onnxtr.io import DocumentFile

            document = DocumentFile.from_images([str(image_path)])
            prediction = predictor(document)
            rendered = prediction.render()
            if isinstance(rendered, str):
                text = rendered
            elif isinstance(rendered, list):
                text = "\n".join(str(item) for item in rendered if item)
            else:
                text = str(rendered or "")

            return OcrPageResult(
                text=text,
                status="completed" if text.strip() else "failed",
                engine_name=self.engine_name,
                model_id=self._model_id,
                warning="" if text.strip() else "onnxtr_empty_result",
                language_hint="multilingual",
            )
        except Exception as exc:
            logger.warning("ocr.onnxtr_page_failed error=%s", exc)
            return OcrPageResult(
                status="failed",
                engine_name=self.engine_name,
                model_id=self._model_id,
                warning=f"onnxtr_ocr_failed:{exc}",
                language_hint="multilingual",
            )
        finally:
            try:
                if image_path is not None:
                    image_path.unlink(missing_ok=True)
            except Exception:
                logger.debug("ocr.onnxtr_cleanup_failed path=%s", image_path)

    def _ensure_predictor(self) -> Any | None:
        if self._predictor is not None:
            return self._predictor
        if self._load_attempted:
            return None
        self._load_attempted = True

        try:
            from onnxtr.models import linknet_resnet18, ocr_predictor, parseq
        except Exception as exc:
            self._load_error = f"onnxtr_import_failed:{exc}"
            logger.warning("ocr.onnxtr_import_failed error=%s", exc)
            return None

        try:
            if self._model_dir is not None:
                detector_path = self._model_dir / "detector.onnx"
                recognizer_path = self._model_dir / "recognizer.onnx"
                vocab_path = self._model_dir / "recognizer_vocab.txt"
                if detector_path.exists() and recognizer_path.exists() and vocab_path.exists():
                    vocab = vocab_path.read_text(encoding="utf-8")
                    self._predictor = ocr_predictor(
                        det_arch=linknet_resnet18(str(detector_path)),
                        reco_arch=parseq(str(recognizer_path), vocab=vocab),
                        assume_straight_pages=True,
                        straighten_pages=False,
                        resolve_blocks=False,
                    )
                    self._model_id = "custom:linknet_resnet18+parseq"
                    logger.info("ocr.onnxtr_loaded model_id=%s model_dir=%s", self._model_id, self._model_dir)
                    return self._predictor

            self._predictor = ocr_predictor(
                det_arch="db_mobilenet_v3_large",
                reco_arch="parseq",
                assume_straight_pages=True,
                straighten_pages=False,
                resolve_blocks=False,
            )
            self._model_id = "db_mobilenet_v3_large+parseq"
            logger.info("ocr.onnxtr_loaded model_id=%s", self._model_id)
            return self._predictor
        except Exception as exc:
            self._load_error = f"onnxtr_predictor_init_failed:{exc}"
            logger.warning("ocr.onnxtr_predictor_init_failed error=%s", exc)
            return None
