# -*- mode: python ; coding: utf-8 -*-
from __future__ import annotations

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path.cwd()


def optional(callable_, *args, **kwargs):
    try:
        return callable_(*args, **kwargs)
    except Exception:
        return []


datas = [
    (str(ROOT / "app" / "prompts"), "app/prompts"),
    *optional(collect_data_files, "litellm", include_py_files=False),
    *optional(collect_data_files, "onnxtr", include_py_files=False),
    *optional(collect_data_files, "fitz", include_py_files=False),
    *optional(collect_data_files, "pymupdf", include_py_files=False),
    *optional(collect_data_files, "tiktoken", include_py_files=False),
]

binaries = [
    *optional(collect_dynamic_libs, "onnxruntime"),
    *optional(collect_dynamic_libs, "fitz"),
    *optional(collect_dynamic_libs, "pymupdf"),
]

hiddenimports = sorted(
    set(
        optional(collect_submodules, "onnxtr")
        + optional(collect_submodules, "litellm")
        + optional(collect_submodules, "sqlalchemy.dialects")
        + optional(collect_submodules, "tiktoken_ext")
    )
)

a = Analysis(
    [str(ROOT / "app" / "sidecar.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="vibe-learner-sidecar",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)
