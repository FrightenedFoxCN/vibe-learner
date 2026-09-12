import tempfile
import time
from pathlib import Path
import unittest
from unittest.mock import patch

from model_quality.protocol import Autoscale, Campaign
from model_quality.ledger import GateClosed, Ledger, WaitForCapacity
from model_quality.scaling import observe
from model_quality.runner import run
from tests.test_infrastructure import config


def state():
    return dict(current=2, rate_factor=1., cooldown_until=0., window_started=0., healthy_windows=0, bad_windows=0, baseline_p95_ms=None)


def observations(at, n=30, latency=100, errors=0):
    return [dict(finished=at, state='finished', metadata=dict(elapsed_ms=latency, total_tokens=20, http_status=503 if i < errors else 200)) for i in range(n)]


class AutoscaleTests(unittest.TestCase):
    def test_two_full_windows_then_increase_and_latency_decrease(self):
        policy = Autoscale(max_concurrency=8).model_dump()
        first, reason = observe(state(), policy, observations(59), 60, 100)
        self.assertEqual(first['current'], 2)
        second, reason = observe(first, policy, observations(119), 120, 100)
        self.assertEqual((second['current'], reason), (4, 'healthy_up'))
        slow, reason = observe(second, policy, observations(179, latency=130), 180, 100)
        self.assertEqual((slow['current'], reason), (2, 'latency_down'))

    def test_no_scale_without_samples_time_backlog_or_known_usage(self):
        policy = Autoscale().model_dump()
        for wires, now in [(observations(59,n=29), 60), (observations(59),59)]:
            self.assertEqual(observe(state(),policy,wires,now,100), (state(),None))
        current = state()
        for now in (60,120,180):
            current, _ = observe(current, policy, observations(now-1), now, 1)
        self.assertEqual(current['current'],2)
        unknown = observations(240)
        unknown[0]['metadata']['total_tokens'] = None
        current, reason = observe(current,policy,unknown,241,100)
        self.assertEqual(reason,'hold_incomplete_evidence')

    def test_two_bad_windows_pause_infrastructure(self):
        policy = Autoscale().model_dump()
        first, _ = observe(state(),policy,observations(59,errors=2),60,100)
        second, reason = observe(first,policy,observations(119,errors=2),120,100)
        self.assertEqual(reason,'infrastructure_pause')

    def test_overload_is_immediate_durable_and_reservation_checks_cooldown(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=config()
            ledger=Ledger(Path(tmp)/'window.sqlite3')
            ledger.initialize(c.budget,'fake')
            ledger.configure_scaling(4,Autoscale(max_concurrency=4))
            wire=ledger.reserve('a','a',100)
            ledger.finish(wire,{'http_status':429,'total_tokens':None,'retry_after_seconds':12},None,stop_reason='provider_overload')
            control=ledger.tick_scaling(100)
            self.assertEqual(control['current'],2)
            self.assertIsNone(control['stopped'])
            with self.assertRaises(WaitForCapacity):
                ledger.reserve('a','b',100)
            ledger.configure_scaling(4,Autoscale(max_concurrency=4))
            self.assertEqual(ledger.tick_scaling(100)['current'],2)
            with patch('model_quality.ledger.time.time', return_value=control['cooldown_until']+1):
                ledger.reserve('a','b',100)
                ledger.reserve('a','c',100)
                with self.assertRaises(WaitForCapacity):
                    ledger.reserve('a','d',100)
            self.assertEqual(ledger.snapshot()['scaling_events'][-1]['reason'],'overload_down')

    def test_budget_extension_preserves_existing_usage(self):
        with tempfile.TemporaryDirectory() as tmp:
            c=config()
            ledger=Ledger(Path(tmp)/'window.sqlite3')
            ledger.initialize(c.budget,'fake')
            wire=ledger.reserve('old','a',100)
            with self.assertRaises(ValueError):
                ledger.amend_budget(c.budget,'inflight refused')
            ledger.finish(wire,{'total_tokens':None},None)
            bigger=c.budget.model_copy(update={'token_limit':200000})
            ledger.amend_budget(bigger,'authorized second batch')
            ledger.initialize(bigger,'fake')
            self.assertEqual(ledger.snapshot()['charged_or_reserved_tokens'],100)

    def test_live_shortened_windows_rejected(self):
        c=config().model_dump()
        c.update(transport='minimax',autoscale={'max_concurrency':4,'window_seconds':.1,'min_completed':1})
        with self.assertRaises(ValueError):
            Campaign.model_validate(c)

    def test_spawn_scheduler_scales_real_workers_under_fake_load(self):
        c=config().model_dump()
        c.update(concurrency=1,autoscale={'max_concurrency':4,'window_seconds':.05,'min_completed':2})
        c['cases']=[{**c['cases'][0],'id':str(i)} for i in range(16)]
        c['budget'].update(wire_limit=40,rpm=100,tpm=500000,token_limit=500000)
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            result=run(Campaign.model_validate(c),root/'run',root/'ledger.sqlite3')
            self.assertEqual(result['states'],{'completed':32})
            self.assertTrue(any(e['reason']=='healthy_up' and e['state']['current']>1 for e in result['campaign_usage']['scaling_events']))
            self.assertLessEqual(max(e['state']['current'] for e in result['campaign_usage']['scaling_events']),4)


if __name__ == '__main__':
    unittest.main()
