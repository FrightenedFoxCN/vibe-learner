"""Shared manifest and desktop preflight checks for release candidates."""

import argparse
import json
from pathlib import Path
import re
import subprocess
import tomllib

ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = {
    "package.json": ("version",),
    "apps/web/package.json": ("version",),
    "apps/desktop/package.json": ("version",),
    "packages/shared/package.json": ("version",),
    "services/ai/pyproject.toml": ("project", "version"),
    "apps/desktop/src-tauri/tauri.conf.json": ("version",),
    "apps/desktop/src-tauri/Cargo.toml": ("package", "version"),
}
PREFLIGHT_WORKFLOW = "desktop-preflight.yml"


def check_versions(tag: str | None) -> str:
    versions = {}
    for name, keys in MANIFESTS.items():
        manifest = ROOT / name
        load = tomllib.loads if manifest.suffix == ".toml" else json.loads
        value = load(manifest.read_text(encoding="utf-8"))
        for key in keys:
            value = value[key]
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Invalid version in {name}")
        versions[name] = value
    expected = versions["package.json"]
    if tag is not None:
        if not tag.startswith("v") or len(tag) == 1:
            raise ValueError("Expected a release tag like vX.Y.Z")
        expected = tag[1:]
    mismatches = [
        f"{name}={version}" for name, version in versions.items() if version != expected
    ]
    if mismatches:
        raise ValueError(f"Expected version {expected}; found {', '.join(mismatches)}")
    return expected


def matching_preflight(result: dict, repository: str, sha: str) -> int | None:
    for run in result["workflow_runs"]:
        if (
            run.get("path") == f".github/workflows/{PREFLIGHT_WORKFLOW}"
            and run.get("head_sha") == sha
            and run.get("head_branch") == "main"
            and (run.get("head_repository") or {}).get("full_name") == repository
            and run.get("event") == "workflow_dispatch"
            and run.get("status") == "completed"
            and run.get("conclusion") == "success"
        ):
            return int(run["id"])
    return None


def require_preflight(repository: str, sha: str) -> int:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Expected repository in owner/name form")
    if not re.fullmatch(r"[a-f0-9]{40}", sha):
        raise ValueError("Expected the full release commit SHA")
    response = subprocess.check_output(
        [
            "gh",
            "api",
            "--method",
            "GET",
            f"repos/{repository}/actions/workflows/{PREFLIGHT_WORKFLOW}/runs",
            "-f",
            f"head_sha={sha}",
            "-f",
            "branch=main",
            "-f",
            "event=workflow_dispatch",
            "-f",
            "status=success",
            "-F",
            "per_page=100",
        ],
        text=True,
        timeout=30,
    )
    run_id = matching_preflight(json.loads(response), repository, sha)
    if run_id is None:
        raise ValueError(
            f"No successful Desktop Release Preflight for {sha}. "
            "Run the preflight from main at that commit before publishing."
        )
    return run_id


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    versions = commands.add_parser("versions")
    versions.add_argument("--tag")
    preflight = commands.add_parser("preflight")
    preflight.add_argument("repository")
    preflight.add_argument("sha")
    args = parser.parse_args()
    try:
        if args.command == "versions":
            print(f"All release manifests agree on {check_versions(args.tag)}.")
        else:
            run_id = require_preflight(args.repository, args.sha)
            print(
                f"Preflight: https://github.com/{args.repository}/actions/runs/{run_id}"
            )
    except (ValueError, KeyError, OSError, subprocess.SubprocessError) as exc:
        raise SystemExit(f"Release validation failed: {exc}") from exc


if __name__ == "__main__":
    main()
