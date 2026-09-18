import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from stargate import bundle, cli
from stargate.policy import author_policy, compile_source, PolicyError
from stargate.records import canon, decode, create_record, public_key, InvalidRecord
from stargate.store import Store, StoreError

RULE = 'fact allowed: bool\ncheck allowed'
FACTS = {'allowed': True}


class Require(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name)/'objects')
        self.key = Ed25519PrivateKey.generate()
        self.trust = {public_key(self.key)}

    def make(self, rule=RULE, facts=None):
        authored = author_policy(rule, FACTS if facts is None else facts, self.store, self.key)
        return bundle.export_bundle(self.store.read(authored['object']), self.store, self.trust)[0]

    def require(self, raw, rule=RULE, facts=None):
        return bundle.require_bundle(raw, self.trust, rule=rule, facts=FACTS if facts is None else facts)

    def test_satisfied_without_store_access(self):
        raw = self.make()
        with patch.object(Store, 'get', side_effect=AssertionError('store fallback')):
            report = self.require(raw)
        self.assertEqual(report['status'], 'satisfied')
        self.assertIsNone(report['reason'])
        self.assertEqual(report['verification']['status'], 'verified')

    def test_trusted_accept_for_easier_rule_is_unsatisfied(self):
        report = self.require(self.make('check true', {}))
        self.assertEqual(report['verification']['decision'], 'accept')
        self.assertEqual((report['status'], report['reason']), ('unsatisfied', 'rule_mismatch'))

    def test_different_facts_even_same_accept(self):
        rule = 'fact a: bool\nfact b: bool\ncheck a || b'
        raw = self.make(rule, {'a': True, 'b': False})
        report = self.require(raw, rule, {'a': False, 'b': True})
        self.assertEqual(report['verification']['decision'], 'accept')
        self.assertEqual(report['reason'], 'facts_mismatch')
        self.assertEqual(report['status'], 'unsatisfied')
        self.assertEqual(self.require(raw, rule, {'b': False, 'a': True})['status'], 'satisfied')

    def test_raw_accept_is_not_policy_accept(self):
        c = compile_source('check true')
        envelope = create_record(c.check, c.objects, self.key)
        raw, _ = bundle.export_bundle(canon(envelope), c.objects, self.trust)
        report = self.require(raw)
        self.assertEqual((report['status'], report['reason']), ('unsatisfied', 'policy_missing'))

    def test_matching_reject_is_unsatisfied(self):
        report = self.require(self.make(RULE, {'allowed': False}), RULE, {'allowed': False})
        self.assertEqual((report['status'], report['reason']), ('unsatisfied', 'decision_reject'))
        self.assertEqual(report['verification']['status'], 'verified')

    def test_invalid_and_missing_are_not_unsatisfied(self):
        raw = self.make()
        with self.assertRaises(InvalidRecord):
            bundle.require_bundle(raw, set(), rule=RULE, facts=FACTS)
        doc = decode(raw); doc['envelope']['signature'] = '00'*64
        with self.assertRaises(InvalidRecord): self.require(canon(doc))
        doc = decode(raw); del doc['objects'][doc['envelope']['body']['policy']['rule']]
        with self.assertRaises(StoreError): self.require(canon(doc))

    def test_request_validation_and_exact_rule_bytes(self):
        raw = self.make()
        for facts in ({}, {'allowed': 1}, {'allowed': True, 'extra': False}):
            with self.assertRaises(PolicyError): self.require(raw, RULE, facts)
        report = self.require(raw, RULE+'\n')
        self.assertEqual(report['reason'], 'rule_mismatch')

    def test_cli_statuses_and_duplicate_facts(self):
        root = Path(self.tmp.name)
        rule = root/'rule.wpl'; rule.write_text(RULE)
        facts = root/'facts.json'; facts.write_text(json.dumps(FACTS))
        path = root/'proof.json'
        args = ['require', str(path), '--trust', public_key(self.key),
                '--rule', str(rule), '--facts', str(facts)]
        def run():
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(args)
            return code, json.loads(out.getvalue() or err.getvalue())
        path.write_bytes(self.make()); self.assertEqual(run()[0], 0)
        path.write_bytes(self.make('check true', {}))
        code, report = run(); self.assertEqual(code, 4); self.assertEqual(report['status'], 'unsatisfied')
        facts.write_text('{"allowed":false}')
        path.write_bytes(self.make(RULE, {'allowed': False}))
        code, report = run(); self.assertEqual(code, 4); self.assertEqual(report['reason'], 'decision_reject')
        facts.write_text(json.dumps(FACTS))
        path.write_bytes(b'bad'); self.assertEqual(run()[0], 2)
        path.unlink(); self.assertEqual(run()[0], 3)
        path.write_bytes(self.make()); facts.write_text('{"allowed":true,"allowed":false}')
        self.assertEqual(run()[0], 2)
