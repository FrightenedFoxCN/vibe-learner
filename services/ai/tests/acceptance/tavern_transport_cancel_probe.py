"""Run focused real-HTTP production adapter checks and retain honest evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
from pathlib import Path
import subprocess
import sys
import unittest

from tests.test_provider_cancellation import EVIDENCE, ProviderCancellationTests


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=Path("/tmp/vibe-tavern-transport-cancel.json")
    )
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(ProviderCancellationTests)
    result = unittest.TextTestRunner(verbosity=1).run(suite)
    root = Path(__file__).resolve().parents[4]
    files = [
        "services/ai/app/services/provider_cancellation.py",
        "services/ai/app/services/provider_http_chat.py",
        "services/ai/app/services/provider_sdk.py",
        "services/ai/app/services/provider_transport.py",
        "services/ai/app/services/model_provider.py",
        "services/ai/app/services/provider_capabilities.py",
        "services/ai/app/services/tavern.py",
        "services/ai/app/persistence/tavern_repository.py",
        "services/ai/tests/test_provider_cancellation.py",
    ]
    payload = {
        "contract": "tavern-transport-cancel-probe-v1",
        "source_revision": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip(),
        "worktree_state": "dirty"
        if subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=root, text=True
        ).strip()
        else "clean",
        "implementation_sha256": {
            name: hashlib.sha256((root / name).read_bytes()).hexdigest()
            for name in files
        },
        "environment": {
            "platform": platform.platform(),
            "python": platform.python_version(),
            "network": "loopback-only",
            "production_adapter": "compatible-chat-http-v1",
            "live_provider_calls": 0,
        },
        "status": "passed" if result.wasSuccessful() else "failed",
        "tests": result.testsRun,
        "cases": EVIDENCE,
        "limitations": [
            "Socket EOF proves local disconnect only",
            "Provider computation/billing stop remains unverified",
            "Other native LiteLLM protocols retain synchronous fallback",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": payload["status"],
                "tests": payload["tests"],
                "output": str(args.output),
            }
        )
    )
    sys.exit(0 if result.wasSuccessful() else 1)
