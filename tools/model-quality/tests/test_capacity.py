import tempfile
from pathlib import Path
import unittest

from model_quality.capacity import select_stage, restore_control, summarize
from model_quality.ledger import Ledger, GateClosed
from tests.test_infrastructure import config


class CapacityTests(unittest.TestCase):
    def test_measures_actual_overlap_tail_and_failure(self):
        wires=[{'started':0.,'finished':2.,'state':'finished','charged':10,'metadata':{'http_status':200,'elapsed_ms':2000,'total_tokens':10}},
               {'started':1.,'finished':4.,'state':'finished','charged':20,'metadata':{'http_status':429,'elapsed_ms':3000,'total_tokens':None}}]
        result=summarize(wires,0.,4.)
        self.assertEqual(result['observed_peak_inflight'],2)
        self.assertEqual(result['p95_ms'],3000)
        self.assertEqual(result['infrastructure_error_rate'],.5)
        self.assertEqual(result['requests_per_second'],.5)
        self.assertEqual(result['unknown_usage_requests'],1)

    def test_explicit_stages_fence_other_campaigns_and_restore_without_usage_reset(self):
        c=config()
        with tempfile.TemporaryDirectory() as tmp:
            ledger=Ledger(Path(tmp)/'ledger.sqlite3')
            ledger.initialize(c.budget,'fake')
            ledger.configure_scaling(2,None)
            previous=select_stage(ledger,'probe',4,'capacity_begin')
            with self.assertRaises(GateClosed):
                ledger.reserve('other','a',100)
            wire=ledger.reserve('probe','a',100)
            with self.assertRaises(ValueError):
                select_stage(ledger,'probe',2,'capacity_down')
            ledger.finish(wire,{'total_tokens':20},20)
            restore_control(ledger,previous)
            self.assertEqual(ledger.tick_scaling(0)['current'],2)
            self.assertEqual(ledger.snapshot()['charged_or_reserved_tokens'],20)

    def test_stage_cannot_clear_provider_stop(self):
        c=config()
        with tempfile.TemporaryDirectory() as tmp:
            ledger=Ledger(Path(tmp)/'ledger.sqlite3')
            ledger.initialize(c.budget,'fake')
            ledger.configure_scaling(2,None)
            previous=select_stage(ledger,'probe',4,'capacity_begin')
            wire=ledger.reserve('probe','a',100)
            ledger.finish(wire,{'http_status':429},None,stop_reason='provider_overload')
            with self.assertRaises(GateClosed):
                select_stage(ledger,'probe',2,'retry')
            restore_control(ledger,previous)
            self.assertEqual(ledger.snapshot()['stopped'],'provider_overload')
