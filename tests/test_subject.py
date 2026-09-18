import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from stargate import bundle, cli
from stargate.policy import author_policy
from stargate.records import DOMAIN, canon, decode, record_id, public_key, InvalidRecord
from stargate.store import Store

RULE = 'fact reviewed: bool\ncheck reviewed'
FACTS = {'reviewed': True}
A = b'release artifact A\x00\xff'
B = b'release artifact B\x00\xff'
HA = hashlib.sha256(A).hexdigest()
HB = hashlib.sha256(B).hexdigest()


class Subject(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.store = Store(self.root/'objects')
        self.key = Ed25519PrivateKey.generate()
        self.trust = {public_key(self.key)}

    def make(self, subject=HA):
        item = author_policy(RULE, FACTS, self.store, self.key, subject=subject)
        return bundle.export_bundle(self.store.read(item['object']), self.store, self.trust)[0]

    def require(self, raw, subject=HA):
        return bundle.require_bundle(raw, self.trust, rule=RULE, facts=FACTS, subject=subject)

    def test_exact_subject_required(self):
        raw = self.make()
        ok = self.require(raw)
        self.assertEqual(ok['status'], 'satisfied')
        self.assertEqual(ok['expected']['subject'], HA)
        self.assertEqual(ok['verification']['subject'], HA)
        other = self.require(raw, HB)
        self.assertEqual((other['status'], other['reason']), ('unsatisfied', 'subject_mismatch'))
        self.assertEqual(other['verification']['decision'], 'accept')

    def test_absence_is_not_wildcard_in_either_direction(self):
        for raw, expected in ((self.make(), None), (self.make(None), HA)):
            report = self.require(raw, expected)
            self.assertEqual((report['status'], report['reason']), ('unsatisfied', 'subject_mismatch'))
        self.assertEqual(self.require(self.make(None), None)['status'], 'satisfied')

    def test_hash_is_signed_and_resigning_changes_identity(self):
        raw = self.make(); doc = decode(raw)
        original = record_id(doc['envelope']['body'])
        doc['envelope']['body']['subject'] = HB
        with self.assertRaisesRegex(InvalidRecord, 'signature'):
            self.require(canon(doc))
        rid = record_id(doc['envelope']['body'])
        self.assertNotEqual(rid, original)
        doc['envelope']['signature'] = self.key.sign(DOMAIN + bytes.fromhex(rid)).hex()
        report = self.require(canon(doc))
        self.assertEqual(report['reason'], 'subject_mismatch')
        self.assertEqual(self.require(canon(doc), HB)['status'], 'satisfied')

    def test_subject_is_not_a_transport_dependency(self):
        raw = self.make()
        self.assertNotIn(HA, decode(raw)['objects'])
        self.assertIsNone(self.store.get(bytes.fromhex(HA)))
        with patch.object(Store, 'get', side_effect=AssertionError('store fallback')):
            self.assertEqual(self.require(raw)['status'], 'satisfied')
        doc = decode(raw); doc['objects'][HA] = A.hex()
        with self.assertRaisesRegex(InvalidRecord, 'outside'):
            self.require(canon(doc))

    def test_missing_or_malformed_signed_subject_refused(self):
        for subject in ('A'*64, 'bad', 1, {}, False):
            with self.assertRaises(InvalidRecord): self.make(subject)
            with self.assertRaises(InvalidRecord): self.require(self.make(), subject)
        doc = decode(self.make()); del doc['envelope']['body']['subject']
        with self.assertRaisesRegex(InvalidRecord, 'fields'):
            self.require(canon(doc))

    def test_file_hash_binary_empty_and_rename(self):
        a = self.root/'a'; a.write_bytes(A)
        self.assertEqual(cli.subject_hash(a), HA)
        a.rename(self.root/'renamed')
        self.assertEqual(cli.subject_hash(self.root/'renamed'), HA)
        a.write_bytes(b'')
        self.assertEqual(cli.subject_hash(a), 'e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855')
        fifo = self.root/'pipe'; os.mkfifo(fifo)
        with self.assertRaisesRegex(ValueError, 'regular file'): cli.subject_hash(fifo)

    def test_directory_is_invalid_before_wrapping_and_descriptor_is_closed(self):
        actual_open = cli.os.open
        opened = []
        def tracked_open(*args, **kwargs):
            fd = actual_open(*args, **kwargs)
            opened.append(fd)
            return fd
        with patch.object(cli.os, 'open', side_effect=tracked_open):
            with self.assertRaisesRegex(ValueError, 'subject must be a regular file'):
                cli.subject_hash(self.root)
        self.assertEqual(len(opened), 1)
        with self.assertRaises(OSError): os.fstat(opened[0])

    def test_file_change_detected(self):
        a = self.root/'a'; a.write_bytes(A)
        before = a.stat()
        class Changed:
            st_size = before.st_size + 1
            st_mtime_ns = before.st_mtime_ns
            st_ctime_ns = before.st_ctime_ns
        with patch.object(cli.os, 'fstat', side_effect=[before, Changed()]):
            with self.assertRaisesRegex(OSError, 'changed'): cli.subject_hash(a)

    def test_cli_author_export_and_require_in_empty_directory(self):
        import stargate
        env = dict(os.environ, PYTHONPATH=str(Path(stargate.__file__).parent.parent))
        cmd = [sys.executable, '-m', 'stargate']
        def run(args, cwd):
            return subprocess.run(cmd+args, cwd=cwd, env=env, capture_output=True, text=True)
        rule = self.root/'rule'; rule.write_text(RULE)
        facts = self.root/'facts'; facts.write_text(json.dumps(FACTS))
        key = self.root/'key'
        self.assertEqual(run(['keygen', str(key)], self.root).returncode, 0)
        # Derive the actual signer from the generated key through policy output's envelope.
        artifact = self.root/'artifact'; artifact.write_bytes(A)
        result = run(['--store', str(self.store.path), 'policy', str(rule), '--facts', str(facts),
                      '--key', str(key), '--subject', str(artifact)], self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        obj = json.loads(result.stdout)['object']
        signer = decode(self.store.read(obj))['body']['key']
        output = self.root/'proof'
        result = run(['--store', str(self.store.path), 'export', obj, str(output), '--trust', signer], self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        with tempfile.TemporaryDirectory() as dest:
            root = Path(dest)
            for name, content in [('proof', output.read_bytes()), ('rule', rule.read_bytes()),
                                  ('facts', facts.read_bytes()), ('different-name', A)]:
                (root/name).write_bytes(content)
            args = ['require', 'proof', '--trust', signer, '--rule', 'rule', '--facts', 'facts',
                    '--subject', 'different-name']
            result = run(args, dest); self.assertEqual(result.returncode, 0, result.stderr)
            (root/'different-name').write_bytes(B)
            result = run(args, dest); self.assertEqual(result.returncode, 4, result.stderr)
            self.assertEqual(json.loads(result.stdout)['reason'], 'subject_mismatch')
            (root/'different-name').unlink()
            (root/'different-name').mkdir()
            result = run(args, dest); self.assertEqual(result.returncode, 2, result.stderr)
            self.assertEqual(json.loads(result.stderr)['status'], 'invalid')
            self.assertEqual(json.loads(result.stderr)['error'], 'subject must be a regular file')
            (root/'different-name').rmdir()
            result = run(args, dest); self.assertEqual(result.returncode, 3)
            self.assertEqual(json.loads(result.stderr)['status'], 'unverified')
            self.assertEqual(sorted(p.name for p in root.iterdir()), ['facts', 'proof', 'rule'])
