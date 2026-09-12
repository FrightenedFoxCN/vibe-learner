import unittest
from pydantic import ValidationError
from model_quality.protocol import Case

class PublicFixtureProvenanceTests(unittest.TestCase):
    def test_public_sources_are_distinct_from_synthetic_and_still_strict(self):
        base=dict(id='public-photo',family='public-photo',lane='grounding',source='Frozen source URL/license/digest recorded by adapter.',request='Find a cup.',gold='Frozen manual annotation.',rubric='natural-grounding-v1')
        for value in ('synthetic-authored','public-licensed','user-provided'):
            self.assertEqual(Case(**base,provenance=value).provenance,value)
        for value in ('unknown','user-private',None):
            with self.assertRaises(ValidationError):Case(**base,provenance=value)
