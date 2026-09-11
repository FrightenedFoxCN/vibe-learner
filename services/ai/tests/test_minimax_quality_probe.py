"""Exploratory grader failures must not mislabel valid proposal boundaries."""
import unittest
from pydantic import ValidationError

from tests.acceptance.minimax_domain_probe import generation_boundary_success
from tests.acceptance.minimax_study_probe import safe_schema_errors
from app.models.study_chat_reply import StudyChatReplyProposalV1


class GenerationProbeBoundaryTests(unittest.TestCase):
    def test_question_diagnostics_keep_reason_without_candidate_values(self):
        payload = {"text": "请选择", "mood": "calm", "action": "point",
            "interactive_question": {"question_type": "multiple_choice", "prompt": "private sentinel",
                "options": [{"key": "A", "text": "one"}, {"key": "B", "text": "two"}]}}
        with self.assertRaises(ValidationError) as caught:
            StudyChatReplyProposalV1.model_validate(payload)
        errors = safe_schema_errors(caught.exception)
        self.assertEqual(errors, [{"type": "value_error", "loc": ("interactive_question",),
            "reason": "study_question_answer_key_required"}])
        self.assertNotIn("private sentinel", str(errors))

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
