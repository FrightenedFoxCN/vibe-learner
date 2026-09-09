"""Embedding payload and decode behavior without a model SDK or database."""
import unittest
from unittest.mock import Mock

from app.services.provider_embedding import RemoteEmbeddingProvider


class EmbeddingProviderTests(unittest.TestCase):
    def test_blank_input_does_not_issue_request(self):
        request = Mock()
        self.assertEqual(RemoteEmbeddingProvider("embed", request).embed_texts(["", "  "]), [])
        request.assert_not_called()

    def test_clean_input_and_preserve_vector_order(self):
        request = Mock(return_value=({"data": [
            {"embedding": [1, "2.5"]}, {"other": []}, {"embedding": [3, 4]},
        ]}, 1))
        result = RemoteEmbeddingProvider("embed", request).embed_texts([" first ", "", "second"])
        self.assertEqual(result, [[1.0, 2.5], [3.0, 4.0]])
        request.assert_called_once_with({"model": "embed", "input": ["first", "second"]}, model="embed")

    def test_provider_failure_is_not_retried_at_capability_layer(self):
        request = Mock(side_effect=RuntimeError("embedding_request_timeout"))
        with self.assertRaisesRegex(RuntimeError, "embedding_request_timeout"):
            RemoteEmbeddingProvider("embed", request).embed_texts(["text"])
        self.assertEqual(request.call_count, 1)
