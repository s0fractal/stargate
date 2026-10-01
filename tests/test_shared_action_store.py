"""Proof eligibility must not become a stale or duplicate SQLite effect."""
from concurrent.futures import ThreadPoolExecutor
import copy
import importlib.util
from pathlib import Path
import sqlite3
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
