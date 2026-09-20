import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from stargate.case import pack_case, inspect_case, unpack_case
from stargate.records import canon, decode, InvalidRecord


class Case(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.manifest = dict(title='A counterexample', claim='old accepts the mutant',
            scope='one fixture', limits=['not a proof of general correctness'],
            source=dict(repository='local:test', commit='ab'*20),
            entrypoint='replay.py', expected='the mutant fails the new assertion')
        self.payload = {'replay.py': b"raise RuntimeError('must never execute')\n",
                        'data/input': b'\x00\xff'}
        self.raw = pack_case(self.manifest, self.payload)

    def test_roundtrip_deterministic_and_inert(self):
        self.assertEqual(self.raw, pack_case(self.manifest, dict(reversed(list(self.payload.items())))))
        report, files = inspect_case(self.raw)
        self.assertEqual(report['status'], 'intact')
        self.assertEqual(report['case_id'], hashlib.sha256(self.raw).hexdigest())
        self.assertEqual(files, self.payload)
        out = self.root/'case'
        result = unpack_case(self.raw, out)
        self.assertEqual((result['status'], result['executed']), ('materialized', False))
        for name, value in self.payload.items():
            self.assertEqual((out/name).read_bytes(), value)
            self.assertEqual((out/name).stat().st_mode & 0o777, 0o600)

    def test_tamper_and_recomputed_packet_are_distinct(self):
        doc = decode(self.raw)
        doc['files']['data/input']['hex'] = '1234'
        with self.assertRaisesRegex(InvalidRecord, 'digest mismatch'):
            unpack_case(canon(doc), self.root/'out')
        self.assertFalse((self.root/'out').exists())
        doc['files']['data/input']['sha256'] = hashlib.sha256(bytes.fromhex('1234')).hexdigest()
        report, _ = inspect_case(canon(doc))
        self.assertEqual(report['status'], 'intact')  # integrity, NOT authentication
        self.assertNotEqual(report['case_id'], inspect_case(self.raw)[0]['case_id'])

    def test_paths_collisions_and_missing_entrypoint(self):
        bad = ['../escape', '/absolute', 'a/../b', 'a//b', 'a\\b', '.', 'a/.']
        for name in bad:
            with self.subTest(name=name), self.assertRaises(InvalidRecord):
                pack_case(self.manifest, dict(self.payload, **{name: b'x'}))
        for extra in ({'REPLAY.py': b'x'}, {'data': b'x'}, {'DATA/input/more': b'x'}):
            with self.assertRaises(InvalidRecord):
                pack_case(self.manifest, dict(self.payload, **extra))
        with self.assertRaises(InvalidRecord):
            pack_case(dict(self.manifest, entrypoint='absent'), self.payload)

    def test_existing_directory_and_symlink_untouched(self):
        out = self.root/'out'; out.mkdir(); (out/'keep').write_bytes(b'original')
        with self.assertRaises(FileExistsError): unpack_case(self.raw, out)
        link = self.root/'link'; link.symlink_to(out)
        with self.assertRaises(FileExistsError): unpack_case(self.raw, link)
        self.assertEqual(list(out.iterdir()), [out/'keep'])
        self.assertEqual((out/'keep').read_bytes(), b'original')

    def test_write_failure_removes_only_owned_directory(self):
        out = self.root/'out'
        real_open = os.open
        def fail_writes(path, flags, *args, **kwargs):
            if flags & os.O_WRONLY:
                raise PermissionError('injected write failure')
            return real_open(path, flags, *args, **kwargs)
        with patch('stargate.case.os.open', side_effect=fail_writes):
            with self.assertRaises(PermissionError): unpack_case(self.raw, out)
        self.assertFalse(out.exists())

    def test_canonical_shape_and_limits(self):
        from stargate.case import MAX_CASE_BYTES
        from stargate.store import StoreError
        for raw in (self.raw+b' ', b'{"x":1,"x":2}'):
            with self.assertRaises(InvalidRecord): inspect_case(raw)
        with self.assertRaises(StoreError): inspect_case(b'x'*(MAX_CASE_BYTES+1))
        with self.assertRaises(InvalidRecord): pack_case(self.manifest, {})
        with self.assertRaises(InvalidRecord):
            pack_case(self.manifest, dict(self.payload, **{str(i): b'' for i in range(64)}))

    def cli(self, *args):
        p = subprocess.run([sys.executable, '-m', 'stargate', *map(str,args)], capture_output=True, text=True)
        return p.returncode, json.loads(p.stdout or p.stderr)

    def test_supplied_counterexamples_replay_outside_checkout(self):
        # Explicit execution of these repository-owned fixtures, never arbitrary
        # incoming packets. The receiver commands themselves do not run code.
        examples = Path(__file__).resolve().parents[1] / 'examples'
        for name in ('m1', 'm2'):
            out = self.root/name
            unpack_case((examples/('case-' + name + '.json')).read_bytes(), out)
            run = subprocess.run([sys.executable, '-I', str(out/'replay.py')],
                                 cwd=self.root, capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            result = json.loads(run.stdout)
            self.assertEqual(result['status'], 'reproduced')
            self.assertEqual([r['failures'] for r in result['runs']], [0, 0, 0, 1])
            self.assertEqual([r['errors'] for r in result['runs']], [0, 0, 0, 0])

    def test_cli_pack_inspect_unpack_and_refusals(self):
        for name, value in self.payload.items():
            p = self.root/name; p.parent.mkdir(exist_ok=True); p.write_bytes(value)
        spec = self.root/'spec.json'
        spec.write_text(json.dumps(dict(manifest=self.manifest, files=list(self.payload))))
        packed = self.root/'case.json'
        code, report = self.cli('case-pack', spec, '--root', self.root, '--output', packed)
        self.assertEqual((code, report['status']), (0, 'intact'))
        self.assertEqual(packed.read_bytes(), self.raw)
        self.assertEqual(self.cli('inspect', '--expect-kind', 'case', packed)[0], 0)
        out = self.root/'materialized'
        self.assertEqual(self.cli('unpack', '--expect-kind', 'case', packed, '--output', out)[0], 0)
        self.assertEqual(self.cli('unpack', '--expect-kind', 'case', packed, '--output', out)[0], 1)
        self.assertEqual(self.cli('inspect', '--expect-kind', 'case', self.root/'absent')[0], 3)
        packed.write_bytes(b'{}')
        self.assertEqual(self.cli('inspect', '--expect-kind', 'case', packed)[0], 2)
