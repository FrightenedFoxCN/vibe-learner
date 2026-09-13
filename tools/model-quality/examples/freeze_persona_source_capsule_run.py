"""Create the digest anchor that must be committed before blind review export."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from examples.export_persona_source_capsule_paired_review import build_run_anchor


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("persona_capsule_run_anchor_output_exists")
    anchor = build_run_anchor(args.run)
    args.output.write_text(
        json.dumps(anchor, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
