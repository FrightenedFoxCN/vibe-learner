"""Opt-in project adapter acceptance, separate from app and standalone unit gates."""
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

from model_quality.protocol import Campaign
from model_quality.runner import run


from vibe_learner.fixtures import campaign


class DomainAcceptance(unittest.TestCase):
    def test_claim_without_memory_effect_is_candidate_failure(self):
        from vibe_learner import study
        from vibe_learner.common import Bridge, envelope
        from model_quality.adapters import Context
        from model_quality.ledger import Ledger
        from model_quality.transport import MeteredTransport
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            (root/'storage').mkdir()
            c=campaign('study')
            ledger=Ledger(root/'ledger.sqlite3')
            ledger.initialize(c.budget,'fake')
            context=Context(MeteredTransport(c,ledger,'claim-without-write',time.monotonic()+300),root/'storage',root/'domain.sqlite3')
            original=Bridge.__init__
            def initialize(bridge, context, fake):
                original(bridge,context,lambda payload: envelope(json.dumps({'text':'已经保存。','mood':'calm','action':'idle','interactive_question':None})))
            with patch.object(Bridge,'__init__',initialize):
                result=study.run_sample(context,c.cases[0],c.variants[0])
            self.assertEqual(result['status'],'candidate_failed')
            self.assertTrue(result['metrics']['committed'])
            self.assertFalse(result['metrics']['memory_exact'])
            self.assertFalse(result['metrics']['memory_effect_exact'])
            self.assertTrue(result['metrics']['restart_equal'])


    def test_study_and_tavern_isolated_commits_and_restart_readback(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            budget = campaign('study').budget.model_dump()
            outputs = []
            for domain in ('study', 'tavern'):
                c = campaign(domain, budget=budget)
                result = run(c, root/domain, root/'window.sqlite3')
                self.assertEqual(result['states'], {'completed': 2}, json.dumps(result['samples'], ensure_ascii=False))
                expected_wires = 6 if domain == 'study' else 2
                self.assertEqual(result['campaign_usage']['wire_count'], expected_wires)
                if domain == 'study':
                    offered = result['campaign_usage']['wires'][0]['metadata']['offered_tools']
                    self.assertIn('write_session_memory', offered)
                    self.assertIn('read_session_memory', offered)
                self.assertEqual(len(list((root/domain).glob('*/*/*/domain.sqlite3'))), 2)
                evidence = [json.loads(p.read_text()) for p in (root/domain).glob('*/*/*/storage/domain-evidence.json')]
                self.assertEqual(len({e['harness_operation_id'] for e in evidence}), 2)
                self.assertTrue(all(e['metrics']['restart_equal'] for e in evidence))
                resumed = run(c, root/domain, root/'window.sqlite3', resume=True)
                self.assertEqual(resumed['campaign_usage']['wire_count'], expected_wires)
                outputs.append(result)
            self.assertEqual(outputs[-1]['resource_window_usage']['wire_count'], 8)


if __name__ == '__main__':
    unittest.main()
