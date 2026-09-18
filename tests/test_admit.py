import hashlib
import json
import os
from pathlib import Path
import stat
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

RULE = 'fact reviewed: bool\ncheck reviewed'
FACTS = {'reviewed': True}
DATA = b'approved bytes\x00\xff' * 100000
HASH = hashlib.sha256(DATA).hexdigest()


class Admit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root/'source'; self.source.write_bytes(DATA)
        self.output = self.root/'approved'
        self.store = Store(self.root/'objects')
        self.key = Ed25519PrivateKey.generate()
        self.trust = {public_key(self.key)}
        item = author_policy(RULE, FACTS, self.store, self.key, subject=HASH)
        self.raw = bundle.export_bundle(self.store.read(item['object']), self.store, self.trust)[0]

    def admit(self, raw=None, **overrides):
        kwargs = dict(rule=RULE, facts=FACTS, subject=self.source, output=self.output)
        kwargs.update(overrides)
        return artifact.admit_bundle(self.raw if raw is None else raw, self.trust, **kwargs)

    def assert_clean(self):
        self.assertFalse(list(self.root.glob('.sg-admit-*')))

    def test_publishes_exact_bytes_and_private_mode(self):
        with patch.object(Store, 'get', side_effect=AssertionError('store fallback')):
            report = self.admit()
        self.assertEqual(report['status'], 'admitted')
        self.assertEqual(report['artifact'], {'path': str(self.output), 'sha256': HASH})
        self.assertEqual(self.output.read_bytes(), DATA)
        self.assertEqual(stat.S_IMODE(self.output.stat().st_mode), 0o600)
        self.assertNotEqual(self.source.stat().st_ino, self.output.stat().st_ino)
        self.source.write_bytes(b'changed later')
        self.assertEqual(self.output.read_bytes(), DATA)
        self.assert_clean()

    def test_source_replaced_during_verification_cannot_change_output(self):
        real_require = artifact.require_bundle
        def replace_source(*args, **kwargs):
            self.assertFalse(self.output.exists())
            self.source.unlink(); self.source.write_bytes(b'UNAPPROVED')
            return real_require(*args, **kwargs)
        with patch.object(artifact, 'require_bundle', side_effect=replace_source):
            report = self.admit()
        self.assertEqual(report['status'], 'admitted')
        self.assertEqual(self.output.read_bytes(), DATA)
        self.assertEqual(hashlib.sha256(self.output.read_bytes()).hexdigest(), HASH)
        self.assert_clean()

    def test_unsatisfied_never_publishes(self):
        self.source.write_bytes(b'wrong subject')
        report = self.admit()
        self.assertEqual(report['status'], 'unsatisfied')
        self.assertEqual(report['reason'], 'subject_mismatch')
        self.assertIsNone(report['artifact'])
        self.assertFalse(self.output.exists()); self.assert_clean()

    def test_invalid_and_unverified_clean_up(self):
        doc = decode(self.raw); doc['envelope']['signature'] = '00'*64
        with self.assertRaises(InvalidRecord): self.admit(canon(doc))
        self.assertFalse(self.output.exists()); self.assert_clean()
        doc = decode(self.raw); del doc['objects'][doc['envelope']['body']['policy']['rule']]
        with self.assertRaises(StoreError): self.admit(canon(doc))
        self.assertFalse(self.output.exists()); self.assert_clean()
        self.source.unlink()
        with self.assertRaises(StoreError): self.admit()
        self.assertFalse(self.output.exists()); self.assert_clean()

    def test_existing_file_and_symlink_never_overwritten(self):
        for symlink in (False, True):
            if symlink:
                self.output.symlink_to(self.source)
            else:
                self.output.write_bytes(b'existing')
            with self.assertRaises(FileExistsError): self.admit()
            self.assertEqual(self.output.read_bytes(), DATA if symlink else b'existing')
            self.assertEqual(self.source.read_bytes(), DATA)
            self.output.unlink(); self.assert_clean()
        with self.assertRaises(FileExistsError): self.admit(output=self.source)
        self.assertEqual(self.source.read_bytes(), DATA); self.assert_clean()

    def test_destination_race_and_link_failure_clean_up(self):
        real_require = artifact.require_bundle
        def create_destination(*args, **kwargs):
            self.output.write_bytes(b'concurrent writer')
            return real_require(*args, **kwargs)
        with patch.object(artifact, 'require_bundle', side_effect=create_destination):
            with self.assertRaises(FileExistsError): self.admit()
        self.assertEqual(self.output.read_bytes(), b'concurrent writer'); self.assert_clean()
        self.output.unlink()
        with patch.object(artifact.os, 'link', side_effect=PermissionError('denied')):
            with self.assertRaises(PermissionError): self.admit()
        self.assertFalse(self.output.exists()); self.assert_clean()

    def test_nonregular_and_detected_source_change_never_publish(self):
        with self.assertRaisesRegex(ValueError, 'regular file'): self.admit(subject=self.root)
        self.assertFalse(self.output.exists()); self.assert_clean()
        def changed(_):
            yield b'partial'
            raise OSError('source changed')
        with patch.object(artifact, '_subject_chunks', changed):
            with self.assertRaises(StoreError): self.admit()
        self.assertFalse(self.output.exists()); self.assert_clean()

    def test_cli_codes_and_no_recipient_store(self):
        import stargate
        env = dict(os.environ, PYTHONPATH=str(Path(stargate.__file__).parent.parent))
        recipient = self.root/'recipient'; recipient.mkdir()
        (recipient/'proof').write_bytes(self.raw)
        (recipient/'rule').write_text(RULE)
        (recipient/'facts').write_text(json.dumps(FACTS))
        args = [sys.executable, '-m', 'stargate', 'admit', 'proof', '--trust', public_key(self.key),
                '--rule', 'rule', '--facts', 'facts', '--subject', str(self.source), '--output', 'approved']
        def run():
            r = subprocess.run(args, cwd=recipient, env=env, capture_output=True, text=True)
            return r.returncode, json.loads(r.stdout or r.stderr)
        code, report = run(); self.assertEqual(code, 0); self.assertEqual(report['status'], 'admitted')
        self.assertEqual((recipient/'approved').read_bytes(), DATA)
        code, report = run(); self.assertEqual(code, 1); self.assertEqual(report['status'], 'operation_error')
        (recipient/'approved').unlink()
        self.source.write_bytes(b'wrong'); self.assertEqual(run()[0], 4)
        self.source.unlink(); self.assertEqual(run()[0], 3)
        self.source.mkdir(); self.assertEqual(run()[0], 2)
        self.assertEqual(sorted(p.name for p in recipient.iterdir()), ['facts', 'proof', 'rule'])
