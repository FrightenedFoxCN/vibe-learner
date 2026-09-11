"""Post-hoc checks for the synthetic 2x+3=11 fill-blank fixture only."""
import argparse
import json
from pathlib import Path
import re


PRIVATE_KEYS = {"answer_key", "accepted_answers", "grading_spec", "correct_option_key", "explanation"}


def private_paths(value, prefix=""):
    if isinstance(value, dict):
        for key, child in value.items():
            path = f"{prefix}.{key}"
            if key in PRIVATE_KEYS:
                yield path
            yield from private_paths(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            yield from private_paths(child, f"{prefix}[{index}]")


def review(paths):
    rows = []
    for path in paths:
        for line in path.read_text().splitlines():
            row = json.loads(line)
            if row.get("case_id") not in {"fill_blank_attempt", "fill_blank_native_attempt"}:
                continue
            result = (row.get("receipt") or {}).get("result") or {}
            question = result.get("interactive_question") or {}
            # Read only public pre-submission reply and character fields, not
            # provider contents, reasoning, tool result or private grading spec.
            public = {key: result.get(key) for key in ("reply", "rich_blocks", "interactive_question", "character_events")}
            text = json.dumps(public, ensure_ascii=False)
            attempt = row.get("answer_submission") or {}
            rows.append({"operation_id": row.get("harness_operation_id"), "source": path.name,
                "repetition": row["repetition"], "boundary_success": row["boundary_success"],
                "has_fill_blank": question.get("question_type") == "fill_blank",
                "pre_submission_private_field_paths": list(private_paths(question)),
                "fixture_answer_literal_in_public_content": bool(re.search(r"(?<!\d)4(?!\d)|四", text)),
                "submitted_answer": attempt.get("submitted_answer"),
                "submission_http_status": attempt.get("http_status"),
                "grading_matches_fixture": attempt.get("grading_matches_fixture"),
                "duplicate_equal": attempt.get("duplicate_equal"),
                "revision_incremented_once": attempt.get("revision_incremented_once")})
    return {"scope": "synthetic fill-blank post-hoc public-answer and submission review",
        "limitations": ["Literal answer scan is fixture-specific, not a general semantic leakage detector.",
            "Absence of answer literals does not prove absence of premature hints or solutions.",
            "Grading success is separate from generation, tool compliance and pre-submission privacy.",
            "Developer-authored checks are not independent quality certification."], "rows": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, nargs="+", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    args.output.write_text(json.dumps(review(args.evidence), ensure_ascii=False, indent=2) + "\n")
