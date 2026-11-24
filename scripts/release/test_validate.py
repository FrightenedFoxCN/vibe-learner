import json
import subprocess
import unittest
from unittest.mock import patch

import validate

REPO = "example/vibe-learner"
SHA = "a" * 40
SUCCESS = {
    "id": 42,
    "path": ".github/workflows/desktop-preflight.yml",
    "head_branch": "main",
    "head_sha": SHA,
    "head_repository": {"full_name": REPO},
    "event": "workflow_dispatch",
    "status": "completed",
    "conclusion": "success",
}


class ReleaseValidationTests(unittest.TestCase):
    def test_versions_agree_and_match_release_tag(self):
        expected = validate.check_versions(None)
        self.assertEqual(validate.check_versions(f"v{expected}"), expected)
        with self.assertRaisesRegex(ValueError, "Expected version"):
            validate.check_versions(f"v{expected}-different")

    def test_desktop_preflight_requires_exact_successful_main_run(self):
        rejected = (
            {"head_sha": "b" * 40},
            {"head_branch": "feature"},
            {"head_repository": {"full_name": "fork/vibe-learner"}},
            {"head_repository": None},
            {"path": ".github/workflows/desktop-preview.yml"},
            {"event": "pull_request"},
            {"status": "in_progress"},
            {"conclusion": "failure"},
            {"conclusion": "cancelled"},
            {"conclusion": "skipped"},
        )
        for overrides in rejected:
            with self.subTest(overrides=overrides):
                result = {"workflow_runs": [{**SUCCESS, **overrides}]}
                self.assertIsNone(validate.matching_preflight(result, REPO, SHA))
        self.assertEqual(
            validate.matching_preflight({"workflow_runs": [SUCCESS]}, REPO, SHA), 42
        )

    @patch("validate.subprocess.check_output")
    def test_queries_only_candidate_preflight_runs(self, read_runs):
        read_runs.return_value = json.dumps({"workflow_runs": [SUCCESS]})
        self.assertEqual(validate.require_preflight(REPO, SHA), 42)
        args = read_runs.call_args.args[0]
        self.assertIn(
            f"repos/{REPO}/actions/workflows/desktop-preflight.yml/runs", args
        )
        self.assertIn(f"head_sha={SHA}", args)
        self.assertIn("event=workflow_dispatch", args)
        self.assertIn("branch=main", args)
        self.assertIn("status=success", args)

    @patch("validate.subprocess.check_output")
    def test_no_preflight_result_or_api_failure_blocks_release(self, read_runs):
        read_runs.return_value = '{"workflow_runs": []}'
        with self.assertRaisesRegex(
            ValueError, "No successful Desktop Release Preflight"
        ):
            validate.require_preflight(REPO, SHA)
        read_runs.side_effect = subprocess.CalledProcessError(1, "gh")
        with self.assertRaises(subprocess.CalledProcessError):
            validate.require_preflight(REPO, SHA)


if __name__ == "__main__":
    unittest.main()
