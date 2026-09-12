from pathlib import Path
import tempfile
import time
import unittest

from model_quality.adapters import Context
from model_quality.ledger import Ledger
from model_quality.protocol import Campaign
from model_quality.transport import MeteredTransport
from vibe_learner.capacity import run_sample
from vibe_learner.fixtures import campaign


class CapacitySampleTests(unittest.TestCase):
    def test_invalid_proposal_does_not_stop_load_or_issue_repair_wire(self):
        c=campaign('tavern').model_copy(update={'sample_wire_limit':1,'max_output_tokens':768,'input_reservation_tokens':16384})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            ledger=Ledger(root/'ledger.sqlite3')
            ledger.initialize(c.budget,'fake')
            context=Context(MeteredTransport(c,ledger,'one',time.monotonic()+90),root,root/'unused.sqlite3')
            result=run_sample(context,c.cases[0],c.variants[0])
            self.assertEqual(result['status'],'candidate_failed')
            self.assertEqual(ledger.snapshot()['wire_count'],1)
            self.assertIsNone(ledger.snapshot()['stopped'])

    def test_invalid_proposals_keep_a_full_load_window_running(self):
        from model_quality.capacity import run_window
        c=campaign('tavern').model_copy(update={'sample_wire_limit':1,'max_output_tokens':768,
            'input_reservation_tokens':16384,'adapter':'vibe_learner.capacity:run_sample'})
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            ledger=Ledger(root/'ledger.sqlite3')
            ledger.initialize(c.budget,'fake')
            result=run_window(c,ledger,root,2,0,.3,4,2.)
            self.assertGreaterEqual(result['elapsed_seconds'],.3)
            self.assertGreaterEqual(result['requests'],4)
            self.assertEqual(result['proposal_successes'],0)
            self.assertEqual(result['requests'],result['completed_samples'])
