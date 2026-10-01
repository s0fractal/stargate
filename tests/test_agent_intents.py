"""Retained budgets and cancellation must survive interruption and stale workers."""
from concurrent.futures import ThreadPoolExecutor
import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('agent_intents', ROOT/'integration/agent_intents.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class AgentIntents(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selection, cls.payload = tool.store.fixture()

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = Path(tmp.name)/'state.sqlite'
        self.connection = tool.store.connect(self.path)
        self.addCleanup(self.connection.close)
        tool.store.initialize(self.connection, self.selection)
        tool.initialize(self.connection)
        self.revision = tool.store.revise(self.connection, ack=True)['revision']

    def enroll(self, budget=1):
        return tool.enroll(self.connection, 'job', self.revision, self.payload, budget)

    def test_recovery_reconciles_even_after_budget_exhaustion(self):
        self.enroll()
        first = tool.attempt(self.connection, 'job')
        self.assertEqual(first['status'], 'completed')
        other = tool.store.connect(self.path)
        try:
            with patch.object(tool.store, 'release', side_effect=AssertionError('must not execute again')):
                replay = tool.attempt(other, 'job', max_steps=0)
            self.assertEqual(replay['status'], 'completed')
            self.assertEqual(replay['attempts'], 1)
            self.assertEqual(replay['receipt']['receipt'], first['outcome'])
        finally:
            other.close()

    def test_attempt_budget_survives_reopen_and_incomplete_checks(self):
        self.enroll(2)
        for _ in range(2):
            other = tool.store.connect(self.path)
            try:
                result = tool.attempt(other, 'job', max_steps=0)
                self.assertEqual(result['outcome']['status'], 'not_admitted')
                self.assertEqual(result['status'], 'pending')
            finally:
                other.close()
        with patch.object(tool.store, 'release', side_effect=AssertionError('exhausted budget')):
            self.assertEqual(tool.attempt(self.connection, 'job')['status'], 'budget_exhausted')
        self.assertEqual(tool.store.snapshot(self.connection)['revision'], self.revision)
        with self.assertRaises(sqlite3.IntegrityError):
            self.enroll(3)

    def test_cancel_between_reservation_and_effect_invalidates_old_revision(self):
        self.enroll()
        original = tool.store.release
        def intervene(*args, **kwargs):
            other = tool.store.connect(self.path)
            try:
                self.assertEqual(tool.cancel(other, 'job')['status'], 'cancelled')
            finally:
                other.close()
            return original(*args, **kwargs)
        with patch.object(tool.store, 'release', intervene):
            result = tool.attempt(self.connection, 'job')
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(result['outcome']['status'], 'stale_revision')
        self.assertTrue(tool.store.snapshot(self.connection)['state']['held'])
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM receipt').fetchone()[0], 0)

    def test_cancel_during_proof_check_blocks_commit(self):
        self.enroll()
        original = tool.store.shared.check
        def intervene(*args, **kwargs):
            checked = original(*args, **kwargs)
            other = tool.store.connect(self.path)
            try:
                tool.cancel(other, 'job')
            finally:
                other.close()
            return checked
        with patch.object(tool.store.shared, 'check', intervene):
            result = tool.attempt(self.connection, 'job')
        self.assertEqual(result['status'], 'cancelled')
        self.assertFalse(result['outcome']['applied'])

    def test_cancel_after_commit_reports_completed_not_undone(self):
        self.enroll()
        tool.reserve(self.connection, 'job')
        tool.store.release(self.connection, self.payload, self.revision, operation='job')
        before = tool.store.snapshot(self.connection)
        self.assertEqual(tool.cancel(self.connection, 'job')['status'], 'completed')
        self.assertEqual(tool.store.snapshot(self.connection), before)

    def test_cancel_does_not_invalidate_a_newer_generation(self):
        self.enroll()
        before = tool.store.revise(self.connection, ack=False)
        self.assertEqual(tool.cancel(self.connection, 'job')['status'], 'cancelled')
        self.assertEqual(tool.store.snapshot(self.connection), before)
        with patch.object(tool.store, 'release', side_effect=AssertionError('cancelled intent')):
            self.assertEqual(tool.attempt(self.connection, 'job')['status'], 'cancelled')

    def test_parallel_reservations_cannot_overspend(self):
        self.enroll(2)
        def reserve(_):
            connection = tool.store.connect(self.path)
            try:
                return tool.reserve(connection, 'job')['status']
            finally:
                connection.close()
        with ThreadPoolExecutor(max_workers=6) as pool:
            outcomes = list(pool.map(reserve, range(6)))
        self.assertEqual(outcomes.count('reserved'), 2)
        self.assertEqual(outcomes.count('budget_exhausted'), 4)
        self.assertEqual(tool.inspect(self.connection, 'job')['attempts'], 2)

    def test_binding_and_budget_cannot_be_rewritten(self):
        self.enroll()
        before = tool.inspect(self.connection, 'job')
        self.assertEqual(tool.wire(before), tool.store.certificate.canon(dict(operation='job', revision=self.revision)))
        for change in ('revision=revision+1', "payload='{}'", 'limit_attempts=2', "request='other'"):
            with self.subTest(change=change), self.assertRaises(sqlite3.IntegrityError):
                self.connection.execute('UPDATE intent SET '+change)
        self.assertEqual(tool.inspect(self.connection, 'job'), before)
        tool.reserve(self.connection, 'job')
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute('UPDATE intent SET attempts=0')

    def test_conflicting_receipt_is_never_completion(self):
        self.enroll()
        # A different operator path used this ID at a different revision.
        revision = tool.store.revise(self.connection, ack=True)['revision']
        tool.store.release(self.connection, self.payload, revision, operation='job')
        result = tool.reconcile(self.connection, 'job')
        self.assertEqual(result['status'], 'conflict')
        self.assertEqual(result['attempts'], 0)

    def test_actual_process_loss_consumes_reserved_attempt_and_recovers_receipt(self):
        self.enroll()
        script = r'''
import importlib.util, os, sys
spec=importlib.util.spec_from_file_location('intents',sys.argv[1])
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
c=m.store.connect(sys.argv[2]);r=m.reserve(c,'job');assert r['status']=='reserved'
if sys.argv[3]=='after':
 i=r['intent'];m.store.release(c,i['payload'],i['revision'],operation='job')
os._exit(73)
'''
        for phase in ('before', 'after'):
            if phase == 'after':
                # A separate database, so no spent budget is reset.
                path = Path(self.path.parent)/'after.sqlite'
                c = tool.store.connect(path)
                tool.store.initialize(c, self.selection);tool.initialize(c)
                revision = tool.store.revise(c, ack=True)['revision']
                tool.enroll(c, 'job', revision, self.payload, 1)
                c.close()
            else:
                path = self.path
            process = subprocess.run([sys.executable, '-c', script, str(ROOT/'integration/agent_intents.py'),
                                      str(path), phase], capture_output=True, timeout=30)
            self.assertEqual(process.returncode, 73, process.stderr)
            c = tool.store.connect(path)
            try:
                recovered = tool.attempt(c, 'job')
                self.assertEqual(recovered['status'], 'budget_exhausted' if phase=='before' else 'completed')
                self.assertEqual(recovered['attempts'], 1)
                self.assertEqual(tool.store.snapshot(c)['state']['held'], phase=='before')
            finally:
                c.close()

    def test_cancel_storage_failure_rolls_back_revision_and_status(self):
        self.enroll()
        before = tool.store.snapshot(self.connection)
        def deny(action, table, *unused):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_UPDATE and table == 'intent' else sqlite3.SQLITE_OK
        self.connection.set_authorizer(deny)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                tool.cancel(self.connection, 'job')
        finally:
            self.connection.set_authorizer(None)
        self.assertFalse(self.connection.in_transaction)
        self.assertEqual(tool.store.snapshot(self.connection), before)
        self.assertEqual(tool.inspect(self.connection, 'job')['status'], 'pending')

    def test_demo_and_identity_freeze(self):
        self.assertEqual(tool.run()['recovered'], 'completed')
        import copy
        payload = copy.deepcopy(self.payload)
        intent = tool.enroll(self.connection, 'job', self.revision, payload, 1)
        payload['proofs'].clear()
        self.assertEqual(tool.inspect(self.connection, 'job')['payload'], intent['payload'])
        for budget in (True, 0, -1, 1.5, 1001):
            with self.subTest(budget=budget), self.assertRaises(ValueError):
                tool.enroll(self.connection, 'other', self.revision, self.payload, budget)
