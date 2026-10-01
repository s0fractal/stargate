"""Public receiver checks do not require or impersonate private Sokol source."""
import copy
import importlib.util
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('sokol_receipts', ROOT/'integration/sokol_receipts.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class SokolReceipts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selection, cls.payload = tool.store.fixture()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.connection = tool.store.connect(Path(tmp.name)/'state.sqlite')
        self.addCleanup(self.connection.close)
        tool.store.initialize(self.connection, self.selection)
        self.revision = tool.store.revise(self.connection, ack=True)['revision']
        self.raw = tool.store.certificate.canon(dict(operation='agent.1', revision=self.revision))

    def test_success_and_duplicate_reply_follow_actual_commit(self):
        first = tool.dispatch(self.connection, self.payload, self.raw)
        self.assertEqual(tool.acknowledge(first), b'OK applied\n')
        before = tool.store.snapshot(self.connection)
        again = tool.dispatch(self.connection, self.payload, self.raw)
        self.assertEqual(tool.acknowledge(again), b'OK duplicate\n')
        self.assertEqual(again['receipt'], first)
        self.assertEqual(tool.store.snapshot(self.connection), before)

    def test_incomplete_check_is_not_a_terminal_ack(self):
        before = tool.store.snapshot(self.connection)
        refused = tool.dispatch(self.connection, self.payload, self.raw, max_steps=0)
        self.assertEqual(refused['status'], 'not_admitted')
        self.assertIsNone(tool.acknowledge(refused))
        self.assertEqual(tool.store.snapshot(self.connection), before)
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM receipt').fetchone()[0], 0)
        self.assertEqual(tool.acknowledge(tool.dispatch(self.connection, self.payload, self.raw)), b'OK applied\n')

    def test_changed_conditions_before_retry_refuse_without_effect(self):
        tool.dispatch(self.connection, self.payload, self.raw, max_steps=0)
        before = tool.store.revise(self.connection, ack=False)
        refused = tool.dispatch(self.connection, self.payload, self.raw)
        self.assertEqual(tool.acknowledge(refused), b'OK refused stale_revision\n')
        self.assertEqual(tool.store.snapshot(self.connection), before)

    def test_conflicting_reuse_is_final_refusal_not_duplicate(self):
        tool.dispatch(self.connection, self.payload, self.raw)
        changed = tool.store.certificate.canon(dict(operation='agent.1', revision=self.revision+1))
        before = tool.store.snapshot(self.connection)
        refused = tool.dispatch(self.connection, self.payload, changed)
        self.assertEqual(tool.acknowledge(refused), b'OK refused operation_conflict\n')
        self.assertEqual(tool.store.snapshot(self.connection), before)

    def test_unknown_and_inconsistent_statuses_never_acknowledge_success(self):
        for result in ({}, dict(status='incomplete'), dict(status='checker_error'),
                       dict(status='applied', applied=False), dict(status='applied', applied=1),
                       dict(status='already_applied', applied=False),
                       dict(status='already_applied', applied=False, receipt=dict(status='applied', applied=False)),
                       dict(status='operation_conflict', applied=True)):
            with self.subTest(result=result):
                self.assertIsNone(tool.acknowledge(result))

    def test_wire_input_cannot_select_payload_or_database(self):
        for request in (dict(operation=None, revision=1), dict(operation='agent.1', revision=True),
                        dict(operation='agent.1', revision=1, database='other'),
                        dict(operation='agent.1', revision=1, payload={})):
            with self.subTest(request=request), self.assertRaises(ValueError):
                tool.dispatch(self.connection, self.payload, tool.store.certificate.canon(request))
        with self.assertRaises(ValueError):
            tool.dispatch(self.connection, self.payload, b'{"operation":"a","operation":"b","revision":1}')
        self.assertEqual(tool.store.snapshot(self.connection)['revision'], 1)

    def test_changed_proof_cannot_acknowledge_success(self):
        changed = copy.deepcopy(self.payload)
        changed['proofs']['custodian'] = b'{}'
        before = tool.store.snapshot(self.connection)
        with self.assertRaises(ValueError):
            tool.dispatch(self.connection, changed, self.raw)
        self.assertEqual(tool.store.snapshot(self.connection), before)
