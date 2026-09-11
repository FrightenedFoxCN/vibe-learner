"""Compare current prompt preflight against trusted repository revision 991876b.

Runs both implementations with the same synthetic histories and asserts exact
prompt, retained-message and budget-report equality before recording timings.
"""
import argparse
from dataclasses import asdict
import json
from pathlib import Path
import platform
import subprocess
import sys
import time
import types

from app.services import tavern_prompt
from tests.test_tavern_prompt_safety import _persona, _participant, _message


def run(samples: int, output: Path) -> None:
    source = subprocess.check_output([
        "git", "show", "991876b:services/ai/app/services/tavern_prompt.py",
    ], text=True)
    reference = types.ModuleType("qg_preflight_reference")
    sys.modules[reference.__name__] = reference
    exec(compile(source, "git:991876b/tavern_prompt.py", "exec"), reference.__dict__)
    cast = [_participant(_persona("quality", "沈舟"), display_order=0)]
    rows = []
    for count in (32, 128, 256):
        kwargs = dict(persona=cast[0].persona_snapshot, participants=cast,
            scene_profile=None, recent_messages=[_message(i+1,
                "这是一段合成的雨天旅途闲谈，人物约定始终保持一致。" * 40) for i in range(count)],
            user_message="你好。", guidance="", allowed_target_ids=["quality"], actor_reply_schema="{}")
        for index in range(samples + 1):
            results = {}
            timings = {}
            order = ("reference", "current") if index % 2 else ("current", "reference")
            for label in order:
                module = reference if label == "reference" else tavern_prompt
                started = time.perf_counter()
                results[label] = module.preflight_tavern_actor_prompt(**kwargs)
                timings[label] = round((time.perf_counter()-started)*1000, 3)
            old, new = results["reference"], results["current"]
            assert old.messages == new.messages
            assert old.recent_messages == new.recent_messages
            assert asdict(old.report) == asdict(new.report)
            if index:
                rows.append({"messages": count, "repetition": index-1, "order": order,
                    "reference_ms": timings["reference"], "current_ms": timings["current"],
                    "removed": new.report.removed_message_count, "exact_equal": True})
        print(json.dumps({"messages": count, "pairs": samples, "exact_equal": True}), flush=True)
    output.write_text(json.dumps({"fixture_version": "tavern-preflight-comparison-v1",
        "reference_revision": "991876b", "python": platform.python_version(),
        "platform": platform.system(), "machine": platform.machine(),
        "warmup_pairs_per_size": 1, "samples": rows}, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=30)
    args = parser.parse_args()
    if args.samples < 1:
        parser.error("samples must be positive")
    run(args.samples, args.output)
