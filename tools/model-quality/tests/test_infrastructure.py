import json
import multiprocessing
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from pydantic import ValidationError

from model_quality.ledger import GateClosed, Ledger, WaitForCapacity
from model_quality.protocol import AdapterResult, Budget, Campaign
from model_quality.runner import Checkpoints, exclusive, report_only, run
from model_quality.transport import MeteredTransport, NoRedirect, WireFailure, usage_metadata


def config(**overrides):
    value = dict(version='quality-campaign-v1', id='test', purpose='infrastructure regression',
                 transport='fake', concurrency=4,
                 budget=dict(token_limit=100000, wire_limit=20, rpm=30, tpm=100000,
                             max_inflight=4, expires_at=time.time()+3600),
                 cases=[dict(id='a', family='a', lane='preflight', provenance='synthetic-authored',
                             source='Synthetic control.', request='Reply OK', gold='OK', rubric='exact-text-v1'),
                        dict(id='b', family='b', lane='preflight', provenance='synthetic-authored',
                             source='合成控制。', request='Reply OK', gold='OK', rubric='exact-text-v1')],
                 variants=[dict(id='baseline', instruction='Follow the request.'), dict(id='precise', instruction='Reply precisely.')])
    value.update(overrides)
    return Campaign.model_validate(value)


def reserve_worker(path, sample, queue):
    try:
        queue.put(('ok', Ledger(Path(path)).reserve('parallel', sample, 100)))
    except (GateClosed, WaitForCapacity) as exc:
        queue.put(('blocked', type(exc).__name__))


class InfrastructureTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.c = config()
        self.ledger = Ledger(self.root / 'ledger.sqlite3')
        self.ledger.initialize(self.c.budget, 'fake')

    def tearDown(self):
        self.tmp.cleanup()

    def test_spawn_processes_cannot_overspend(self):
        path = self.root / 'tiny.sqlite3'
        ledger = Ledger(path)
        ledger.initialize(self.c.budget.model_copy(update={'token_limit': 250}), 'fake')
        ctx = multiprocessing.get_context('spawn')
        queue = ctx.Queue()
        jobs = [ctx.Process(target=reserve_worker, args=(str(path), str(i), queue)) for i in range(8)]
        for job in jobs:
            job.start()
        results = [queue.get(timeout=20) for _ in jobs]
        for job in jobs:
            job.join(timeout=10)
            self.assertEqual(job.exitcode, 0)
        self.assertEqual(sum(row[0] == 'ok' for row in results), 2)
        self.assertEqual(ledger.snapshot()['charged_or_reserved_tokens'], 200)

    def test_unknown_usage_and_recovered_crash_keep_reservations(self):
        wire = self.ledger.reserve('one', 'a', 100)
        self.ledger.finish(wire, {'total_tokens': None}, None)
        self.ledger.reserve('one', 'b', 200)
        self.ledger.recover('one', 'b')
        self.assertEqual(self.ledger.snapshot()['charged_or_reserved_tokens'], 300)
        self.assertEqual(self.ledger.snapshot()['unknown_usage_requests'], 2)
        with self.assertRaises(GateClosed):
            self.ledger.reserve('one', 'b', 200)

    def test_actual_usage_reconciles_and_underestimate_halts(self):
        wire = self.ledger.reserve('one', 'a', 100)
        self.ledger.finish(wire, {'total_tokens': 25}, 25)
        self.assertEqual(self.ledger.snapshot()['charged_or_reserved_tokens'], 25)
        with self.assertRaises(ValueError):
            self.ledger.finish(wire, {}, 0)
        wire = self.ledger.reserve('two', 'a', 100)
        self.ledger.finish(wire, {'total_tokens': 120}, 120)
        with self.assertRaises(GateClosed):
            self.ledger.reserve('two', 'b', 1)

    def test_rate_concurrency_expiry_and_wire_gates(self):
        for field, value in [('rpm', 1), ('max_inflight', 1), ('tpm', 100), ('wire_limit', 1)]:
            ledger = Ledger(self.root / (field + '.sqlite3'))
            ledger.initialize(self.c.budget.model_copy(update={field: value}), 'fake')
            ledger.reserve('a', 'a', 100)
            with self.assertRaises((GateClosed, WaitForCapacity)):
                ledger.reserve('b', 'b', 100)
        with patch('model_quality.ledger.time.time', return_value=self.c.budget.expires_at):
            with self.assertRaises(GateClosed):
                self.ledger.reserve('a', 'a', 1)

    def test_cumulative_ledger_is_immutable_across_batches(self):
        self.ledger.initialize(self.c.budget, 'fake')
        with self.assertRaises(ValueError):
            self.ledger.initialize(self.c.budget.model_copy(update={'token_limit': 200000}), 'fake')
        self.ledger.bind_campaign('a', 'first')
        with self.assertRaises(ValueError):
            self.ledger.bind_campaign('a', 'second')

    def test_adapter_owns_rubric_and_rejects_unknown_before_network(self):
        from model_quality.adapters import Context, text_probe
        transport = MeteredTransport(self.c, self.ledger, 'unknown-rubric', time.monotonic()+180)
        case = self.c.cases[0].model_copy(update={'rubric': 'another-project-rubric-v1'})
        result = text_probe(Context(transport, self.root, self.root/'domain.sqlite3'),case,self.c.variants[0])
        self.assertEqual(result['status'], 'data_failed')
        self.assertEqual(self.ledger.snapshot()['wire_count'], 0)

    def test_unsupported_images_are_rejected_before_wire_admission(self):
        transport = MeteredTransport(self.c, self.ledger, 'image', time.monotonic()+180)
        with self.assertRaises(GateClosed):
            transport.complete([{'role': 'user', 'content': [{'type': 'image_url', 'image_url': {'url': 'https://example/image'}}]}])
        self.assertEqual(self.ledger.snapshot()['wire_count'], 0)

    def test_usage_missing_details_and_inconsistent_total_remain_unknown(self):
        self.assertIsNone(usage_metadata({})['total_tokens'])
        row = usage_metadata({'usage': {'prompt_tokens': 2, 'completion_tokens': 3, 'total_tokens': 4}})
        self.assertIsNone(row['total_tokens'])
        self.assertIsNone(row['cached_tokens'])

    def test_isolated_spawn_checkpoint_resume_and_changed_config(self):
        output = self.root / 'run'
        result = run(self.c, output, self.ledger.path)
        self.assertEqual(result['states'], {'completed': 4})
        self.assertEqual(len({s['result']['pid'] for s in result['samples']}), 4)
        self.assertEqual(len(list(output.glob('*/*/*/domain.sqlite3'))), 4)
        replay = run(self.c, output, self.ledger.path, resume=True)
        self.assertEqual(replay['campaign_usage']['wire_count'], 4)
        with self.assertRaises(ValueError):
            run(self.c.model_copy(update={'seed': 123}), output, self.ledger.path, resume=True)
        self.assertNotIn('reasoning_content', (output/'report.json').read_text())

    def test_resume_marks_interrupted_sample_uncertain_without_replay(self):
        output = self.root/'run'
        run(self.c, output, self.ledger.path)
        cp = Checkpoints(output/'checkpoints.sqlite3')
        sid = cp.rows()[0]['id']
        with cp.connection() as db:
            db.execute("UPDATE samples SET state='running',result=NULL WHERE id=?", (sid,))
        result = run(self.c, output, self.ledger.path, resume=True)
        self.assertEqual(result['states'], {'completed': 3, 'uncertain': 1})
        self.assertEqual(result['campaign_usage']['wire_count'], 4)

    def test_active_worker_lock_blocks_recovery_and_report_rebuild_is_offline(self):
        output = self.root/'owned'
        run(self.c, output, self.ledger.path)
        cp = Checkpoints(output/'checkpoints.sqlite3')
        row = cp.rows()[0]
        with cp.connection() as db:
            db.execute("UPDATE samples SET state='running' WHERE id=?", (row['id'],))
        identity = json.loads(row['identity'])
        lock = output/identity['case']/identity['variant']/str(identity['repetition'])/'worker.lock'
        with exclusive(lock):
            with self.assertRaises(RuntimeError):
                run(self.c, output, self.ledger.path, resume=True)
        with patch('model_quality.runner.source_state', side_effect=AssertionError('no code execution')):
            result = report_only(self.c, output, self.ledger.path)
        self.assertEqual(result['states'], {'completed': 3, 'running': 1})
        self.assertEqual(result['campaign_usage']['wire_count'], 4)
        self.assertTrue(cp.running(row['id']))
        latencies = [r['metadata']['elapsed_ms'] for r in result['campaign_usage']['wires']]
        self.assertEqual(result['wire_latency_ms']['95'], max(latencies))

    def test_real_worker_crash_retains_inflight_and_is_never_replayed(self):
        c = self.c.model_copy(update={'adapter': 'tests.fault_adapters:crash_after_reserve'})
        output = self.root/'crash'
        result = run(c, output, self.ledger.path)
        self.assertEqual(result['states'], {'uncertain': 4})
        self.assertEqual(result['campaign_usage']['charged_or_reserved_tokens'], 400)
        self.assertTrue(all(r['state'] == 'uncertain' for r in result['campaign_usage']['wires']))
        resumed = run(c, output, self.ledger.path, resume=True)
        self.assertEqual(resumed['campaign_usage']['wire_count'], 4)

    def test_adapter_exception_cannot_leave_inflight_slot_or_claim_success(self):
        c = self.c.model_copy(update={'adapter': 'tests.fault_adapters:raise_after_reserve'})
        result = run(c, self.root/'raise', self.ledger.path)
        self.assertEqual(result['states'], {'uncertain': 4})
        self.assertTrue(all(r['state'] == 'uncertain' for r in result['campaign_usage']['wires']))
        self.assertEqual(result['campaign_usage']['charged_or_reserved_tokens'], 400)

    def test_invalid_metrics_are_not_candidate_failures_or_success(self):
        c = self.c.model_copy(update={'adapter': 'tests.fault_adapters:invalid_metric'})
        result = run(c, self.root/'badmetric', self.ledger.path)
        self.assertEqual(result['states'], {'metric_failed': 4})
        self.assertEqual(result['campaign_usage']['wire_count'], 0)

    def test_sample_deadline_terminates_hung_worker(self):
        c = self.c.model_copy(update={'adapter': 'tests.fault_adapters:hang',
                                     'sample_deadline_seconds': 2, 'timeout_seconds': 1})
        started = time.monotonic()
        result = run(c, self.root/'hang', self.ledger.path)
        self.assertEqual(result['states'], {'uncertain': 4})
        self.assertLess(time.monotonic()-started, 15)

    def test_second_campaign_cannot_reset_resource_wire_limit(self):
        budget = self.c.budget.model_copy(update={'wire_limit': 4})
        c = self.c.model_copy(update={'budget': budget})
        path = self.root/'shared.sqlite3'
        first = run(c, self.root/'first', path)
        self.assertEqual(first['states'], {'completed': 4})
        second = run(c.model_copy(update={'id': 'second'}), self.root/'second', path)
        self.assertEqual(second['states'], {'stopped': 4})
        self.assertEqual(second['resource_window_usage']['wire_count'], 4)
        self.assertEqual(second['campaign_usage']['wire_count'], 0)

    def test_http_auth_and_overload_stop_without_retry_or_secret_log(self):
        import urllib.error
        for status in (401, 403, 429, 529):
            ledger = Ledger(self.root/f'http{status}.sqlite3')
            ledger.initialize(self.c.budget, 'minimax')
            live = self.c.model_copy(update={'transport': 'minimax'})
            transport = MeteredTransport(live, ledger, 'sample', time.monotonic()+180)
            opener = unittest.mock.Mock()
            opener.open.side_effect = urllib.error.HTTPError('https://example', status, 'SECRET_SENTINEL', {}, None)
            with patch.dict('os.environ', {'K3_API_KEY': 'SECRET_SENTINEL'}), patch('urllib.request.build_opener', return_value=opener):
                with self.assertRaises(WireFailure):
                    transport.complete([{'role': 'user', 'content': 'Hello'}])
            snapshot = ledger.snapshot()
            self.assertEqual(snapshot['wire_count'], 1)
            self.assertIsNotNone(snapshot['stopped'])
            self.assertNotIn('SECRET_SENTINEL', json.dumps(snapshot))

    def test_http_200_provider_error_is_infrastructure_and_stops(self):
        from unittest.mock import MagicMock
        live = self.c.model_copy(update={'transport': 'minimax'})
        transport = MeteredTransport(live, self.ledger, 'envelope', time.monotonic()+180)
        response = MagicMock()
        response.__enter__.return_value = response
        response.status = 200
        response.read.return_value = b'{"base_resp":{"status_code":1004,"status_msg":"SECRET_SENTINEL"}}'
        opener = MagicMock()
        opener.open.return_value = response
        with patch.dict('os.environ', {'K3_API_KEY': 'SECRET_SENTINEL'}), patch('urllib.request.build_opener', return_value=opener):
            with self.assertRaises(WireFailure) as caught:
                transport.complete([{'role': 'user', 'content': 'Hello'}])
        self.assertEqual(caught.exception.code, 'provider_error_envelope')
        self.assertFalse(caught.exception.uncertain)
        snapshot = self.ledger.snapshot()
        self.assertEqual(snapshot['stopped'], 'provider_error_envelope')
        self.assertEqual(snapshot['wire_count'], 1)
        self.assertNotIn('SECRET_SENTINEL', json.dumps(snapshot))

    def test_no_redirect_or_reserved_split_and_strict_result_ownership(self):
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, '', {}, 'https://example'))
        data = self.c.model_dump()
        data['cases'][0]['split'] = 'reserved'
        with self.assertRaises(ValidationError):
            Campaign.model_validate(data)
        with self.assertRaises(ValidationError):
            AdapterResult(status='completed', failure_owner='candidate')


if __name__ == '__main__':
    unittest.main()
