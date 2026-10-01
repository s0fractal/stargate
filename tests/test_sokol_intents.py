"""Public retained-sender contracts; fake transport is not Sokol evidence."""
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sokol_intents', ROOT/'integration/sokol_intents.py')
tool = importlib.util.module_from_spec(spec); spec.loader.exec_module(tool)


class Sender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selection, cls.payload = tool.store.fixture()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)/'db'
        self.c = tool.store.connect(self.path); self.addCleanup(self.c.close)
        tool.store.initialize(self.c, self.selection); tool.intents.initialize(self.c)
        self.rev = tool.store.revise(self.c, ack=True)['revision']
        tool.intents.enroll(self.c, 'job', self.rev, self.payload, 1)

    def send(self):
        return tool.send_once(self.c, 'job', '/trusted/sender', '/trusted/socket')

    def test_reservation_is_committed_before_launch_and_wire_is_retained(self):
        def launch(argv, **kwargs):
            c = tool.store.connect(self.path)
            try:
                intent = tool.intents.inspect(c, 'job')
                self.assertEqual(intent['attempts'], 1)
                self.assertEqual(argv, ['/trusted/sender', '/trusted/socket', tool.intents.wire(intent).decode()])
                tool.dispatch(c, argv[2].encode())
            finally:
                c.close()
            return subprocess.CompletedProcess(argv, 0, 'arbitrary output', '')
        with patch.object(tool.subprocess, 'run', launch):
            self.assertEqual(self.send()['status'], 'completed')
        with patch.object(tool.subprocess, 'run', side_effect=AssertionError('must not resend')):
            self.assertEqual(self.send()['status'], 'completed')

    def test_transport_success_without_receipt_is_not_completion(self):
        with patch.object(tool.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, 'OK applied', '')):
            result = self.send()
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(result['attempts'], 1)
        with patch.object(tool.subprocess, 'run', side_effect=AssertionError('budget exhausted')):
            self.assertEqual(self.send()['status'], 'budget_exhausted')

    def test_launch_error_spends_slot_without_effect(self):
        with patch.object(tool.subprocess, 'run', side_effect=OSError('missing executable')):
            result = self.send()
        self.assertEqual((result['status'], result['transport']['status']), ('pending', 'launch_error'))
        self.assertEqual(tool.intents.reserve(self.c, 'job')['status'], 'budget_exhausted')
        self.assertTrue(tool.store.snapshot(self.c)['state']['held'])

    def test_timeout_after_commit_recovers_receipt(self):
        def timeout(argv, **kwargs):
            tool.dispatch(self.c, argv[2].encode())
            raise subprocess.TimeoutExpired(argv, 10)
        with patch.object(tool.subprocess, 'run', timeout):
            result = self.send()
        self.assertEqual((result['status'], result['transport']['status']), ('completed', 'timeout'))

    def test_failed_child_never_creates_completion(self):
        with patch.object(tool.subprocess, 'run', return_value=subprocess.CompletedProcess([], 7, 'OK applied', '')):
            result = self.send()
        self.assertEqual(result['status'], 'pending')
        self.assertEqual(result['transport']['returncode'], 7)

    def test_cancel_between_reservation_and_delivery_fences_effect(self):
        def launch(argv, **kwargs):
            tool.intents.cancel(self.c, 'job')
            self.assertEqual(tool.dispatch(self.c, argv[2].encode())['status'], 'stale_revision')
            return subprocess.CompletedProcess(argv, 0)
        with patch.object(tool.subprocess, 'run', launch):
            self.assertEqual(self.send()['status'], 'cancelled')
        self.assertTrue(tool.store.snapshot(self.c)['state']['held'])

    def test_wire_cannot_override_retained_payload_or_revision(self):
        for request in (dict(operation='job', revision=self.rev+1), dict(operation='job', revision=True),
                        dict(operation='job', revision=self.rev, payload={})):
            with self.subTest(request=request), self.assertRaises(ValueError):
                tool.dispatch(self.c, tool.store.certificate.canon(request))
        self.assertTrue(tool.store.snapshot(self.c)['state']['held'])

    def test_receipt_consumer_mutant_is_detected(self):
        original = tool.intents.reconcile
        def false_completion(c, operation):
            return dict(original(c, operation), status='completed')
        # Execute the same refusal assertion against a consumer that substitutes
        # transport success for the receipt, and require an assertion failure.
        with patch.object(tool.intents, 'reconcile', false_completion):
            with self.assertRaises(AssertionError):
                self.test_transport_success_without_receipt_is_not_completion()
