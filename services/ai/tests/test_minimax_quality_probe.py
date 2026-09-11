"""Exploratory grader failures must not mislabel valid proposal boundaries."""
import unittest

from tests.acceptance.minimax_domain_probe import generation_boundary_success


class GenerationProbeBoundaryTests(unittest.TestCase):
    def test_proposals_allow_passed_and_repaired_without_claiming_domain_commit(self):
        for status in ("passed", "repaired"):
            with self.subTest(status=status):
                self.assertTrue(generation_boundary_success(True, [
                    {"status": status, "commit_evidence": {"status": "not_applicable"}},
                ]))

    def test_missing_readback_missing_trace_or_failed_attempt_cannot_pass(self):
        trace = {"status": "passed", "commit_evidence": {"status": "not_applicable"}}
        self.assertFalse(generation_boundary_success(False, [trace]))
        self.assertFalse(generation_boundary_success(True, []))
        self.assertFalse(generation_boundary_success(True, [
            trace, {"status": "failed", "commit_evidence": {"status": "not_committed"}},
        ]))

    def test_unexpected_committed_policy_is_not_silently_accepted(self):
        self.assertFalse(generation_boundary_success(True, [
            {"status": "passed", "commit_evidence": {"status": "committed"}},
        ]))
