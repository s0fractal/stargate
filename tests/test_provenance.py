from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from stargate import policy, kernel as k
from stargate.bundle import export_bundle, verify_bundle
from stargate.records import DOMAIN, InvalidRecord, canon, decode, record_id, public_key, verify_record
from stargate.store import Store, StoreError

RULE = 'fact within_window: bool\nfact retroactive: bool\ncheck within_window && !retroactive'
FACTS = dict(within_window=True, retroactive=False)


class Provenance(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        self.trust = {public_key(self.key)}
        self.authored = policy.author_policy(RULE, FACTS, self.store, self.key)
        self.raw = self.store.read(self.authored['object'])

    def resign(self, envelope):
        envelope['signature'] = self.key.sign(DOMAIN + bytes.fromhex(record_id(envelope['body']))).hex()
        return canon(envelope)

    def test_report_exposes_authenticated_source_and_facts(self):
        report = verify_record(self.raw, self.store, self.trust)
        self.assertEqual(report['policy'], dict(self.authored['policy'], source=RULE, inputs=FACTS))
        bundle, exported = export_bundle(self.raw, self.store, self.trust)
        objects = decode(bundle)['objects']
        self.assertIn(self.authored['policy']['rule'], objects)
        self.assertIn(self.authored['policy']['facts'], objects)
        with patch.object(Store, 'get', side_effect=AssertionError('local-store fallback')):
            self.assertEqual(verify_bundle(bundle, self.trust), report)
        self.assertEqual(exported, report)

    def test_same_rule_different_facts_gives_different_decision(self):
        other = policy.author_policy(RULE, dict(FACTS, retroactive=True), self.store, self.key)
        self.assertEqual(other['policy']['rule'], self.authored['policy']['rule'])
        self.assertNotEqual(other['policy']['facts'], self.authored['policy']['facts'])
        self.assertNotEqual(other['record'], self.authored['record'])
        report = verify_record(self.store.read(other['object']), self.store, self.trust)
        self.assertEqual(report['decision'], 'reject')
        self.assertTrue(report['policy']['inputs']['retroactive'])

    def test_renamed_facts_same_term_distinct_signed_identity(self):
        a = policy.author_policy('fact a: bool\ncheck a', {'a': True}, self.store, self.key)
        b = policy.author_policy('fact x: bool\ncheck x', {'x': True}, self.store, self.key)
        self.assertEqual(a['check'], b['check'])
        self.assertNotEqual(a['record'], b['record'])
        self.assertNotEqual(a['policy'], b['policy'])

    def test_source_and_facts_replacement_need_new_signature(self):
        for field, raw in (('rule', b'check true'), ('facts', canon(dict(FACTS, retroactive=True)))):
            envelope = decode(self.raw)
            envelope['body']['policy'][field] = self.store.put(raw)
            with self.assertRaisesRegex(InvalidRecord, 'signature'):
                verify_record(canon(envelope), self.store, self.trust)

    def test_valid_signature_cannot_bind_wrong_facts_to_existing_term(self):
        envelope = decode(self.raw)
        envelope['body']['policy']['facts'] = self.store.put(canon(dict(FACTS, retroactive=True)))
        with self.assertRaisesRegex(InvalidRecord, 'does not match'):
            verify_record(self.resign(envelope), self.store, self.trust)

    def test_valid_signature_cannot_bind_wrong_check_even_same_result(self):
        envelope = decode(self.raw)
        # Both reduce to TRUE, but only one is the declared rule's compilation.
        forged = policy.compile_source('check true').check
        forged['atp'] = envelope['body']['check']['atp']
        envelope['body']['check'] = forged
        with self.assertRaisesRegex(InvalidRecord, 'does not match'):
            verify_record(self.resign(envelope), self.store, self.trust)

    def test_missing_source_or_facts_is_unverified(self):
        bundle, _ = export_bundle(self.raw, self.store, self.trust)
        for h in self.authored['policy'].values():
            doc = decode(bundle); del doc['objects'][h]
            with self.assertRaisesRegex(StoreError, h):
                verify_bundle(canon(doc), self.trust)

    def test_corrupt_source_or_facts_refused(self):
        bundle, _ = export_bundle(self.raw, self.store, self.trust)
        for h in self.authored['policy'].values():
            doc = decode(bundle); doc['objects'][h] = b'bad'.hex()
            with self.assertRaisesRegex(InvalidRecord, 'hash mismatch'):
                verify_bundle(canon(doc), self.trust)

    def test_external_fact_domain_is_exact_and_boolean(self):
        for facts in ({}, dict(FACTS, extra=True), dict(FACTS, within_window=1), None, []):
            with self.assertRaises((InvalidRecord, policy.PolicyError)):
                policy.author_policy(RULE, facts, self.store, self.key)
        with self.assertRaises(policy.PolicyError):
            policy.author_policy('fact a: bool = true\ncheck a', {'a': True}, self.store, self.key)

    def test_old_unsigned_source_shape_is_not_accepted(self):
        envelope = decode(self.raw); del envelope['body']['policy']
        with self.assertRaisesRegex(InvalidRecord, 'fields'):
            verify_record(self.resign(envelope), self.store, self.trust)

    def test_untrusted_signature_does_not_invoke_compiler(self):
        with patch('stargate.compiler.compile_source', side_effect=AssertionError('untrusted compile')):
            with self.assertRaisesRegex(InvalidRecord, 'trusted'):
                verify_record(self.raw, self.store, set())
