"""Reviewed algorithms plus concrete OCR/model files define reuse compatibility."""

from __future__ import annotations

import hashlib
from importlib.metadata import PackageNotFoundError, version

from app.core.harness_component_versions import (
    DOCUMENT_PARSER_CONTRACT_VERSION,
    OCR_ENGINE_CONTRACT_VERSION,
    STUDY_UNIT_CLEANER_CONTRACT_VERSION,
)
from app.models.harness import canonical_harness_digest


def configuration_digest(parser) -> str:
    model_dir = getattr(getattr(parser, "ocr_engine", None), "_model_dir", None)
    files = {}
    if model_dir is not None and model_dir.is_dir():
        for path in sorted(model_dir.rglob("*")):
            if path.is_file():
                with path.open("rb") as handle:
                    files[str(path.relative_to(model_dir))] = hashlib.file_digest(
                        handle, "sha256"
                    ).hexdigest()
    packages = {}
    for name in ("onnxtr", "PyMuPDF"):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return canonical_harness_digest(
        {
            "parser_contract": DOCUMENT_PARSER_CONTRACT_VERSION,
            "ocr_contract": OCR_ENGINE_CONTRACT_VERSION,
            "cleanup_contract": STUDY_UNIT_CLEANER_CONTRACT_VERSION,
            "parser_class": f"{type(parser).__module__}.{type(parser).__qualname__}",
            "ocr_engine": getattr(parser, "ocr_engine_name", ""),
            "model_dir": str(model_dir or ""),
            "model_files": files,
            "packages": packages,
        }
    )
