from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from stargate import bundle as b, kernel as k
from stargate.policy import author_policy
from stargate.records import (InvalidRecord, canon, decode, create_record,
                              public_key, verify_record)
from stargate.store import Store, StoreError


class PortableCheck(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.store = Store(self.tmp.name)
        self.key = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
        self.trust = {public_key(self.key)}

    def export_policy(self, source='check true'):
        authored = author_policy(source, self.store, self.key)
        raw, report = b.export_bundle(self.store.read(authored['object']), self.store, self.trust)
        return raw, report

    def test_portable_accept_and_reject_match_original(self):
        for source in ('check true', 'check false', 'check true && !false'):
            raw, report = self.export_policy(source)
            with patch.object(Store, 'get', side_effect=AssertionError('local store access')):
                self.assertEqual(b.verify_bundle(raw, self.trust), report)

    def test_export_omits_unused_and_nonexistent_domain_members(self):
        phantom = k.sha(b'not stored').hex()
        check = dict(term=k.K_H.hex(), atp=0, expect=k.K_H.hex(), exit='normal_form',
                     environment=sorted([phantom, k.FALSE_H.hex()]))
        self.store.put(k.FALSE_BYTES)
        env = create_record(check, self.store, self.key)
        raw, report = b.export_bundle(canon(env), self.store, self.trust)
        self.assertEqual(decode(raw)['objects'], {})
        self.assertEqual(b.verify_bundle(raw, self.trust), report)

    def test_missing_demanded_is_unverified_and_wrong_bytes_invalid(self):
        raw, _ = self.export_policy('check !false')
        doc = decode(raw); self.assertTrue(doc['objects'])
        term = doc['envelope']['body']['check']['term']
        missing = deepcopy(doc); del missing['objects'][term]
        # Exporter's local store still has the bytes; verification MUST NOT use it.
        self.assertIsNotNone(self.store.get(bytes.fromhex(term)))
        with self.assertRaisesRegex(StoreError, term):
            b.verify_bundle(canon(missing), self.trust)
        bad = deepcopy(doc); bad['objects'][term] = k.S_BYTES.hex()
        with self.assertRaisesRegex(InvalidRecord, 'hash mismatch'):
            b.verify_bundle(canon(bad), self.trust)

    def test_signature_trust_and_temperature_are_not_supplied_by_bundle(self):
        raw, _ = self.export_policy()
        with self.assertRaisesRegex(InvalidRecord, 'trusted'):
            b.verify_bundle(raw, set())
        for mutation in ('signature', 'temperature', 'trust'):
            doc = decode(raw)
            if mutation == 'signature': doc['envelope']['signature'] = '00'*64
            if mutation == 'temperature': doc['stargate_bundle'] = 31
            if mutation == 'trust': doc['trusted_keys'] = list(self.trust)
            with self.assertRaises(InvalidRecord):
                b.verify_bundle(canon(doc), self.trust)

    def test_unknown_paths_and_extra_objects_refused(self):
        raw, _ = self.export_policy()
        doc = decode(raw); doc['objects']['../../escape'] = '00'
        with self.assertRaises(InvalidRecord): b.verify_bundle(canon(doc), self.trust)
        doc = decode(raw); doc['objects'][k.S_H.hex()] = k.S_BYTES.hex()
        with self.assertRaisesRegex(InvalidRecord, 'outside'):
            b.verify_bundle(canon(doc), self.trust)

    def test_size_cap_and_no_overwrite(self):
        raw, _ = self.export_policy()
        path = Path(self.tmp.name)/'proof.json'
        b.write_bundle(path, raw)
        with self.assertRaises(FileExistsError): b.write_bundle(path, b'bad')
        self.assertEqual(path.read_bytes(), raw)
        self.assertFalse(list(path.parent.glob('.sg-export-*')))
        with patch.object(b, 'MAX_BUNDLE_BYTES', len(raw)-1):
            with self.assertRaises(StoreError): b.read_bundle(path)
            with self.assertRaises(StoreError): b.verify_bundle(raw, self.trust)

    def test_failed_export_cannot_emit_a_bundle(self):
        authored = author_policy('check !false', self.store, self.key)
        env = self.store.read(authored['object'])
        term = decode(env)['body']['check']['term']
        (self.store.path/term).unlink()
        with self.assertRaisesRegex(StoreError, term):
            b.export_bundle(env, self.store, self.trust)

    def test_cli_in_empty_directory_with_no_store(self):
        raw, _ = self.export_policy('check !false')
        # Use the actual export CLI, then take only the file to a fresh directory.
        authored = author_policy('check !false', self.store, self.key)
        output = Path(self.tmp.name)/'portable.json'
        cmd = [sys.executable, '-m', 'stargate']
        export = subprocess.run(cmd+['--store', self.tmp.name, 'export', authored['object'],
                                     str(output), '--trust', public_key(self.key)], capture_output=True, text=True)
        self.assertEqual(export.returncode, 0, export.stderr)
        with tempfile.TemporaryDirectory() as other:
            target = Path(other)/'portable.json'; target.write_bytes(output.read_bytes())
            # For checkout tests use a module search path; no object data follows it.
            import os, stargate
            env = dict(os.environ, PYTHONPATH=str(Path(stargate.__file__).parent.parent))
            result = subprocess.run(cmd+['verify-bundle', str(target), '--trust', public_key(self.key)],
                                    cwd=other, env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(json.loads(result.stdout)['decision'], 'accept')
            self.assertEqual(sorted(p.name for p in Path(other).iterdir()), ['portable.json'])
