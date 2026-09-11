"""Lower-bound tool coverage from checked-in admitted MiniMax experiment evidence."""
import argparse
import json
from pathlib import Path
import subprocess

from app.models.tool_manifest import TOOL_MANIFEST_REGISTRY


def run(evidence: Path, output: Path):
    coverage = {(t.workflow.value, t.canonical_name): {"requested": set(), "successful": set(), "committed": set()}
        for t in TOOL_MANIFEST_REGISTRY.tools}
    files = []
    for path in sorted(evidence.glob("minimax-*.jsonl")):
        files.append(path.name)
        for line in path.read_text().splitlines():
            row = json.loads(line)
            operation = row.get("harness_operation_id")
            if not operation or row.get("model") != "MiniMax-M3":
                continue
            scope = row.get("scope")
            if scope == "live_planning_admission_commit_readback":
                workflow = "planning"
                results = row.get("tool_diagnostics", [])
            elif scope == "live_study_operation_receipt_readback":
                workflow = "study_chat"
                result = (row.get("receipt") or {}).get("result") or {}
                results = [{"tool_name": t["tool_name"], **json.loads(t["result_json"])} for t in result.get("tool_calls", [])]
            else:
                continue
            for call in row.get("calls", []):
                for name in call.get("requested_tools", []):
                    if (workflow, name) in coverage:
                        coverage[(workflow, name)]["requested"].add(operation)
            for result in results:
                name = result.get("tool_name")
                if (workflow, name) not in coverage:
                    continue
                entry = coverage[(workflow, name)]
                entry["requested"].add(operation)
                if result.get("ok") is True:
                    entry["successful"].add(operation)
                    if row.get("boundary_success") is True:
                        entry["committed"].add(operation)
    rows = [{"workflow": workflow, "tool": name,
        "requested_operations": len(v["requested"]), "successful_tool_operations": len(v["successful"]),
        "successful_tool_and_boundary_operations": len(v["committed"])} for (workflow, name), v in sorted(coverage.items())]
    output.write_text(json.dumps({"scope": "admitted-operation tool coverage lower bound",
        "git_revision": subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip(),
        "limitations": ["Deduplicated by Harness operation ID, including duplicated evidence exports.",
            "Missing tool result diagnostics are unknown, not failure.",
            "Tool ok and domain commit do not prove answer quality, native image receipt, or independent review.",
            "Direct provider experiments without admission are excluded."],
        "source_files": files, "tools": rows}, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    run(args.evidence, args.output)
