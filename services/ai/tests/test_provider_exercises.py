"""Independent exercises remain local for both provider configurations."""
from dataclasses import asdict
import unittest
from unittest.mock import patch

from app.services.model_provider import MockModelProvider, OpenAIModelProvider
from tests.support.study_chat_samples import study_persona


class ProviderExerciseContractTests(unittest.TestCase):
    def provider(self):
        return OpenAIModelProvider(api_key="test", base_url="http://127.0.0.1:9/v1", plan_model="test")

    def test_real_provider_does_not_inherit_mock_behavior(self):
        self.assertFalse(issubclass(OpenAIModelProvider, MockModelProvider))
        self.assertEqual(self.provider().exercise_implementation, "local_heuristic")

    def test_exercise_matches_existing_local_output_without_transport(self):
        provider = self.provider()
        persona = study_persona()
        with patch.object(provider, "_sdk_adapter", side_effect=AssertionError("exercise called transport")):
            result = provider.generate_exercise(persona=persona, section_id="unit-1", topic="线性空间")
        self.assertEqual(result.text, "围绕 unit-1 的 线性空间，请你先用三句话概括概念，再举一个教材中的例子。")
        self.assertEqual(result.mood, "encouraging")
        self.assertEqual(result.action, "lean_in")
        self.assertEqual(result.speech_style, persona.default_speech_style)
        self.assertEqual(asdict(result), asdict(MockModelProvider().generate_exercise(persona=persona, section_id="unit-1", topic="线性空间")))

    def test_submission_keeps_existing_length_heuristic_and_no_transport(self):
        provider = self.provider()
        persona = study_persona()
        for answer, quality, mood in [("  短答  ", "偏短", "concerned"), ("x" * 25, "完整", "excited")]:
            with self.subTest(quality=quality), patch.object(provider, "_sdk_adapter", side_effect=AssertionError("grading called transport")):
                result = provider.grade_submission(persona=persona, exercise_id="exercise-1", answer=answer)
                self.assertEqual(result.text, f"针对练习 exercise-1，你的回答{quality}。 我会指出遗漏点，并给出下一步复习建议。")
                self.assertEqual(result.mood, mood)
                self.assertEqual(asdict(result), asdict(MockModelProvider().grade_submission(persona=persona, exercise_id="exercise-1", answer=answer)))
