import hashlib
import json
from pathlib import Path
import random
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from stargate import artifact, bundle
from stargate.facts import FactDeriver
from stargate.policy import author_policy, PolicyError
from stargate.records import public_key
from stargate.store import Store

RULE = 'fact nonempty: bool\nfact small: bool\nfact text: bool\ncheck nonempty && small && text'
PROFILE = {'nonempty': {'size_at_least': 1}, 'small': {'size_at_most': 64}, 'text': {'utf8': True}}


class DerivedFacts(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root/'source'
        self.output = self.root/'approved'
        self.store = Store(self.root/'objects')
        self.key = Ed25519PrivateKey.generate()
        self.trust = {public_key(self.key)}

    def make(self, data, facts):
        self.source.write_bytes(data)
        item = author_policy(RULE, facts, self.store, self.key, subject=hashlib.sha256(data).hexdigest())
        return bundle.export_bundle(self.store.read(item['object']), self.store, self.trust)[0]

    def admit(self, raw, profile=PROFILE):
        return artifact.admit_bundle(raw, self.trust, rule=RULE, derive=profile,
                                     subject=self.source, output=self.output)

    def test_signed_lie_about_subject_is_unsatisfied(self):
        raw = self.make(b'\xff', {'nonempty': True, 'small': True, 'text': True})
        # The signed computation is valid; its facts are false of this artifact.
        self.assertEqual(bundle.verify_bundle(raw, self.trust)['decision'], 'accept')
        report = self.admit(raw)
        self.assertEqual(report['status'], 'unsatisfied')
        self.assertEqual(report['reason'], 'facts_mismatch')
        self.assertEqual(report['derivation']['facts'], {'nonempty': True, 'small': True, 'text': False})
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob('.sg-admit-*')))

    def test_honest_false_facts_yield_decision_reject(self):
        raw = self.make(b'', {'nonempty': False, 'small': True, 'text': True})
        report = self.admit(raw)
        self.assertEqual((report['status'], report['reason']), ('unsatisfied', 'decision_reject'))
        self.assertFalse(self.output.exists())

    def test_derivation_and_subject_use_staged_bytes_once(self):
        data = 'Привіт'.encode()
        raw = self.make(data, {'nonempty': True, 'small': True, 'text': True})
        original_chunks = artifact._subject_chunks
        original_require = artifact.require_bundle
        def replaced(*args, **kwargs):
            self.source.write_bytes(b'\xff')
            return original_require(*args, **kwargs)
        with patch.object(artifact, '_subject_chunks', wraps=original_chunks) as reads:
            with patch.object(artifact, 'require_bundle', side_effect=replaced):
                report = self.admit(raw)
        self.assertEqual(reads.call_count, 1)
        self.assertEqual(report['status'], 'admitted')
        self.assertEqual(self.output.read_bytes(), data)
        self.assertTrue(report['requirement']['derivation']['facts']['text'])
        self.assertEqual(report['artifact']['sha256'], hashlib.sha256(data).hexdigest())

    def test_utf8_and_size_against_independent_whole_byte_oracle(self):
        rng = random.Random(1101)
        samples = [b'', b'\x00', b'\xef\xbb\xbf', b'\xed\xa0\x80', b'\xc0\x80', b'\xf4\x90\x80\x80',
                   b'\xe2\x82', 'a€𐀀'.encode(), b'a'*64, b'a'*65]
        samples += [rng.randbytes(rng.randrange(80)) for _ in range(100)]
        for data in samples:
            try:
                data.decode('utf-8', errors='strict'); valid = True
            except UnicodeDecodeError:
                valid = False
            for width in (1, 2, 3, 7, 1024):
                d = FactDeriver(PROFILE)
                for i in range(0, len(data), width): d.update(data[i:i+width])
                self.assertEqual(d.finish(), {'nonempty': len(data) >= 1, 'small': len(data) <= 64, 'text': valid})

    def test_real_file_utf8_crosses_chunk_and_truncated_tail(self):
        data = b'a'*(1024*1024-1) + '€'.encode()
        profile = {'text': {'utf8': True}, 'bound': {'size_at_most': len(data)}}
        self.source.write_bytes(data)
        result = artifact.measure_subject(self.source, profile)
        self.assertEqual(result['facts'], {'text': True, 'bound': True})
        self.assertEqual(result['subject'], hashlib.sha256(data).hexdigest())
        self.source.write_bytes(data[:-1])
        self.assertFalse(artifact.measure_subject(self.source, profile)['facts']['text'])

    def test_invalid_profiles_and_snapshot(self):
        bad = [None, {}, [], {'text': {'utf8': False}}, {'x': {'size_at_most': True}},
               {'x': {'size_at_least': -1}}, {'x': {'size_at_most': 2**53}},
               {'x': {'size_at_most': 1.0}},
               {'x': {'exec': 'true'}}, {'x': {'utf8': True, 'size_at_least': 1}},
               {'check': {'utf8': True}}, {'bad name': {'utf8': True}},
               {f'x{i}': {'utf8': True} for i in range(33)}]
        for profile in bad:
            with self.subTest(profile=profile):
                with self.assertRaises(PolicyError): FactDeriver(profile)
        profile = {'x': {'size_at_least': 2}}
        d = FactDeriver(profile); profile['x']['size_at_least'] = 0
        d.update(b'a'); self.assertEqual(d.finish(), {'x': False})
        with self.assertRaisesRegex(ValueError, 'subject'):
            artifact.measure_subject(None, PROFILE)

    def test_fact_and_profile_modes_are_exclusive(self):
        raw = self.make(b'a', {'nonempty': True, 'small': True, 'text': True})
        for extra in ({}, {'facts': {}, 'derive': PROFILE}):
            with self.assertRaisesRegex(ValueError, 'exactly one'):
                artifact.admit_bundle(raw, self.trust, rule=RULE, subject=self.source, output=self.output, **extra)
        with self.assertRaises(PolicyError): self.admit(raw, {'different': {'utf8': True}})
        self.assertFalse(self.output.exists()); self.assertFalse(list(self.root.glob('.sg-admit-*')))

    def test_cli_derived_authoring_require_and_admit(self):
        import os, stargate
        env = dict(os.environ, PYTHONPATH=str(Path(stargate.__file__).parent.parent))
        rule = self.root/'rule'; rule.write_text(RULE)
        profile = self.root/'profile'; profile.write_text(json.dumps(PROFILE))
        key = self.root/'key'
        from cryptography.hazmat.primitives import serialization
        key.write_text(self.key.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                              serialization.NoEncryption()).hex())
        self.source.write_bytes('hello €'.encode())
        def run(args):
            p = subprocess.run([sys.executable, '-m', 'stargate']+args, cwd=self.root,
                               env=env, capture_output=True, text=True)
            return p
        p = run(['--store', str(self.store.path), 'policy', str(rule), '--derive', str(profile),
                 '--subject', str(self.source), '--key', str(key)])
        self.assertEqual(p.returncode, 0, p.stderr)
        authored = json.loads(p.stdout)
        self.assertEqual(authored['derivation']['facts'], {'nonempty': True, 'small': True, 'text': True})
        proof = self.root/'proof'
        proof.write_bytes(bundle.export_bundle(self.store.read(authored['object']), self.store, self.trust)[0])
        common = [str(proof), '--trust', public_key(self.key), '--rule', str(rule),
                  '--derive', str(profile), '--subject', str(self.source)]
        p = run(['require']+common); self.assertEqual(p.returncode, 0, p.stderr)
        p = run(['admit']+common+['--output', str(self.output)])
        self.assertEqual(p.returncode, 0, p.stderr); self.assertEqual(self.output.read_bytes(), self.source.read_bytes())
        self.output.unlink()
        proof.write_bytes(self.make(b'\xff', {'nonempty': True, 'small': True, 'text': True}))
        p = run(['admit']+common+['--output', str(self.output)])
        self.assertEqual(p.returncode, 4, p.stderr)
        self.assertEqual(json.loads(p.stdout)['reason'], 'facts_mismatch')
        self.assertFalse(self.output.exists())
        profile.write_text('{"text":{"utf8":true},"text":{"utf8":true}}')
        p = run(['require']+common); self.assertEqual(p.returncode, 2, p.stderr)
