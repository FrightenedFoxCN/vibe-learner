import argparse
import json
from pathlib import Path


parser = argparse.ArgumentParser()
parser.add_argument("--budget-from", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument(
    "--round3-run",
    type=Path,
    default=Path(__file__).resolve().parents[1] / "runs" / "m3-text-iteration-20260913" / "round3" / "run",
)
args = parser.parse_args()


CASE_IDS = ("planned-rill-count", "recorded-umber-signal")


def load_case(case_id):
    evidence_path = args.round3_run / case_id / "baseline" / "0" / "storage" / "role-evidence.json"
    evidence = json.loads(evidence_path.read_text())
    if evidence.get("case") != case_id or len(evidence.get("drafts", [])) != 1:
        raise ValueError(f"unexpected frozen baseline evidence for {case_id}")

    manifest = json.loads((args.round3_run.parent / "manifest.json").read_text())
    source_case = next((case for case in manifest["cases"] if case["id"] == case_id), None)
    if source_case is None:
        raise ValueError(f"missing source case {case_id}")
    if evidence.get("source") != source_case["source"] or evidence.get("request") != source_case["request"]:
        raise ValueError(f"source/request drift for {case_id}")

    structural_gold = json.loads(source_case["gold"])
    return {
        "id": case_id,
        "family": case_id,
        "lane": "roles",
        "split": "development",
        "provenance": "synthetic-authored",
        "source": evidence["source"],
        "request": evidence["request"],
        "gold": json.dumps(
            {
                "initial_draft": evidence["drafts"][0],
                "facts": structural_gold["facts"],
                "minutes": structural_gold["minutes"],
                "activity_count": structural_gold["activity_count"],
            },
            ensure_ascii=False,
        ),
        "rubric": "role-repair-replay-v1",
    }


budget_document = json.loads(args.budget_from.read_text())
manifest = {
    "version": "quality-campaign-v1",
    "id": "m3-role-repair-replay-20260913",
    "purpose": (
        "Proposal-only replay of the two Round 3 baseline drafts manually confirmed as major failures. "
        "Compare matched two-wire self revision with one fresh-context role-separated specialist review plus one repair. "
        "Automated checks cover structure only; every final Draft requires clause-by-clause manual semantic review."
    ),
    "transport": "minimax",
    "adapter": "vibe_learner.role_repair_replay:run_sample",
    "concurrency": 2,
    "seed": 913,
    "repetitions": 1,
    "timeout_seconds": 60,
    "sample_deadline_seconds": 600,
    "sample_wire_limit": 2,
    "max_output_tokens": 4096,
    "input_reservation_tokens": 100000,
    "thinking": "adaptive",
    "temperature": 0.1,
    # Reuse the caller's single shared ledger budget verbatim.
    "budget": budget_document["budget"],
    "cases": [load_case(case_id) for case_id in CASE_IDS],
    "variants": [
        {"id": "self-revise-twice", "instruction": "Two sequential revisions by the same model."},
        {
            "id": "specialist-review-revise",
            "instruction": "One fresh-context role-separated source-grounding critic call followed by one repair call.",
        },
    ],
}

args.output.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
