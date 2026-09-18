"""Composition must enforce every independent request before publication."""
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from stargate import artifact, bundle
from stargate.policy import author_policy
from stargate.records import canon, decode, public_key, InvalidRecord
from stargate.store import Store, StoreError


class AdmitAll(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / 'candidate'
        self.data = b'approved text'
        self.source.write_bytes(self.data)
        self.digest = hashlib.sha256(self.data).hexdigest()
        self.output = self.root / 'approved'
        self.store = Store(self.root / 'objects')
        self.keys = [Ed25519PrivateKey.generate() for _ in range(2)]
        self.requests = [self.request('review', 'reviewed', 0),
                         self.request('measurement', 'text', 1)]
        self.requests[1].pop('facts')
        self.requests[1]['derive'] = {'text': {'utf8': True}}

    def request(self, name, fact, signer, *, subject=None, value=True):
        rule = f'fact {fact}: bool\ncheck {fact}'
        facts = {fact: value}
        trust = [public_key(self.keys[signer])]
        item = author_policy(rule, facts, self.store, self.keys[signer],
                             subject=self.digest if subject is None else subject)
        raw = bundle.export_bundle(self.store.read(item['object']), self.store, set(trust))[0]
        return dict(name=name, bundle=raw, trust=trust, rule=rule, facts=facts)

    def run_all(self):
        return artifact.admit_all(self.requests, subject=self.source, output=self.output)

    def clean(self):
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.root.glob('.sg-admit-*')), [])

    def test_all_hold_one_read_and_publish_only_after_last(self):
        real = artifact.require_bundle
        chunks = artifact._subject_chunks
        calls = []
        def check(*args, **kwargs):
            self.assertFalse(self.output.exists())
            calls.append(kwargs['subject'])
            self.source.write_bytes(b'changed between decisions')
            return real(*args, **kwargs)
        with patch.object(artifact, 'require_bundle', side_effect=check), \
             patch.object(artifact, '_subject_chunks', wraps=chunks) as reads:
            result = self.run_all()
        self.assertEqual(reads.call_count, 1)
        self.assertEqual(calls, [self.digest, self.digest])
        self.assertEqual(result['status'], 'admitted')
        self.assertEqual([r['name'] for r in result['requirements']], ['review', 'measurement'])
        self.assertEqual(result['requirements'][1]['report']['derivation']['facts'], {'text': True})
        self.assertEqual(self.output.read_bytes(), self.data)
        self.assertEqual(self.output.stat().st_mode & 0o777, 0o600)

    def test_all_derivers_consume_the_same_stream(self):
        self.requests[0] = self.request('size', 'large', 0)
        self.requests[0].pop('facts')
        self.requests[0]['derive'] = {'large': {'size_at_least': len(self.data)}}
        report = self.run_all()
        self.assertEqual(report['status'], 'admitted')
        derived = [entry['report']['derivation'] for entry in report['requirements']]
        self.assertEqual([d['facts'] for d in derived], [{'large': True}, {'text': True}])
        self.assertEqual([d['subject'] for d in derived], [self.digest, self.digest])
        self.output.unlink()
        self.requests[0]['derive']['large']['size_at_least'] += 1
        report = self.run_all()
        self.assertEqual((report['status'], report['failed']), ('unsatisfied', 'size'))
        self.clean()

    def test_second_reject_blocks_publication(self):
        self.requests[1] = self.request('measurement', 'text', 1, value=False)
        result = self.run_all()
        self.assertEqual(result['status'], 'unsatisfied')
        self.assertEqual(result['failed'], 'measurement')
        self.assertEqual(result['requirements'][-1]['report']['reason'], 'decision_reject')
        self.clean()

    def test_second_subject_must_match_same_staged_bytes(self):
        self.requests[1] = self.request('measurement', 'text', 1, subject='ab'*32)
        result = self.run_all()
        self.assertEqual(result['requirements'][-1]['report']['reason'], 'subject_mismatch')
        self.clean()

    def test_no_trust_union_between_roles(self):
        # B is allowed for the first role, but only A for the second.
        self.requests[0]['trust'].append(public_key(self.keys[1]))
        self.requests[1]['trust'] = [public_key(self.keys[0])]
        with self.assertRaises(InvalidRecord):
            self.run_all()
        self.clean()

    def test_missing_second_material_is_unverified(self):
        doc = decode(self.requests[1]['bundle'])
        del doc['objects'][doc['envelope']['body']['policy']['rule']]
        self.requests[1]['bundle'] = canon(doc)
        with self.assertRaises(StoreError):
            self.run_all()
        self.clean()

    def test_snapshot_requests_before_verification(self):
        real = artifact.require_bundle
        def change(*args, **kwargs):
            self.requests[1]['trust'].clear()
            self.requests[1]['derive']['text'] = {'size_at_most': 0}
            return real(*args, **kwargs)
        with patch.object(artifact, 'require_bundle', side_effect=change):
            self.assertEqual(self.run_all()['status'], 'admitted')

    def test_invalid_plan_never_reads_subject(self):
        original = self.requests
        cases = [[], original * 17, [original[0], original[0]],
                 [dict(original[0], derive={})], [dict(original[0], trust=[])],
                 [dict(original[0], unexpected=True)]]
        with patch.object(artifact, '_subject_chunks', side_effect=AssertionError('read')):
            for case in cases:
                with self.subTest(case=len(case)):
                    with self.assertRaises(ValueError):
                        artifact.admit_all(case, subject=self.source, output=self.output)
                    self.clean()

    def test_first_refusal_does_not_claim_second_checked(self):
        self.requests[0] = self.request('review', 'reviewed', 0, value=False)
        self.requests[1]['bundle'] = b'invalid later proof'
        result = self.run_all()
        self.assertEqual(result['failed'], 'review')
        self.assertEqual(len(result['requirements']), 1)
        self.clean()

    def test_destination_race_preserves_occupant(self):
        real = artifact.require_bundle
        def occupy(*args, **kwargs):
            self.output.write_bytes(b'occupant')
            return real(*args, **kwargs)
        with patch.object(artifact, 'require_bundle', side_effect=occupy):
            with self.assertRaises(FileExistsError):
                self.run_all()
        self.assertEqual(self.output.read_bytes(), b'occupant')
        self.assertEqual(list(self.root.glob('.sg-admit-*')), [])

    def plan(self):
        plan = []
        for req in self.requests:
            entry = dict(req)
            for key in ('bundle', 'rule', 'facts', 'derive'):
                if key not in entry:
                    continue
                name = req['name'] + '.' + key
                path = self.root / name
                value = entry[key]
                path.write_bytes(value if key == 'bundle' else
                                 value.encode() if key == 'rule' else json.dumps(value).encode())
                entry[key] = name
            plan.append(entry)
        path = self.root / 'plan.json'
        path.write_text(json.dumps(plan))
        return path

    def cli(self, plan):
        done = subprocess.run([sys.executable, '-m', 'stargate', 'admit-all', str(plan),
                               '--subject', str(self.source), '--output', str(self.output)],
                              capture_output=True, text=True)
        return done.returncode, json.loads(done.stdout or done.stderr)

    def test_cli_relative_plan_paths_and_success(self):
        code, report = self.cli(self.plan())
        self.assertEqual((code, report['status']), (0, 'admitted'))
        self.assertEqual(self.output.read_bytes(), self.data)

    def test_cli_refusal_missing_and_malformed_inputs(self):
        self.requests[1] = self.request('measurement', 'text', 1, value=False)
        plan = self.plan()
        code, report = self.cli(plan)
        self.assertEqual((code, report['status']), (4, 'unsatisfied'))
        self.clean()
        (self.root / 'measurement.bundle').unlink()
        code, report = self.cli(plan)
        self.assertEqual((code, report['status']), (3, 'unverified'))
        self.clean()
        plan.write_text('[{"name":"x","name":"y"}]')
        code, report = self.cli(plan)
        self.assertEqual((code, report['status']), (2, 'invalid'))
        self.clean()
