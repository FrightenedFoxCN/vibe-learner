import os
from pathlib import Path
import socket
import tempfile
import unittest
from unittest.mock import patch
from model_quality.ledger import Ledger
from model_quality.runner import run, Checkpoints
from tests.test_infrastructure import config


class DNSPreflightTests(unittest.TestCase):
    def test_dns_failure_leaves_pending_without_wire_or_domain_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            c=config().model_copy(update={'transport':'minimax'})
            with patch.dict(os.environ,{'K3_API_KEY':'fake-not-sent'}), patch('socket.getaddrinfo',side_effect=socket.gaierror('blocked')):
                with self.assertRaises(socket.gaierror):
                    run(c,root/'run',root/'ledger.sqlite3')
            self.assertEqual(Ledger(root/'ledger.sqlite3').snapshot()['wire_count'],0)
            self.assertTrue(all(r['state']=='pending' for r in Checkpoints(root/'run/checkpoints.sqlite3').rows()))
