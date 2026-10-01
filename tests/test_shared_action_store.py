"""Proof eligibility must not become a stale or duplicate SQLite effect."""
from concurrent.futures import ThreadPoolExecutor
import copy
import importlib.util
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('shared_store', ROOT/'integration/shared_action_store.py')
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)


class SharedActionStore(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.selection, cls.payload = tool.fixture()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name)/'resource.sqlite'
        self.connection = tool.connect(self.path)
        self.addCleanup(self.connection.close)
        tool.initialize(self.connection, self.selection)

    def acknowledge(self):
        return tool.revise(self.connection, ack=True)['revision']

    def test_experiment_and_single_release_replay(self):
        self.assertEqual(tool.run()['status'], 'passed')
        before = tool.snapshot(self.connection)
        self.assertEqual(tool.release(self.connection, self.payload, 0)['status'], 'no_release')
        self.assertEqual(tool.snapshot(self.connection), before)
        revision = self.acknowledge()
        self.assertTrue(tool.release(self.connection, self.payload, revision)['applied'])
        after = tool.snapshot(self.connection)
        self.assertEqual(after['state'], dict(held=False, ack=True))
        self.assertEqual(tool.release(self.connection, self.payload, revision)['status'], 'stale_revision')
        self.assertEqual(tool.release(self.connection, self.payload, revision+1)['status'], 'no_release')
        self.assertEqual(tool.snapshot(self.connection), after)

    def test_changed_state_selection_and_aba_during_check_do_not_apply(self):
        original = tool.shared.check
        for mutation in ('new_handoff', 'selection', 'aba'):
            revision = tool.revise(self.connection, held=True, ack=True, selection=self.selection)['revision']
            changed = []
            def intervene(*args, **kwargs):
                result = original(*args, **kwargs)
                if mutation == 'selection':
                    selection = copy.deepcopy(self.selection)
                    selection['expected_contracts']['custodian'] = '0'*64
                    tool.revise(self.connection, selection=selection)
                else:
                    tool.revise(self.connection, held=True, ack=False)
                    if mutation == 'aba':
                        tool.revise(self.connection, ack=True)
                changed.append(tool.snapshot(self.connection))
                return result
            with self.subTest(mutation=mutation), patch.object(tool.shared, 'check', intervene):
                result = tool.release(self.connection, self.payload, revision)
            self.assertEqual(result['status'], 'stale_revision')
            self.assertFalse(result['applied'])
            self.assertEqual(tool.snapshot(self.connection), changed[0])

    def test_two_simultaneous_verified_attempts_have_one_effect(self):
        revision = self.acknowledge()
        rendezvous = threading.Barrier(2, timeout=20)
        original = tool.shared.check
        def together(*args, **kwargs):
            result = original(*args, **kwargs)
            rendezvous.wait()
            return result
        def attempt():
            connection = tool.connect(self.path)
            try:
                return tool.release(connection, self.payload, revision)
            finally:
                connection.close()
        with patch.object(tool.shared, 'check', together), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(sorted(r['status'] for r in results), ['applied', 'stale_revision'])
        final = tool.snapshot(self.connection)
        self.assertEqual(final['revision'], revision+1)
        self.assertEqual(final['state'], dict(held=False, ack=True))

    def test_refusal_incomplete_and_bad_proofs_have_no_effect(self):
        revision = self.acknowledge()
        before = tool.snapshot(self.connection)
        self.assertEqual(tool.release(self.connection, self.payload, revision, max_steps=0)['status'], 'not_admitted')
        # A real refutation under a selected alternative candidate must block effects.
        _, artifacts = tool.shared.run()
        choices = tool.shared.document(artifacts['selections.json'])
        selection = dict(self.selection, expected_candidate=choices['candidates']['premature'])
        revision = tool.revise(self.connection, selection=selection)['revision']
        payload = dict(self.payload, candidate=artifacts['premature/candidate.json'], proofs=dict(
            custodian=artifacts['premature/custodian/refutation.json'],
            reclaimer=artifacts['premature/reclaimer/certificate.json']))
        before = tool.snapshot(self.connection)
        self.assertEqual(tool.release(self.connection, payload, revision)['status'], 'not_admitted')
        self.assertEqual(tool.snapshot(self.connection), before)
        with self.assertRaises(ValueError):
            tool.release(self.connection, self.payload, revision)
        self.assertEqual(tool.snapshot(self.connection), before)

    def test_live_state_must_belong_to_both_certified_sets(self):
        revision = tool.revise(self.connection, held=False, ack=False)['revision']
        before = tool.snapshot(self.connection)
        self.assertEqual(tool.release(self.connection, self.payload, revision)['status'], 'state_not_certified')
        self.assertEqual(tool.snapshot(self.connection), before)

    def test_lying_projector_cannot_release_before_acknowledgement(self):
        original = tool.projection.project
        before = tool.snapshot(self.connection)
        def corrupt(*args):
            report, table = original(*args)
            doc = tool.decode(table)
            for row in doc['rows']:
                if row['state'] == dict(held=True, ack=False) and row['event'] == dict(a=False, b=True):
                    row['next']['held'] = False
            return report, tool.certificate.canon(doc)
        with patch.object(tool.projection, 'project', corrupt):
            result = tool.release(self.connection, self.payload, 0)
        self.assertEqual(result['status'], 'projection_refused')
        self.assertEqual(result['projection_check']['status'], 'mismatch')
        self.assertEqual(tool.snapshot(self.connection), before)

    def test_selected_projection_checker_is_required(self):
        selection = dict(self.selection, expected_projection_checker='0'*64)
        revision = tool.revise(self.connection, ack=True, selection=selection)['revision']
        before = tool.snapshot(self.connection)
        result = tool.release(self.connection, self.payload, revision)
        self.assertEqual(result['status'], 'projection_refused')
        self.assertEqual(result['projection_check']['status'], 'projection_checker_unavailable')
        self.assertEqual(tool.snapshot(self.connection), before)

    def test_caller_mutation_cannot_replace_checked_payload(self):
        revision = self.acknowledge()
        payload = copy.deepcopy(self.payload)
        original = tool.shared.check
        def replace(*args, **kwargs):
            result = original(*args, **kwargs)
            payload['proofs'].clear()
            payload['contracts'].clear()
            payload['candidate'] = b'{}'
            return result
        with patch.object(tool.shared, 'check', replace):
            self.assertTrue(tool.release(self.connection, payload, revision)['applied'])

    def test_sql_failure_and_uncommitted_transaction_never_report_applied(self):
        revision = self.acknowledge()
        before = tool.snapshot(self.connection)
        self.connection.execute('BEGIN')
        with self.assertRaisesRegex(ValueError, 'autocommit'):
            tool.release(self.connection, self.payload, revision)
        self.connection.rollback()
        def deny_update(action, *unused):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_UPDATE else sqlite3.SQLITE_OK
        self.connection.set_authorizer(deny_update)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                tool.release(self.connection, self.payload, revision)
        finally:
            self.connection.set_authorizer(None)
        self.assertEqual(tool.snapshot(self.connection), before)

    def test_revision_cannot_be_reused_by_an_ordinary_update(self):
        before = tool.snapshot(self.connection)
        with self.assertRaises(sqlite3.IntegrityError):
            self.connection.execute('UPDATE resource SET ack=1 WHERE id=1')
        self.assertEqual(tool.snapshot(self.connection), before)

    def test_receipt_survives_reopen_and_does_not_authorize_new_generation(self):
        revision = self.acknowledge()
        first = tool.release(self.connection, self.payload, revision, operation='agent.release.1')
        self.assertTrue(first['applied'])
        # A later operator change is not undone or treated as permission by replay.
        current = tool.revise(self.connection, held=True, ack=False)
        other = tool.connect(self.path)
        try:
            replay = tool.release(other, self.payload, revision, operation='agent.release.1', max_steps=0)
            self.assertEqual(replay['status'], 'already_applied')
            self.assertFalse(replay['applied'])
            self.assertEqual(replay['receipt'], first)
            self.assertEqual(tool.snapshot(other), current)
            self.assertEqual(tool.release(other, self.payload, current['revision'],
                                         operation='agent.release.1')['status'], 'operation_conflict')
        finally:
            other.close()

    def test_operation_identity_binds_every_payload_component(self):
        revision = self.acknowledge()
        tool.release(self.connection, self.payload, revision, operation='bound')
        before = tool.snapshot(self.connection)
        for field in ('world', 'candidate', 'contracts', 'proofs'):
            payload = copy.deepcopy(self.payload)
            if field in ('contracts', 'proofs'):
                payload[field]['custodian'] += b' '
            else:
                payload[field] += b' '
            with self.subTest(field=field):
                result = tool.release(self.connection, payload, revision, operation='bound')
                self.assertEqual(result['status'], 'operation_conflict')
                self.assertFalse(result['applied'])
                self.assertEqual(tool.snapshot(self.connection), before)

    def test_receipt_insert_failure_rolls_back_effect(self):
        revision = self.acknowledge()
        before = tool.snapshot(self.connection)
        def deny_receipt(action, table, *unused):
            return (sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_INSERT and table == 'receipt'
                    else sqlite3.SQLITE_OK)
        self.connection.set_authorizer(deny_receipt)
        try:
            with self.assertRaises(sqlite3.DatabaseError):
                tool.release(self.connection, self.payload, revision, operation='write-failure')
        finally:
            self.connection.set_authorizer(None)
        self.assertFalse(self.connection.in_transaction)
        self.assertEqual(tool.snapshot(self.connection), before)
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM receipt').fetchone()[0], 0)

    def test_incomplete_check_cannot_create_receipt(self):
        revision = self.acknowledge()
        before = tool.snapshot(self.connection)
        result = tool.release(self.connection, self.payload, revision, operation='retry', max_steps=0)
        self.assertEqual(result['status'], 'not_admitted')
        self.assertEqual(tool.snapshot(self.connection), before)
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM receipt').fetchone()[0], 0)
        self.assertTrue(tool.release(self.connection, self.payload, revision, operation='retry')['applied'])

    def test_concurrent_same_operation_returns_one_effect_and_one_receipt(self):
        revision = self.acknowledge()
        rendezvous = threading.Barrier(2, timeout=20)
        original = tool.shared.check
        def together(*args, **kwargs):
            result = original(*args, **kwargs)
            rendezvous.wait()
            return result
        def attempt():
            connection = tool.connect(self.path)
            try:
                return tool.release(connection, self.payload, revision, operation='same')
            finally:
                connection.close()
        with patch.object(tool.shared, 'check', together), ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: attempt(), range(2)))
        self.assertEqual(sorted(r['status'] for r in results), ['already_applied', 'applied'])
        committed = next(r for r in results if r['applied'])
        replay = next(r for r in results if not r['applied'])
        self.assertEqual(replay['receipt'], committed)
        self.assertEqual(tool.snapshot(self.connection)['revision'], revision+1)
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM receipt').fetchone()[0], 1)

    def test_process_exit_before_and_after_commit(self):
        # Actual process loss, not just a simulated timeout response. Parent
        # reopens the file and retries exactly the same operation in both cases.
        script = r"""
import importlib.util, os, sqlite3, sys
spec = importlib.util.spec_from_file_location('actuator', sys.argv[1])
tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tool)
class LostProcess(sqlite3.Connection):
    def commit(self):
        if sys.argv[3] == 'before':
            os._exit(71)
        super().commit()
        os._exit(72)
connection = sqlite3.connect(sys.argv[2], isolation_level=None, factory=LostProcess)
_, payload = tool.fixture()
tool.release(connection, payload, 1, operation='lost-response')
"""
        for phase, code in (('before', 71), ('after', 72)):
            path = Path(self.tmp.name)/(phase+'.sqlite')
            connection = tool.connect(path)
            tool.initialize(connection, self.selection)
            tool.revise(connection, ack=True)
            connection.close()
            result = subprocess.run([sys.executable, '-c', script,
                                     str(ROOT/'integration/shared_action_store.py'), str(path), phase],
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, code, result.stderr)
            connection = tool.connect(path)
            try:
                with self.subTest(phase=phase):
                    before = tool.snapshot(connection)
                    self.assertEqual(before['revision'], 1 if phase == 'before' else 2)
                    recovered = tool.release(connection, self.payload, 1, operation='lost-response')
                    self.assertEqual(recovered['status'], 'applied' if phase == 'before' else 'already_applied')
                    self.assertEqual(tool.snapshot(connection)['revision'], 2)
                    self.assertEqual(connection.execute('SELECT COUNT(*) FROM receipt').fetchone()[0], 1)
            finally:
                connection.close()

    def test_duplicate_commit_between_receipt_lookup_and_snapshot_is_recovered(self):
        revision = self.acknowledge()
        original = tool.recorded
        intervened = []
        def race(*args):
            previous = original(*args)
            if not intervened:
                intervened.append(True)
                other = tool.connect(self.path)
                try:
                    self.assertTrue(tool.release(other, self.payload, revision, operation='race')['applied'])
                finally:
                    other.close()
            return previous
        with patch.object(tool, 'recorded', race):
            recovered = tool.release(self.connection, self.payload, revision, operation='race')
        self.assertEqual(recovered['status'], 'already_applied')
        self.assertFalse(recovered['applied'])
        self.assertEqual(tool.snapshot(self.connection)['revision'], revision+1)
        self.assertEqual(self.connection.execute('SELECT COUNT(*) FROM receipt').fetchone()[0], 1)
