"""Run each unittest module in an isolated, time-bounded process for CI."""
from __future__ import annotations

import argparse
import faulthandler
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import unittest


DEFAULT_MODULE_TIMEOUT_SECONDS = 180


def _run_one_module(module: str) -> int:
    dump_handle = None
    if hasattr(signal, "SIGUSR1"):
        dump_path = os.environ.get("VIBE_CI_STACK_DUMP_PATH")
        if dump_path:
            dump_handle = open(dump_path, "a", encoding="utf-8", buffering=1)
        faulthandler.register(signal.SIGUSR1, file=dump_handle, all_threads=True)
    script_path = Path(__file__).resolve()
    sys.path[:0] = [str(script_path.parent), str(script_path.parents[1])]
    suite = unittest.defaultTestLoader.loadTestsFromName(module)
    try:
        result = unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    finally:
        if dump_handle is not None:
            dump_handle.close()


def _test_modules() -> list[str]:
    tests_root = Path(__file__).resolve().parent
    return [path.stem for path in sorted(tests_root.glob("test_*.py"))]


def _terminate_with_dump(process: subprocess.Popen[bytes]) -> None:
    if os.name == "posix" and hasattr(signal, "SIGUSR1"):
        try:
            os.killpg(process.pid, signal.SIGUSR1)
            process.wait(timeout=2)
            return
        except (ProcessLookupError, subprocess.TimeoutExpired):
            pass
    try:
        process.terminate()
        process.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        process.kill()
        process.wait()


def _annotation_escape(value: str) -> str:
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _report_stack_dump(path: Path, module: str) -> None:
    try:
        stack = path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        stack = f"stack dump unavailable: {type(exc).__name__}"
    if not stack:
        stack = "stack dump was empty; the child may have stopped before handling SIGUSR1"
    # GitHub annotations have a practical payload limit. The tail contains the
    # active frames while retaining enough context for all small test threads.
    stack = stack[-6000:]
    print(
        f"::error title=Backend timeout stack ({module})::{_annotation_escape(stack)}",
        flush=True,
    )


def run_suite(timeout_seconds: int) -> int:
    modules = _test_modules()
    print(f"CI backend suite: {len(modules)} isolated modules, timeout={timeout_seconds}s", flush=True)
    for index, module in enumerate(modules, 1):
        print(f"\n[{index}/{len(modules)}] {module}", flush=True)
        with tempfile.TemporaryDirectory(prefix="vibe-ci-stack-") as directory:
            dump_path = Path(directory) / f"{module}.log"
            process = subprocess.Popen(
                [sys.executable, str(Path(__file__).resolve()), "--module", module],
                cwd=Path(__file__).resolve().parents[1],
                env={
                    **os.environ,
                    "PYTHONFAULTHANDLER": "1",
                    "PYTHONUNBUFFERED": "1",
                    "VIBE_CI_STACK_DUMP_PATH": str(dump_path),
                },
                start_new_session=os.name == "posix",
            )
            try:
                return_code = process.wait(timeout=timeout_seconds)
            except subprocess.TimeoutExpired:
                print(f"::error::Backend test module timed out after {timeout_seconds}s: {module}", flush=True)
                _terminate_with_dump(process)
                _report_stack_dump(dump_path, module)
                return 124
        if return_code != 0:
            print(f"::error::Backend test module failed with exit code {return_code}: {module}", flush=True)
            return return_code
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--module")
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=int(os.environ.get("VIBE_CI_TEST_MODULE_TIMEOUT_SECONDS", DEFAULT_MODULE_TIMEOUT_SECONDS)),
    )
    args = parser.parse_args()
    if args.module:
        return _run_one_module(args.module)
    if not 30 <= args.timeout_seconds <= 900:
        parser.error("--timeout-seconds must be between 30 and 900")
    return run_suite(args.timeout_seconds)


if __name__ == "__main__":
    raise SystemExit(main())
