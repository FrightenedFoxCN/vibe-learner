import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from model_quality.ledger import Ledger
from tests.test_infrastructure import config


class ReopenTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ledger=Ledger(Path(self.tmp.name)/'ledger.sqlite3')
        self.ledger.initialize(config().budget,'fake')
        self.ledger.configure_scaling(4,None)

    def overload(self):
        wire=self.ledger.reserve('old','sample',100)
        self.ledger.finish(wire,{'http_status':429,'total_tokens':None,'retry_after_seconds':120},None,stop_reason='provider_overload')

    def test_cooldown_audit_and_unknown_charge_retained(self):
        self.overload()
        before=self.ledger.snapshot()
        with self.assertRaises(ValueError):
            self.ledger.reopen_overload(concurrency=2,reason='authorized bounded experiment')
        with patch('model_quality.ledger.time.time',return_value=time.time()+121):
            self.ledger.reopen_overload(concurrency=2,reason='authorized bounded experiment')
        after=self.ledger.snapshot()
        self.assertEqual(before['wires'],after['wires'])
        self.assertEqual(after['charged_or_reserved_tokens'],100)
        self.assertIsNone(after['stopped'])
        self.ledger.configure_scaling(2,None)
        with self.ledger.transaction() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM overload_restarts').fetchone()[0],1)
        with self.assertRaises(ValueError):
            self.ledger.reopen_overload(concurrency=2,reason='duplicate restart')

    def test_inflight_and_other_stop_cannot_be_cleared(self):
        active=self.ledger.reserve('other','active',100)
        self.overload()
        with patch('model_quality.ledger.time.time',return_value=time.time()+121):
            with self.assertRaises(ValueError):
                self.ledger.reopen_overload(concurrency=2,reason='active refusal')
        self.ledger.finish(active,{},None,stop_reason='reservation_underestimated')
        with self.assertRaises(ValueError):
            self.ledger.reopen_overload(concurrency=2,reason='wrong stop')

    def test_expiry_and_unsafe_concurrency_refused(self):
        self.overload()
        for concurrency in (0,5,True):
            with self.assertRaises(ValueError):
                self.ledger.reopen_overload(concurrency=concurrency,reason='invalid concurrency')
        with patch('model_quality.ledger.time.time',return_value=time.time()+100000):
            with self.assertRaises(ValueError):
                self.ledger.reopen_overload(concurrency=2,reason='expired')
